import pytest
from httpx import ASGITransport, AsyncClient

from app.db import get_db
from app.dependencies import get_search_service
from app.main import create_app
from app.schemas.integration_contracts import RetrievedChunk
from app.services.search_service import SearchAgentError


class BrokenSearchService:
    def search_chunks(self, **kwargs):
        raise SearchAgentError("Search Agent unavailable")

    def get_chunks_by_ids(self, **kwargs):
        raise SearchAgentError("Search Agent unavailable")


@pytest.mark.anyio
async def test_generate_problem_returns_503_when_search_agent_fails(db_session):
    app = create_app(auto_create_tables=False)

    async def override_get_db():
        yield db_session

    async def override_search_service():
        return BrokenSearchService()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_search_service] = override_search_service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/problems/generate",
            headers={"X-User-Id": "user_001"},
            json={
                "document_id": "doc_001",
                "concepts": ["뉴턴 제2법칙"],
                "type": "multiple_choice",
                "count": 1,
            },
        )

    assert response.status_code == 503
    assert "Search Agent unavailable" in response.json()["detail"]


@pytest.mark.anyio
async def test_generate_problem_returns_503_when_search_agent_returns_wrong_document(db_session):
    app = create_app(auto_create_tables=False)

    async def override_get_db():
        yield db_session

    async def override_search_service():
        class Service:
            def search_chunks(self, **kwargs):
                return [
                    RetrievedChunk(
                        chunk_id="chunk_wrong_doc",
                        document_id="other_doc",
                        content="다른 문서의 내용이다.",
                        page=1,
                        section_title="다른 문서",
                        concepts=["다른 개념"],
                    )
                ]

            def get_chunks_by_ids(self, **kwargs):
                return []

        return Service()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_search_service] = override_search_service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/problems/generate",
            headers={"X-User-Id": "user_001"},
            json={
                "document_id": "doc_001",
                "concepts": ["뉴턴 제2법칙"],
                "type": "multiple_choice",
                "count": 1,
            },
        )

    assert response.status_code == 503
    assert "different document" in response.json()["detail"]
