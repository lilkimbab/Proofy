from __future__ import annotations

import os
from typing import Any


# OPENAI_BASE_URL로 OpenAI 호환 서버(예: Gemini의 /v1beta/openai)를 쓸 수 있다.
# document_agent/roadmap_agent의 OpenAI SDK도 같은 환경 변수를 읽는다.
OPENAI_API_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def get_ai_provider() -> str:
    provider = os.getenv("AI_PROVIDER", "auto").lower()
    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        return "openai"
    if provider == "ollama" and os.getenv("OLLAMA_BASE_URL"):
        return "ollama"
    if provider == "local":
        return "local"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("OLLAMA_BASE_URL"):
        return "ollama"
    return "local"


async def create_tutor_answer(
    *,
    question: str,
    selected_text: str = "",
    chunks: list[dict[str, Any]],
    document_title: str = "",
    personalization_instructions: str = "",
) -> str | None:
    provider = get_ai_provider()
    if provider == "openai":
        return await create_openai_tutor_answer(
            question=question,
            selected_text=selected_text,
            chunks=chunks,
            document_title=document_title,
            personalization_instructions=personalization_instructions,
        )
    if provider == "ollama":
        return await create_ollama_tutor_answer(
            question=question,
            selected_text=selected_text,
            chunks=chunks,
            document_title=document_title,
            personalization_instructions=personalization_instructions,
        )
    return None


async def create_openai_tutor_answer(
    *,
    question: str,
    selected_text: str,
    chunks: list[dict[str, Any]],
    document_title: str,
    personalization_instructions: str,
) -> str | None:
    import httpx

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
    }
    body = {
        "model": os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini"),
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": "\n".join([
                    "너는 업로드된 학습 자료만 근거로 설명하는 AI 과외 선생님이다.",
                    "제공된 자료에서 확인할 수 없는 내용은 모른다고 말한다.",
                    "선택한 부분이 있으면 그 문맥을 우선해서 설명한다.",
                    personalization_instructions,
                ]),
            },
            {
                "role": "user",
                "content": "\n\n".join(filter(None, [
                    f"질문: {question}",
                    f"선택한 부분: {selected_text}" if selected_text else "",
                    f"관련 자료:\n{build_context(chunks, document_title)}",
                ])),
            },
        ],
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(f"{OPENAI_API_URL}/chat/completions", headers=headers, json=body)
        response.raise_for_status()
        data = response.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content")


async def create_ollama_tutor_answer(
    *,
    question: str,
    selected_text: str,
    chunks: list[dict[str, Any]],
    document_title: str,
    personalization_instructions: str,
) -> str | None:
    import httpx

    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    prompt = "\n".join(filter(None, [
        "너는 업로드된 학습 자료만 근거로 설명하는 AI 과외 선생님이다.",
        "자료에 없는 내용은 없다고 말한다.",
        "선택한 부분이 있으면 그 문맥을 우선해서 설명한다.",
        personalization_instructions,
        "",
        f"질문: {question}",
        f"선택한 부분: {selected_text}" if selected_text else "",
        "",
        f"관련 자료:\n{build_context(chunks, document_title)}",
    ]))
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{base_url}/api/generate",
            json={
                "model": os.getenv("OLLAMA_CHAT_MODEL", "gemma3:4b"),
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2},
            },
        )
        response.raise_for_status()
        data = response.json()
    return data.get("response")


def build_context(chunks: list[dict[str, Any]], document_title: str) -> str:
    blocks = []
    for index, chunk in enumerate(chunks, start=1):
        blocks.append("\n".join([
            f"[자료 {index}]",
            f"문서: {document_title}",
            f"섹션: {chunk.get('section_title') or ''}",
            f"내용: {chunk.get('content') or ''}",
        ]))
    return "\n\n".join(blocks)

