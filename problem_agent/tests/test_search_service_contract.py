import httpx
import pytest

from app.config import Settings
from app.services.search_service import SearchAgentError, SearchService


def make_settings(**overrides) -> Settings:
    values = {
        "DATABASE_URL": "sqlite+pysqlite://",
        "SEARCH_AGENT_API_KEY": None,
        **overrides,
    }
    return Settings(_env_file=None, **values)


def test_search_service_posts_search_contract(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout, **kwargs):
        captured["url"] = url
        captured["json"] = json
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json=[
                {
                    "chunk_id": "chunk_001",
                    "document_id": "doc_001",
                    "content": "뉴턴의 제2법칙은 F = ma이다.",
                    "page": 12,
                    "section_title": "뉴턴의 운동 법칙",
                    "concepts": ["뉴턴 제2법칙"],
                }
            ],
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            SEARCH_AGENT_URL="http://search-agent",
            DEMO_SEARCH_ENABLED=False,
        )
    )

    chunks = service.search_chunks(
        document_id="doc_001",
        concepts=["뉴턴 제2법칙"],
        difficulty="medium",
        query="뉴턴 제2법칙",
        top_k=6,
    )

    assert captured["url"] == "http://search-agent/search"
    assert captured["json"]["document_id"] == "doc_001"
    assert captured["json"]["top_k"] == 6
    assert chunks[0].chunk_id == "chunk_001"


def test_search_service_deduplicates_search_results(monkeypatch):
    def fake_post(url, json, timeout, **kwargs):
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json=[
                {
                    "chunk_id": "chunk_001",
                    "document_id": "doc_001",
                    "content": "첫 번째 검색 결과다.",
                },
                {
                    "chunk_id": "chunk_001",
                    "document_id": "doc_001",
                    "content": "중복 검색 결과다.",
                },
            ],
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            SEARCH_AGENT_URL="http://search-agent",
            DEMO_SEARCH_ENABLED=False,
        )
    )

    chunks = service.search_chunks(
        document_id="doc_001",
        concepts=["뉴턴 제2법칙"],
        difficulty="medium",
        query="뉴턴 제2법칙",
        top_k=6,
    )

    assert [chunk.chunk_id for chunk in chunks] == ["chunk_001"]
    assert chunks[0].content == "첫 번째 검색 결과다."


def test_search_service_rejects_wrong_document_search_results(monkeypatch):
    def fake_post(url, json, timeout, **kwargs):
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json=[
                {
                    "chunk_id": "chunk_wrong_doc",
                    "document_id": "other_doc",
                    "content": "다른 문서의 검색 결과다.",
                }
            ],
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            SEARCH_AGENT_URL="http://search-agent",
            DEMO_SEARCH_ENABLED=False,
        )
    )

    with pytest.raises(SearchAgentError, match="different document"):
        service.search_chunks(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            difficulty="medium",
            query="뉴턴 제2법칙",
            top_k=6,
        )


def test_search_service_can_send_auth_header(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout, headers=None):
        captured["headers"] = headers
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json=[
                {
                    "chunk_id": "chunk_001",
                    "document_id": "doc_001",
                    "content": "뉴턴의 제2법칙은 F = ma이다.",
                }
            ],
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            SEARCH_AGENT_URL="http://search-agent",
            SEARCH_AGENT_API_KEY="secret-key",
            SEARCH_AGENT_API_KEY_HEADER="X-Search-Key",
            DEMO_SEARCH_ENABLED=False,
        )
    )

    service.search_chunks(
        document_id="doc_001",
        concepts=["뉴턴 제2법칙"],
        difficulty="medium",
        query="뉴턴 제2법칙",
        top_k=6,
    )

    assert captured["headers"] == {"X-Search-Key": "secret-key"}


def test_search_service_chunk_batch_reorders_to_requested_chunk_ids(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout, **kwargs):
        captured["json"] = json
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json=[
                {
                    "chunk_id": "chunk_002",
                    "document_id": "doc_001",
                    "content": "두 번째로 요청한 chunk가 먼저 와도 된다.",
                },
                {
                    "chunk_id": "chunk_001",
                    "document_id": "doc_001",
                    "content": "첫 번째로 요청한 chunk다.",
                },
            ],
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            SEARCH_AGENT_URL="http://search-agent",
            DEMO_SEARCH_ENABLED=False,
        )
    )

    chunks = service.get_chunks_by_ids(
        document_id="doc_001",
        chunk_ids=["chunk_001", "chunk_002"],
    )

    assert captured["json"] == {
        "document_id": "doc_001",
        "chunk_ids": ["chunk_001", "chunk_002"],
    }
    assert [chunk.chunk_id for chunk in chunks] == ["chunk_001", "chunk_002"]


