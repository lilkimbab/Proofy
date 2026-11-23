import asyncio
import json
import logging
import os
import re

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self, tag_temperature: float | None = None, gen_temperature: float | None = None):
        self.provider = os.getenv("AI_PROVIDER", "ollama").lower()
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        self.ollama_model = os.getenv("OLLAMA_CHAT_MODEL", "gemma3:4b")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")
        self.max_retries = int(os.getenv("LLM_MAX_RETRIES", "3"))
        self.backoff_base = float(os.getenv("LLM_RETRY_BACKOFF_BASE", "2"))
        self.tag_temperature = tag_temperature or float(os.getenv("LLM_TAG_TEMPERATURE", "0.2"))
        self.gen_temperature = gen_temperature or float(os.getenv("LLM_GEN_TEMPERATURE", "0.4"))

    async def complete_json(self, system_prompt: str, user_prompt: str, temperature: float | None = None) -> dict:
        temp = temperature if temperature is not None else self.tag_temperature
        raw = await self._with_retry(self._call_llm, system_prompt, user_prompt, temp, json_mode=True)
        return self._parse_json(raw)

    async def complete_text(self, system_prompt: str, user_prompt: str, temperature: float | None = None) -> str:
        temp = temperature if temperature is not None else self.gen_temperature
        return await self._with_retry(self._call_llm, system_prompt, user_prompt, temp, json_mode=False)

    async def complete_with_images(
        self, system_prompt: str, user_prompt: str, images: list[str], temperature: float | None = None
    ) -> str:
        temp = temperature if temperature is not None else self.gen_temperature
        if self.provider == "openai" and images:
            return await self._with_retry(
                self._call_openai_with_images, system_prompt, user_prompt, images, temp
            )
        return await self._with_retry(self._call_llm, system_prompt, user_prompt, temp, json_mode=False)

    async def _call_llm(self, system_prompt: str, user_prompt: str, temperature: float, json_mode: bool) -> str:
        if self.provider == "prompt_only":
            return self._call_prompt_only(system_prompt, user_prompt)
        if self.provider == "openai":
            return await self._call_openai(system_prompt, user_prompt, temperature, json_mode)
        return await self._call_ollama(system_prompt, user_prompt, temperature, json_mode)

    def _call_prompt_only(self, system_prompt: str, user_prompt: str) -> str:
        return (
            "=== SYSTEM PROMPT ===\n"
            f"{system_prompt}\n\n"
            "=== USER PROMPT ===\n"
            f"{user_prompt}"
        )

    async def _call_ollama(self, system_prompt: str, user_prompt: str, temperature: float, json_mode: bool) -> str:
        payload: dict = {
            "model": self.ollama_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=600.0) as client:
            resp = await client.post(f"{self.ollama_base_url}/api/chat", json=payload)
            if resp.status_code != 200:
                raise LLMError(f"Ollama HTTP {resp.status_code}: {resp.text[:200]}")
            return resp.json()["message"]["content"]

    async def _call_openai_with_images(
        self, system_prompt: str, user_prompt: str, images: list[str], temperature: float
    ) -> str:
        if not self.openai_api_key:
            raise LLMError("OPENAI_API_KEY가 설정되지 않았습니다")

        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.openai_api_key)
        user_content: list[dict] = [{"type": "text", "text": user_prompt}]
        for img in images:
            url = img if img.startswith("data:") else f"data:image/png;base64,{img}"
            user_content.append({"type": "image_url", "image_url": {"url": url}})

        resp = await client.chat.completions.create(
            model=self.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=temperature,
        )
        return resp.choices[0].message.content or ""

    async def _call_openai(self, system_prompt: str, user_prompt: str, temperature: float, json_mode: bool) -> str:
        if not self.openai_api_key:
            raise LLMError("OPENAI_API_KEY가 설정되지 않았습니다")

        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.openai_api_key)
        kwargs: dict = {
            "model": self.openai_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        resp = await client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    async def _with_retry(self, fn, *args, **kwargs) -> str:
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return await fn(*args, **kwargs)
            except Exception as e:
                last_error = e
                wait = self.backoff_base ** attempt
                logger.warning(f"LLM 호출 실패 (시도 {attempt + 1}/{self.max_retries}): {e}. {wait:.1f}초 후 재시도")
                await asyncio.sleep(wait)
        raise LLMError(f"LLM {self.max_retries}회 재시도 후 실패: {last_error}") from last_error

    def _parse_json(self, raw: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # JSON 서브스트링 추출 시도
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            raise LLMError(f"JSON 파싱 실패: {raw[:300]}")
