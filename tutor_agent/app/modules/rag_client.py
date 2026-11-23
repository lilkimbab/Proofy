"""RAG Agent 연동 모듈. document_id와 질문으로 관련 청크를 검색한다."""
from __future__ import annotations

import os
from typing import Any

import httpx

_RAG_URL = os.getenv("RAG_AGENT_URL", "http://localhost:8000/api/rag")
_TIMEOUT = float(os.getenv("RAG_TIMEOUT", "30"))


async def fetch_chunks(*, document_id: str, question: str, top_k: int = 6) -> list[dict[str, Any]]:
    """RAG /search를 호출해 관련 청크 목록을 반환한다. 실패하면 빈 리스트."""
    url = f"{_RAG_URL.rstrip('/')}/search"
    payload = {"query": question, "title": document_id, "top_k": top_k}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            results = resp.json().get("results", [])
        return [
            {
                "id": r.get("id") or r.get("chunk_id", ""),
                "content": r.get("parent_text") or r.get("content", ""),
                "section_title": (r.get("heading_path") or [""])[0] if r.get("heading_path") else "",
                "score": r.get("score", 0.0),
            }
            for r in results
        ]
    except Exception:
        return []