@pytest.mark.parametrize(
    ("response_json", "requested_chunk_ids", "error_match"),
    [
        (
            [
                {
                    "chunk_id": "chunk_001",
                    "document_id": "doc_001",
                    "content": "요청한 chunk다.",
                },
                {
                    "chunk_id": "chunk_extra",
                    "document_id": "doc_001",
                    "content": "요청하지 않은 chunk다.",
                },
            ],
            ["chunk_001"],
            "unexpected chunks",
        ),
        (
            [
                {
                    "chunk_id": "chunk_001",
                    "document_id": "doc_001",
                    "content": "첫 번째 chunk다.",
                },
                {
                    "chunk_id": "chunk_001",
                    "document_id": "doc_001",
                    "content": "중복 chunk다.",
                },
            ],
            ["chunk_001"],
            "duplicate chunks",
        ),
        (
            [
                {
                    "chunk_id": "chunk_001",
                    "document_id": "doc_001",
                    "content": "첫 번째 chunk만 반환됐다.",
                },
            ],
            ["chunk_001", "chunk_002"],
            "did not return chunks",
        ),
        (
            [
                {
                    "chunk_id": "chunk_001",
                    "document_id": "other_doc",
                    "content": "다른 문서의 chunk다.",
                },
            ],
            ["chunk_001"],
            "different document",
        ),
    ],
)
def test_search_service_chunk_batch_rejects_invalid_contract(
    monkeypatch,
    response_json,
    requested_chunk_ids,
    error_match,
):
    def fake_post(url, json, timeout, **kwargs):
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json=response_json)

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            SEARCH_AGENT_URL="http://search-agent",
            DEMO_SEARCH_ENABLED=False,
        )
    )

    with pytest.raises(SearchAgentError, match=error_match):
        service.get_chunks_by_ids(
            document_id="doc_001",
            chunk_ids=requested_chunk_ids,
        )


def test_search_service_wraps_http_errors(monkeypatch):
    def fake_post(url, json, timeout, **kwargs):
        raise httpx.ConnectError("connection failed")

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            SEARCH_AGENT_URL="http://search-agent",
            DEMO_SEARCH_ENABLED=False,
        )
    )

    with pytest.raises(SearchAgentError):
        service.search_chunks(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            difficulty="medium",
            query="뉴턴 제2법칙",
            top_k=6,
        )


def test_search_service_can_use_rag_agent_contract(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout, **kwargs):
        captured["url"] = url
        captured["json"] = json
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "results": [
                    {
                        "text": "뉴턴의 제2법칙은 $F = ma$로 표현된다.",
                        "source": "physics.pdf",
                        "page": 3,
                        "score": 0.91,
                        "image": None,
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            RAG_AGENT_URL="http://rag-agent",
            RAG_AGENT_FETCH_PATH=None,
            SEARCH_AGENT_URL=None,
            DEMO_SEARCH_ENABLED=False,
        )
    )

    chunks = service.search_chunks(
        document_id="physics_lecture",
        concepts=["뉴턴 제2법칙"],
        difficulty="hard",
        query="수식으로 푸는 뉴턴 제2법칙 문제",
        top_k=8,
    )

    assert captured["url"] == "http://rag-agent/search"
    assert captured["json"] == {
        "query": "수식으로 푸는 뉴턴 제2법칙 문제",
        "title": "physics_lecture",
        "top_k": 8,
        "filter": None,
    }
    assert chunks[0].chunk_id.startswith("rag_")
    assert chunks[0].document_id == "physics_lecture"
    assert chunks[0].content == "뉴턴의 제2법칙은 $F = ma$로 표현된다."
    assert chunks[0].section_title == "physics.pdf"
    assert chunks[0].concepts == ["뉴턴 제2법칙"]
    assert chunks[0].metadata["score"] == 0.91
    assert chunks[0].metadata["image_available"] is False

    cached_chunks = service.get_chunks_by_ids(
        document_id="physics_lecture",
        chunk_ids=[chunks[0].chunk_id],
    )
    assert cached_chunks == chunks


