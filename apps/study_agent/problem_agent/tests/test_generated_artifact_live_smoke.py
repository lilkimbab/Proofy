import os

import pytest

from app.config import Settings
from app.services.generated_artifact_publisher import GeneratedArtifactPublisher


@pytest.mark.rag
def test_live_generated_artifact_index_accepts_problem_payload():
    if os.getenv("GENERATED_ARTIFACT_SMOKE_ENABLED", "").lower() != "true":
        pytest.skip("GENERATED_ARTIFACT_SMOKE_ENABLED=true is required for live artifact index smoke tests")
    index_url = os.getenv("GENERATED_ARTIFACT_INDEX_URL")
    add_url = os.getenv("GENERATED_ARTIFACT_ADD_URL")
    if not index_url and not add_url:
        pytest.skip("GENERATED_ARTIFACT_INDEX_URL or GENERATED_ARTIFACT_ADD_URL is required for live artifact smoke tests")

    user_id = os.getenv("GENERATED_ARTIFACT_SMOKE_USER_ID", "smoke_user_001")
    document_id = os.getenv("GENERATED_ARTIFACT_SMOKE_DOCUMENT_ID", "smoke_doc_001")
    chunk_id = os.getenv("GENERATED_ARTIFACT_SMOKE_CHUNK_ID", "smoke_chunk_001")
    publisher = GeneratedArtifactPublisher(
        Settings(
            DATABASE_URL="sqlite+pysqlite://",
            GENERATED_ARTIFACT_INDEX_URL=index_url,
            GENERATED_ARTIFACT_ADD_URL=add_url,
            GENERATED_ARTIFACT_PUBLISH_ENABLED=True,
            GENERATED_ARTIFACT_PUBLISH_FAIL_FAST=True,
            GENERATED_ARTIFACT_API_KEY=os.getenv("GENERATED_ARTIFACT_API_KEY") or None,
            GENERATED_ARTIFACT_API_KEY_HEADER=os.getenv("GENERATED_ARTIFACT_API_KEY_HEADER", "X-API-Key"),
            GENERATED_ARTIFACT_TIMEOUT_SECONDS=float(os.getenv("GENERATED_ARTIFACT_TIMEOUT_SECONDS", "3")),
        )
    )
    problem = type(
        "ProblemStub",
        (),
        {
            "id": os.getenv("GENERATED_ARTIFACT_SMOKE_PROBLEM_ID", "smoke_prob_001"),
            "user_id": user_id,
            "document_id": document_id,
            "question": "Smoke test problem for generated artifact indexing.",
            "choices": [{"id": "A", "text": "Smoke test choice"}],
            "type": "multiple_choice",
            "difficulty": "medium",
            "bloom_level": "understand",
            "concepts": ["smoke_concept"],
            "source_refs": [{"document_id": document_id, "chunk_id": chunk_id}],
            "quality_status": "passed",
            "item_model_id": "smoke_contract",
            "source_chunk_ids": [chunk_id],
            "created_at": None,
        },
    )()

    assert publisher.publish_problem(problem) is True
