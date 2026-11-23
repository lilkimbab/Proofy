"""Small JSON-in/JSON-out client for the offline content jobs.

Models are named "<provider>:<model>":
- gemini:gemini-3.8-flash      -> Google Generative Language API (APP_GEMINI_API_KEY)
- groq:openai/gpt-oss-120b     -> OpenAI-compatible endpoint (APP_CONTENT_GENERATION_API_URL/KEY,
                                  falling back to APP_LLM_API_URL/KEY)

Unlike llm_service (live lesson answers, a few seconds), these calls are
allowed to think for minutes, and they report token usage so the pipeline
can use it as a difficulty signal.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib import error, request

from app.core.config import settings

USER_AGENT = "proofy-api/1.0"  # Groq (Cloudflare) rejects urllib's default agent


class LLMError(RuntimeError):
    pass


class ModelUnavailable(LLMError):
    """The model is overloaded (503) or out of quota (429 on Gemini); try another model."""


@dataclass
class LLMResult:
    model: str
    text: str
    data: dict[str, Any] | None
    elapsed: float
    output_tokens: int = 0
    reasoning_tokens: int = 0
    raw_usage: dict[str, Any] = field(default_factory=dict)


def redact(text: str) -> str:
    """Drop account identifiers from provider error messages; records end up in a public repo."""
    return re.sub(r"\borg_[A-Za-z0-9]+", "org_[redacted]", text or "")


def extract_json_object(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            value = json.loads(text[start : end + 1])
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _post(url: str, body: dict[str, Any], headers: dict[str, str], timeout: int) -> tuple[dict[str, Any], dict[str, str]]:
    req = request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT, **headers},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8")), dict(response.headers)


class LLMClient:
    def __init__(self, *, max_rate_limit_waits: int = 4, log=None) -> None:
        self.max_rate_limit_waits = max_rate_limit_waits
        self.log = log or (lambda message: None)

    def complete_json(
        self,
        model: str,
        system: str,
        user: str,
        *,
        temperature: float = 0.7,
        reasoning: str = "high",
        timeout: int = 300,
    ) -> LLMResult:
        provider, _, name = model.partition(":")
        if not name:
            raise LLMError(f"model must look like provider:name, got {model!r}")
        started = time.time()
        if provider == "gemini":
            text, usage, output_tokens, reasoning_tokens = self._gemini(name, system, user, temperature, reasoning, timeout)
        elif provider in {"groq", "openai"}:
            text, usage, output_tokens, reasoning_tokens = self._openai_compatible(name, system, user, temperature, reasoning, timeout)
        else:
            raise LLMError(f"unknown provider {provider!r}")
        return LLMResult(
            model=model,
            text=text,
            data=extract_json_object(text),
            elapsed=time.time() - started,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            raw_usage=usage,
        )

    # ------------------------------------------------------------------ gemini
    def _gemini(self, name: str, system: str, user: str, temperature: float, reasoning: str, timeout: int):
        if not settings.gemini_api_key:
            raise LLMError("APP_GEMINI_API_KEY is not set")
        generation_config: dict[str, Any] = {"temperature": temperature, "responseMimeType": "application/json"}
        if reasoning:
            generation_config["thinkingConfig"] = {"thinkingLevel": reasoning}
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": generation_config,
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{name}:generateContent"
        headers = {"x-goog-api-key": settings.gemini_api_key}
        try:
            raw, _ = _post(url, body, headers, timeout)
        except error.HTTPError as exc:
            detail = redact(exc.read().decode("utf-8", "replace"))[:300]
            if exc.code == 400 and "thinking" in detail.lower() and reasoning:
                self.log(f"  {name}: thinkingLevel not accepted, retrying without it")
                return self._gemini(name, system, user, temperature, "", timeout)
            if exc.code in {429, 500, 503}:
                raise ModelUnavailable(f"gemini:{name} HTTP {exc.code}: {detail[:160]}") from exc
            raise LLMError(f"gemini:{name} HTTP {exc.code}: {detail}") from exc
        except (TimeoutError, error.URLError) as exc:
            raise ModelUnavailable(f"gemini:{name} {type(exc).__name__}: {exc}") from exc
        candidates = raw.get("candidates") or []
        if not candidates:
            raise LLMError(f"gemini:{name} returned no candidates: {json.dumps(raw)[:300]}")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "\n".join(part.get("text", "") for part in parts if not part.get("thought"))
        usage = raw.get("usageMetadata", {})
        return text, usage, int(usage.get("candidatesTokenCount", 0)), int(usage.get("thoughtsTokenCount", 0))

    # ------------------------------------------------------- openai-compatible
    def _openai_compatible(self, name: str, system: str, user: str, temperature: float, reasoning: str, timeout: int):
        url = settings.content_generation_api_url or settings.llm_api_url
        key = settings.content_generation_api_key or settings.llm_api_key
        if not (url and key):
            raise LLMError("APP_CONTENT_GENERATION_API_URL/KEY (or APP_LLM_API_URL/KEY) is not set")
        body: dict[str, Any] = {
            "model": name,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_completion_tokens": 32000,
            "response_format": {"type": "json_object"},
        }
        if reasoning and "gpt-oss" in name:
            body["reasoning_effort"] = reasoning
        headers = {"Authorization": f"Bearer {key}"}
        waits = 0
        too_large_retried = False
        while True:
            try:
                raw, _ = _post(url, body, headers, timeout)
                break
            except error.HTTPError as exc:
                detail = redact(exc.read().decode("utf-8", "replace"))[:400]
                if exc.code == 413 and "rate_limit" in detail and not too_large_retried:
                    # Groq's free tier sometimes counts a normal request as larger than the
                    # per-minute budget (we saw 28k "requested" for a 600-token prompt); the
                    # same request went through a minute later. Retry once after a minute.
                    too_large_retried = True
                    self.log(f"  {name}: request counted as too large for the minute budget, retrying in 61s")
                    time.sleep(61)
                    continue
                if exc.code == 429 and waits < self.max_rate_limit_waits:
                    retry_after = exc.headers.get("retry-after")
                    delay = min(float(retry_after) if retry_after else 30.0, 90.0) + 1
                    waits += 1
                    self.log(f"  {name}: rate limited, waiting {delay:.0f}s ({waits}/{self.max_rate_limit_waits})")
                    time.sleep(delay)
                    continue
                if exc.code == 400 and "json" in detail.lower() and "response_format" in body:
                    # the model produced non-JSON text; ask again without JSON mode and parse it ourselves
                    body.pop("response_format")
                    continue
                if exc.code in {429, 500, 502, 503}:
                    raise ModelUnavailable(f"{name} HTTP {exc.code}: {detail[:160]}") from exc
                raise LLMError(f"{name} HTTP {exc.code}: {detail}") from exc
            except (TimeoutError, error.URLError) as exc:
                raise ModelUnavailable(f"{name} {type(exc).__name__}: {exc}") from exc
        message = (raw.get("choices") or [{}])[0].get("message", {})
        usage = raw.get("usage", {})
        details = usage.get("completion_tokens_details") or {}
        return (
            message.get("content") or "",
            usage,
            int(usage.get("completion_tokens", 0)),
            int(details.get("reasoning_tokens", 0)),
        )