def test_rag_agent_adapter_prefers_parent_text_for_problem_generation(monkeypatch):
    def fake_post(url, json, timeout, **kwargs):
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "results": [
                    {
                        "id": "parent_chunk_001",
                        "text": "짧은 child chunk다.",
                        "parent_text": "문제 생성에는 문맥이 보존된 parent text를 우선 사용한다.",
                        "source": "lecture.md",
                        "page": 2,
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            RAG_AGENT_URL="http://rag-agent",
            RAG_AGENT_FETCH_PATH=None,
            SEARCH_AGENT_URL=None,
            DEMO_SEARCH_ENABLED=False,
        )
    )

    chunks = service.search_chunks(
        document_id="doc_001",
        concepts=["문맥 보존"],
        difficulty="medium",
        query="문맥 보존",
        top_k=1,
    )

    assert chunks[0].content == "문제 생성에는 문맥이 보존된 parent text를 우선 사용한다."
    assert chunks[0].metadata["rag_child_text"] == "짧은 child chunk다."


def test_rag_agent_adapter_can_preserve_image_payloads_and_ngrok_header(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout, headers=None):
        captured["headers"] = headers
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "results": [
                    {
                        "id": "diagram_chunk_001",
                        "text": "이 페이지에는 힘과 가속도 관계를 보여주는 다이어그램이 있다.",
                        "source": "physics.pdf",
                        "page": 4,
                        "score": 0.87,
                        "image": "iVBORw0KGgoAAAANSUhEUgAA",
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            RAG_AGENT_URL="https://example.ngrok-free.dev",
            RAG_AGENT_TEXT_ONLY=False,
            RAG_AGENT_SKIP_NGROK_WARNING=True,
            RAG_AGENT_PRESERVE_IMAGE_PAYLOADS=True,
            SEARCH_AGENT_URL=None,
            DEMO_SEARCH_ENABLED=False,
        )
    )

    chunks = service.search_chunks(
        document_id="physics_lecture",
        concepts=["뉴턴 제2법칙"],
        difficulty="medium",
        query="힘과 가속도 다이어그램",
        top_k=1,
    )

    assert captured["headers"] == {"ngrok-skip-browser-warning": "true"}
    assert chunks[0].metadata["score"] == 0.87
    assert chunks[0].metadata["image_available"] is True
    assert chunks[0].metadata["image"] == "iVBORw0KGgoAAAANSUhEUgAA"


def test_rag_agent_adapter_defaults_to_text_only_even_when_image_is_returned(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout, headers):
        captured["headers"] = headers
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "results": [
                    {
                        "id": "diagram_chunk_001",
                        "text": "이미지가 있어도 문제 생성에는 텍스트만 사용한다.",
                        "source": "physics.pdf",
                        "page": 4,
                        "score": 0.87,
                        "image": "iVBORw0KGgoAAAANSUhEUgAA",
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            RAG_AGENT_URL="https://example.ngrok-free.dev",
            RAG_AGENT_PRESERVE_IMAGE_PAYLOADS=True,
            SEARCH_AGENT_URL=None,
            DEMO_SEARCH_ENABLED=False,
        )
    )

    chunks = service.search_chunks(
        document_id="physics_lecture",
        concepts=["뉴턴 제2법칙"],
        difficulty="medium",
        query="힘과 가속도 다이어그램",
        top_k=1,
    )

    assert captured["headers"] == {"X-RAG-Text-Only": "true"}
    assert chunks[0].metadata["image_available"] is True
    assert chunks[0].metadata["image_omitted"] == "text_only"
    assert "image" not in chunks[0].metadata


