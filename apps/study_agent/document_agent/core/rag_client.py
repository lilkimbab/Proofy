import os

import httpx
from dotenv import load_dotenv

load_dotenv()

_RAG_URL = os.getenv("RAG_AGENT_URL", "http://localhost:8000")
_TIMEOUT = float(os.getenv("RAG_TIMEOUT", "30"))


async def add(file_path: str, title: str) -> dict:
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    file_name = os.path.basename(file_path)
    async with httpx.AsyncClient(timeout=_TIMEOUT * 10) as client:
        r = await client.post(
            f"{_RAG_URL}/add",
            data={"title": title},
            files={"file": (file_name, file_bytes)},
        )
        r.raise_for_status()
        result = r.json()
        # 업데이트된 rag_agent는 ParseParent.source로 파일명을 반환하므로 file_name으로 정규화
        for p in result.get("parents", []):
            if "file_name" not in p and "source" in p:
                p["file_name"] = p["source"]
        return result


async def search(
    query: str,
    title: str,
    top_k: int = 10,
    user_id: str | None = None,
) -> list[dict]:
    payload: dict = {"query": query, "title": title, "top_k": top_k}
    if user_id:
        payload["user_id"] = user_id
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.post(f"{_RAG_URL}/search", json=payload)
        r.raise_for_status()
        results = r.json()["results"]
        # 업데이트된 rag_agent는 SearchResult.text를 직렬화에서 제외하고 parent_text로 대체
        for chunk in results:
            if not chunk.get("text") and chunk.get("parent_text"):
                chunk["text"] = chunk["parent_text"]
        return results


async def send_feedback(user_id: str, title: str, chunk_id: str, kind: str = "useful") -> None:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        await client.post(
            f"{_RAG_URL}/feedback",
            json={"user_id": user_id, "title": title, "chunk_id": chunk_id, "kind": kind},
        )


async def get_titles() -> list[str]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.get(f"{_RAG_URL}/titles")
        r.raise_for_status()
        return r.json()["titles"]
