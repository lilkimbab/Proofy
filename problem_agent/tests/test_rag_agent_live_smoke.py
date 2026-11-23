import os

import pytest

from app.config import Settings
from app.services.search_service import SearchService


@pytest.mark.rag
def test_live_rag_agent_search_contract_returns_problem_ready_chunks():
    rag_agent_url = os.getenv("RAG_AGENT_URL")
    if not rag_agent_url:
        pytest.skip("RAG_AGENT_URL is required for live RAG smoke tests")

    document_id = os.getenv("RAG_SMOKE_DOCUMENT_ID", "demo_doc")
    query = os.getenv("RAG_SMOKE_QUERY", "핵심 개념을 문제로 만들 수 있는 문단을 찾아줘")
    concept = os.getenv("RAG_SMOKE_CONCEPT", "핵심 개념")
    service = SearchService(
        Settings(
            RAG_AGENT_URL=rag_agent_url,
            SEARCH_AGENT_URL=None,
            SEARCH_AGENT_API_KEY=os.getenv("SEARCH_AGENT_API_KEY") or None,
            SEARCH_AGENT_API_KEY_HEADER=os.getenv("SEARCH_AGENT_API_KEY_HEADER", "X-API-Key"),
            DEMO_SEARCH_ENABLED=False,
        )
    )

    chunks = service.search_chunks(
        document_id=document_id,
        concepts=[concept],
        difficulty="medium",
        query=query,
        top_k=3,
    )

    assert chunks
    assert all(chunk.document_id == document_id for chunk in chunks)
    assert all(chunk.chunk_id for chunk in chunks)
    assert all(chunk.content.strip() for chunk in chunks)