def test_rag_agent_adapter_can_include_images_for_visual_generation(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout, headers=None):
        captured["headers"] = headers
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "results": [
                    {
                        "id": "diagram_chunk_001",
                        "text": "힙 트리 그림을 보고 heapify 결과를 판단한다.",
                        "source": "heapsort.pdf",
                        "page": 6,
                        "score": 0.91,
                        "image": "iVBORw0KGgoAAAANSUhEUgAA",
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            RAG_AGENT_URL="http://rag-agent",
            SEARCH_AGENT_URL=None,
            DEMO_SEARCH_ENABLED=False,
        )
    )

    chunks = service.search_chunks(
        document_id="heapsort",
        concepts=["힙 정렬"],
        difficulty="medium",
        query="힙 트리 그림",
        top_k=1,
        include_images=True,
    )

    assert captured["headers"] is None
    assert chunks[0].metadata["image_available"] is True
    assert chunks[0].metadata["image"] == "iVBORw0KGgoAAAANSUhEUgAA"


def test_rag_agent_adapter_can_send_auth_header(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout, headers):
        captured["headers"] = headers
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={"results": [{"id": "chunk_001", "text": "인증이 필요한 RAG 검색 결과"}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            RAG_AGENT_URL="http://rag-agent",
            SEARCH_AGENT_URL=None,
            SEARCH_AGENT_API_KEY="secret-key",
            SEARCH_AGENT_API_KEY_HEADER="X-RAG-Key",
            DEMO_SEARCH_ENABLED=False,
        )
    )

    service.search_chunks(
        document_id="doc_001",
        concepts=["개념"],
        difficulty="medium",
        query="개념",
        top_k=1,
    )

    assert captured["headers"] == {"X-RAG-Key": "secret-key", "X-RAG-Text-Only": "true"}


def test_rag_agent_adapter_accepts_flexible_result_shapes(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout, **kwargs):
        captured["json"] = json
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "documents": [
                    {
                        "id": "kim_chunk_001",
                        "content": "수요가 증가하면 가격 상승 압력이 생긴다.",
                        "metadata": {
                            "document_id": "econ_lecture",
                            "section_title": "수요와 가격",
                            "page_number": "7",
                            "concepts": ["수요", "가격"],
                        },
                    },
                    {
                        "id": "kim_chunk_001",
                        "content": "중복 chunk는 첫 번째 결과만 사용한다.",
                        "metadata": {"document_id": "econ_lecture"},
                    },
                    {
                        "node_id": "kim_chunk_002",
                        "page_content": "공급이 일정하면 수요 증가는 균형 가격을 높인다.",
                        "metadata": {
                            "document_id": "econ_lecture",
                            "source": "경제학 강의노트",
                            "page": 8,
                        },
                    },
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            RAG_AGENT_URL="http://rag-agent",
            RAG_AGENT_FETCH_PATH=None,
            SEARCH_AGENT_URL=None,
            DEMO_SEARCH_ENABLED=False,
        )
    )

    chunks = service.search_chunks(
        document_id="econ_lecture",
        concepts=["시장 균형"],
        difficulty="medium",
        query="수요와 가격",
        top_k=5,
    )

    assert captured["json"]["title"] == "econ_lecture"
    assert [chunk.chunk_id for chunk in chunks] == ["kim_chunk_001", "kim_chunk_002"]
    assert chunks[0].content == "수요가 증가하면 가격 상승 압력이 생긴다."
    assert chunks[0].page == 7
    assert chunks[0].section_title == "수요와 가격"
    assert chunks[0].concepts == ["수요", "가격"]
    assert chunks[1].section_title == "경제학 강의노트"
    assert chunks[1].concepts == ["시장 균형"]


def test_rag_agent_adapter_accepts_matches_and_nested_document(monkeypatch):
    def fake_post(url, json, timeout, **kwargs):
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "matches": [
                    {
                        "chunk_id": "nested_chunk_001",
                        "document": {
                            "page_content": "한계비용이 한계수입보다 작으면 생산량을 늘릴 유인이 있다.",
                        },
                        "metadata": {
                            "document_id": "micro_lecture",
                            "source": "생산자 이론",
                            "page": 11,
                        },
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            RAG_AGENT_URL="http://rag-agent",
            SEARCH_AGENT_URL=None,
            DEMO_SEARCH_ENABLED=False,
        )
    )

    chunks = service.search_chunks(
        document_id="micro_lecture",
        concepts=["한계비용", "한계수입"],
        difficulty="hard",
        query="생산량 결정",
        top_k=3,
    )

    assert chunks[0].chunk_id == "nested_chunk_001"
    assert chunks[0].content == "한계비용이 한계수입보다 작으면 생산량을 늘릴 유인이 있다."
    assert chunks[0].section_title == "생산자 이론"
    assert chunks[0].page == 11


