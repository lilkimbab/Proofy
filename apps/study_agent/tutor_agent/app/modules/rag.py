from __future__ import annotations

import re
from typing import Any

from app.schemas.common import Source


def retrieve_relevant_chunks(
    *,
    document: dict[str, Any],
    question: str,
    selected_text: str = "",
    section_id: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    chunks = flatten_document_chunks(document)
    query_tokens = tokenize(" ".join([question, selected_text]))
    scored = []
    for chunk in chunks:
        content = " ".join([
            str(chunk.get("section_title") or ""),
            str(chunk.get("content") or ""),
        ])
        score = lexical_score(query_tokens, content)
        if section_id and chunk.get("section_id") == section_id:
            score += 0.2
        if selected_text and selected_text in str(chunk.get("content") or ""):
            score += 0.25
        scored.append({**chunk, "score": round(score, 4)})
    return sorted(scored, key=lambda item: item["score"], reverse=True)[:limit]


def flatten_document_chunks(document: dict[str, Any]) -> list[dict[str, Any]]:
    direct_chunks = document.get("chunks") or document.get("retrieved_chunks") or []
    if direct_chunks:
        return [normalize_chunk(chunk, index + 1) for index, chunk in enumerate(direct_chunks)]

    chunks: list[dict[str, Any]] = []
    for section_index, section in enumerate(document.get("sections") or [], start=1):
        section_chunks = section.get("chunks") or []
        if section_chunks:
            for chunk_index, chunk in enumerate(section_chunks, start=1):
                chunks.append(normalize_chunk({
                    **chunk,
                    "section_id": section.get("id"),
                    "section_title": section.get("title"),
                    "section_index": section.get("index") or section_index,
                }, chunk_index))
        else:
            content = str(section.get("content") or section.get("summary") or "")
            if content:
                chunks.append(normalize_chunk({
                    "id": f"{section.get('id') or f'section-{section_index}'}-chunk-1",
                    "section_id": section.get("id"),
                    "section_title": section.get("title"),
                    "section_index": section.get("index") or section_index,
                    "content": content,
                }, 1))
    return chunks


def normalize_chunk(chunk: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "id": chunk.get("id") or chunk.get("chunk_id") or chunk.get("chunkId") or f"chunk-{index}",
        "section_id": chunk.get("section_id") or chunk.get("sectionId"),
        "section_title": chunk.get("section_title") or chunk.get("sectionTitle") or chunk.get("title"),
        "section_index": chunk.get("section_index") or chunk.get("sectionIndex") or chunk.get("index"),
        "content": str(chunk.get("content") or ""),
        "score": float(chunk.get("score") or 0),
    }


def chunks_to_sources(chunks: list[dict[str, Any]]) -> list[Source]:
    return [
        Source(
            chunk_id=chunk.get("id"),
            section_id=chunk.get("section_id"),
            title=chunk.get("section_title"),
            index=chunk.get("section_index"),
            quote=build_quote(chunk.get("content")),
            score=float(chunk.get("score") or 0),
        )
        for chunk in chunks
    ]


def compose_local_answer(question: str, chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "업로드된 자료에서 관련 내용을 찾지 못했습니다. 질문을 조금 더 구체적으로 작성해보세요."
    source_summaries = []
    for chunk in chunks[:3]:
        title = chunk.get("section_title") or "관련 섹션"
        content = build_quote(chunk.get("content"), limit=260)
        source_summaries.append(f"{title}: {content}")
    return "\n\n".join([
        "자료에서 관련성이 높은 부분을 기준으로 설명할게요.",
        *source_summaries,
        "질문한 내용은 위 자료의 핵심 개념과 연결됩니다. 먼저 근거 문장을 확인하고 예시나 문제에 적용해보면 이해가 더 쉬워집니다.",
    ])


def build_quote(content: str | None, limit: int = 180) -> str:
    normalized = re.sub(r"\s+", " ", str(content or "")).strip()
    return f"{normalized[:limit]}..." if len(normalized) > limit else normalized


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.sub(r"[^\w가-힣\s]", " ", text.lower()).split()
        if len(token) > 1
    ]


def lexical_score(query_tokens: list[str], content: str) -> float:
    if not query_tokens:
        return 0
    content_tokens = set(tokenize(content))
    hits = sum(1 for token in query_tokens if token in content_tokens)
    return hits / len(query_tokens)

