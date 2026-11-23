import os

EXTERNAL_SERVICE_ENV_DEFAULTS = {
    "OPENAI_API_KEY": "",
    "GEMINI_API_KEY": "",
    "RAG_AGENT_URL": "",
    "SEARCH_AGENT_URL": "",
    "GENERATED_ARTIFACT_INDEX_URL": "",
    "GENERATED_ARTIFACT_ADD_URL": "",
    "GENERATED_ARTIFACT_PUBLISH_ENABLED": "false",
    "LLM_FALLBACK_ENABLED": "true",
    "DEMO_SEARCH_ENABLED": "false",
}
EXTERNAL_SERVICE_ENV_ORIGINALS = {
    key: os.environ.get(key)
    for key in EXTERNAL_SERVICE_ENV_DEFAULTS
}
LIVE_MARKERS = {"llm", "rag"}


def _apply_non_live_env_defaults() -> None:
    for key, value in EXTERNAL_SERVICE_ENV_DEFAULTS.items():
        os.environ[key] = value


def _restore_original_external_env() -> None:
    for key, value in EXTERNAL_SERVICE_ENV_ORIGINALS.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _is_live_test(node) -> bool:
    return any(node.get_closest_marker(marker) is not None for marker in LIVE_MARKERS)


_apply_non_live_env_defaults()

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db import Base
from app.services.search_service import RetrievedChunk


@pytest.fixture(autouse=True)
def isolate_external_service_env(monkeypatch, request):
    if _is_live_test(request.node):
        _restore_original_external_env()
    else:
        for key, value in EXTERNAL_SERVICE_ENV_DEFAULTS.items():
            monkeypatch.setenv(key, value)

    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


class FixedSearchService:
    chunks = [
        RetrievedChunk(
            chunk_id="chunk_001",
            document_id="doc_001",
            content="뉴턴의 제2법칙은 F = ma이다. 같은 힘이 작용할 때 질량이 클수록 가속도는 작아진다.",
            page=12,
            section_title="뉴턴의 운동 법칙",
            concepts=["뉴턴 제2법칙", "질량과 가속도"],
        )
    ]

    def search_chunks(self, **kwargs):
        return self.chunks

    def get_chunks_by_ids(self, **kwargs):
        return self.chunks


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def fixed_search():
    return FixedSearchService()


@pytest.fixture()
def anyio_backend():
    return "asyncio"