@pytest.mark.parametrize("container_key", ["chunks", "data", "contexts", "nodes"])
def test_rag_agent_adapter_accepts_declared_result_container_aliases(monkeypatch, container_key):
    def fake_post(url, json, timeout, **kwargs):
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={
                container_key: [
                    {
                        "id": f"{container_key}_chunk_001",
                        "content": "자료 chunk 컨테이너 이름이 달라도 RetrievedChunk로 변환한다.",
                        "metadata": {"document_id": "doc_001"},
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            RAG_AGENT_URL="http://rag-agent",
            SEARCH_AGENT_URL=None,
            DEMO_SEARCH_ENABLED=False,
        )
    )

    chunks = service.search_chunks(
        document_id="doc_001",
        concepts=["검색 계약"],
        difficulty="medium",
        query="검색 계약",
        top_k=3,
    )

    assert chunks[0].chunk_id == f"{container_key}_chunk_001"
    assert chunks[0].content == "자료 chunk 컨테이너 이름이 달라도 RetrievedChunk로 변환한다."


def test_rag_agent_adapter_can_use_configured_paths_and_chunk_batch(monkeypatch):
    captured = []

    def fake_post(url, json, timeout, **kwargs):
        captured.append({"url": url, "json": json})
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "items": [
                    {
                        "id": "chunk_batch_001",
                        "content": "검색된 chunk를 batch endpoint로 다시 가져올 수 있다.",
                        "metadata": {"document_id": "doc_001", "page": 2},
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            RAG_AGENT_URL="http://rag-agent",
            RAG_AGENT_SEARCH_PATH="/rag/search",
            RAG_AGENT_CHUNKS_PATH="/rag/chunks/batch",
            SEARCH_AGENT_URL=None,
            DEMO_SEARCH_ENABLED=False,
        )
    )

    chunks = service.search_chunks(
        document_id="doc_001",
        concepts=["검색"],
        difficulty="medium",
        query="batch 조회",
        top_k=1,
    )
    batch_chunks = service.get_chunks_by_ids(document_id="doc_001", chunk_ids=["chunk_batch_001"])

    assert captured[0]["url"] == "http://rag-agent/rag/search"
    assert captured[1]["url"] == "http://rag-agent/rag/chunks/batch"
    assert captured[1]["json"] == {
        "document_id": "doc_001",
        "title": "doc_001",
        "chunk_ids": ["chunk_batch_001"],
    }
    assert chunks[0].chunk_id == "chunk_batch_001"
    assert batch_chunks[0].content == "검색된 chunk를 batch endpoint로 다시 가져올 수 있다."


def test_rag_agent_adapter_can_use_fetch_as_chunk_batch_fallback(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout, **kwargs):
        captured["url"] = url
        captured["json"] = json
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "results": [
                    {
                        "id": "chunk_002",
                        "parent_text": "두 번째 chunk다.",
                        "metadata": {"document_id": "doc_001", "page": 3},
                    },
                    {
                        "id": "chunk_001",
                        "parent_text": "첫 번째 chunk다.",
                        "metadata": {"document_id": "doc_001", "page": 2},
                    },
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            RAG_AGENT_URL="http://rag-agent",
            RAG_AGENT_CHUNKS_PATH=None,
            RAG_AGENT_FETCH_PATH="/fetch",
            SEARCH_AGENT_URL=None,
            DEMO_SEARCH_ENABLED=False,
        )
    )

    chunks = service.get_chunks_by_ids(document_id="doc_001", chunk_ids=["chunk_001", "chunk_002"])

    assert captured["url"] == "http://rag-agent/fetch"
    assert captured["json"] == {
        "title": "doc_001",
        "filter": {"id": ["chunk_001", "chunk_002"]},
        "limit": 2,
    }
    assert [chunk.chunk_id for chunk in chunks] == ["chunk_001", "chunk_002"]
    assert chunks[0].content == "첫 번째 chunk다."


def test_rag_agent_chunk_batch_rejects_unexpected_chunk_ids(monkeypatch):
    def fake_post(url, json, timeout, **kwargs):
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "items": [
                    {
                        "id": "chunk_001",
                        "content": "요청한 chunk다.",
                        "metadata": {"document_id": "doc_001"},
                    },
                    {
                        "id": "chunk_extra",
                        "content": "요청하지 않은 chunk다.",
                        "metadata": {"document_id": "doc_001"},
                    },
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            RAG_AGENT_URL="http://rag-agent",
            RAG_AGENT_CHUNKS_PATH="/rag/chunks/batch",
            SEARCH_AGENT_URL=None,
            DEMO_SEARCH_ENABLED=False,
        )
    )

    with pytest.raises(SearchAgentError, match="unexpected chunks"):
        service.get_chunks_by_ids(document_id="doc_001", chunk_ids=["chunk_001"])


def test_rag_agent_chunk_batch_rejects_duplicate_chunk_ids(monkeypatch):
    def fake_post(url, json, timeout, **kwargs):
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "items": [
                    {
                        "id": "chunk_001",
                        "content": "첫 번째 chunk다.",
                        "metadata": {"document_id": "doc_001"},
                    },
                    {
                        "id": "chunk_001",
                        "content": "중복 chunk다.",
                        "metadata": {"document_id": "doc_001"},
                    },
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            RAG_AGENT_URL="http://rag-agent",
            RAG_AGENT_CHUNKS_PATH="/rag/chunks/batch",
            SEARCH_AGENT_URL=None,
            DEMO_SEARCH_ENABLED=False,
        )
    )

    with pytest.raises(SearchAgentError, match="duplicate chunks"):
        service.get_chunks_by_ids(document_id="doc_001", chunk_ids=["chunk_001"])


def test_rag_agent_adapter_rejects_wrong_document_result(monkeypatch):
    def fake_post(url, json, timeout, **kwargs):
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "results": [
                    {
                        "text": "다른 문서의 내용",
                        "source": "other.pdf",
                        "document_id": "other_doc",
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            RAG_AGENT_URL="http://rag-agent",
            RAG_AGENT_FETCH_PATH=None,
            SEARCH_AGENT_URL=None,
            DEMO_SEARCH_ENABLED=False,
        )
    )

    with pytest.raises(SearchAgentError, match="different document"):
        service.search_chunks(
            document_id="doc_001",
            concepts=["개념"],
            difficulty="medium",
            query="개념",
            top_k=3,
        )


def test_rag_agent_adapter_rejects_empty_result_list(monkeypatch):
    def fake_post(url, json, timeout, **kwargs):
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json={"results": []})

    monkeypatch.setattr(httpx, "post", fake_post)
    service = SearchService(
        make_settings(
            RAG_AGENT_URL="http://rag-agent",
            SEARCH_AGENT_URL=None,
            DEMO_SEARCH_ENABLED=False,
        )
    )

    with pytest.raises(SearchAgentError, match="no results"):
        service.search_chunks(
            document_id="doc_001",
            concepts=["개념"],
            difficulty="medium",
            query="개념",
            top_k=3,
        )


def test_rag_agent_adapter_rejects_uncached_chunk_batch():
    service = SearchService(
        make_settings(
            RAG_AGENT_URL="http://rag-agent",
            RAG_AGENT_FETCH_PATH=None,
            SEARCH_AGENT_URL=None,
            DEMO_SEARCH_ENABLED=False,
        )
    )

    with pytest.raises(SearchAgentError, match="uncached chunk ids"):
        service.get_chunks_by_ids(
            document_id="physics_lecture",
            chunk_ids=["rag_not_cached"],
        )


def test_demo_search_chunks_follow_requested_document_and_concepts():
    service = SearchService(
        make_settings(
            SEARCH_AGENT_URL=None,
            DEMO_SEARCH_ENABLED=True,
        )
    )

    chunks = service.search_chunks(
        document_id="doc_custom",
        concepts=["계약의 성립"],
        difficulty="medium",
        query="계약의 성립",
        top_k=6,
    )
    batch_chunks = service.get_chunks_by_ids(
        document_id="doc_custom",
        chunk_ids=[chunks[0].chunk_id],
    )

    assert chunks[0].document_id == "doc_custom"
    assert chunks[0].concepts == ["계약의 성립"]
    assert batch_chunks[0].document_id == "doc_custom"
