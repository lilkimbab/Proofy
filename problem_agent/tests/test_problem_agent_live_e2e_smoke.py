import os

import pytest

from app.agents import FeedbackAgent, ProblemAgent, ProblemQualityChecker
from app.config import Settings
from app.schemas.problems import GenerateProblemRequest, SubmitAnswerRequest
from app.services.feedback_service import FeedbackService
from app.services.generated_artifact_publisher import GeneratedArtifactPublisher
from app.services.problem_service import ProblemService
from app.services.search_service import SearchService


@pytest.mark.rag
def test_live_rag_problem_feedback_artifact_e2e(db_session):
    _run_live_problem_feedback_artifact_e2e(db_session=db_session, use_openai=False)


@pytest.mark.llm
@pytest.mark.rag
def test_live_rag_openai_problem_feedback_artifact_e2e(db_session):
    if os.getenv("PROBLEM_AGENT_E2E_SMOKE_USE_OPENAI", "").lower() != "true":
        pytest.skip("PROBLEM_AGENT_E2E_SMOKE_USE_OPENAI=true is required for live RAG+OpenAI E2E smoke tests")
    _run_live_problem_feedback_artifact_e2e(db_session=db_session, use_openai=True)


def _run_live_problem_feedback_artifact_e2e(db_session, *, use_openai: bool):
    if os.getenv("PROBLEM_AGENT_E2E_SMOKE_ENABLED", "").lower() != "true":
        pytest.skip("PROBLEM_AGENT_E2E_SMOKE_ENABLED=true is required for live problem-agent E2E smoke tests")
    rag_agent_url = os.getenv("RAG_AGENT_URL")
    if not rag_agent_url:
        pytest.skip("RAG_AGENT_URL is required for live problem-agent E2E smoke tests")
    index_url = os.getenv("GENERATED_ARTIFACT_INDEX_URL")
    add_url = os.getenv("GENERATED_ARTIFACT_ADD_URL")
    if not index_url and not add_url:
        pytest.skip("GENERATED_ARTIFACT_INDEX_URL or GENERATED_ARTIFACT_ADD_URL is required for live problem-agent E2E smoke tests")

    user_id = os.getenv("PROBLEM_AGENT_E2E_SMOKE_USER_ID", "smoke_user_001")
    document_id = os.getenv("PROBLEM_AGENT_E2E_SMOKE_DOCUMENT_ID", "demo_doc")
    concept = os.getenv("PROBLEM_AGENT_E2E_SMOKE_CONCEPT", "핵심 개념")
    openai_api_key = os.getenv("OPENAI_API_KEY") if use_openai else None
    if use_openai and not openai_api_key:
        pytest.skip("OPENAI_API_KEY is required when PROBLEM_AGENT_E2E_SMOKE_USE_OPENAI=true")
    settings = Settings(
        DATABASE_URL="sqlite+pysqlite://",
        RAG_AGENT_URL=rag_agent_url,
        SEARCH_AGENT_URL=None,
        SEARCH_AGENT_API_KEY=os.getenv("SEARCH_AGENT_API_KEY") or None,
        SEARCH_AGENT_API_KEY_HEADER=os.getenv("SEARCH_AGENT_API_KEY_HEADER", "X-API-Key"),
        DEMO_SEARCH_ENABLED=False,
        OPENAI_API_KEY=openai_api_key,
        LLM_FALLBACK_ENABLED=not use_openai,
        PROBLEM_MODEL=os.getenv("OPENAI_SMOKE_PROBLEM_MODEL", "gpt-5.4-mini"),
        GRADING_MODEL=os.getenv("OPENAI_SMOKE_GRADING_MODEL", "gpt-5.4-mini"),
        LLM_MAX_OUTPUT_TOKENS_PROBLEM=1800,
        OPENAI_TIMEOUT_SECONDS=45,
        OPENAI_MAX_RETRIES=0,
        GENERATED_ARTIFACT_INDEX_URL=index_url,
        GENERATED_ARTIFACT_ADD_URL=add_url,
        GENERATED_ARTIFACT_PUBLISH_ENABLED=True,
        GENERATED_ARTIFACT_PUBLISH_FAIL_FAST=True,
        GENERATED_ARTIFACT_API_KEY=os.getenv("GENERATED_ARTIFACT_API_KEY") or None,
        GENERATED_ARTIFACT_API_KEY_HEADER=os.getenv("GENERATED_ARTIFACT_API_KEY_HEADER", "X-API-Key"),
        GENERATED_ARTIFACT_TIMEOUT_SECONDS=float(os.getenv("GENERATED_ARTIFACT_TIMEOUT_SECONDS", "3")),
    )
    search_service = SearchService(settings)
    artifact_publisher = GeneratedArtifactPublisher(settings)
    chunks = search_service.search_chunks(
        document_id=document_id,
        concepts=[concept],
        difficulty="medium",
        query=concept,
        top_k=3,
    )
    assert chunks, "RAG smoke preflight returned no chunks"
    assert all(chunk.document_id == document_id for chunk in chunks), "RAG smoke preflight returned wrong document chunks"
    assert all(chunk.chunk_id for chunk in chunks), "RAG smoke preflight returned chunks without chunk_id"
    assert all(chunk.content.strip() for chunk in chunks), "RAG smoke preflight returned empty chunk content"

    problem_service = ProblemService(
        db=db_session,
        search_service=search_service,
        problem_agent=ProblemAgent(settings=settings),
        quality_checker=ProblemQualityChecker(),
        artifact_publisher=artifact_publisher,
        settings=settings,
    )

    problems = problem_service.generate_problems(
        user_id=user_id,
        request=GenerateProblemRequest(
            document_id=document_id,
            concepts=[concept],
            type="multiple_choice",
            count=1,
        ),
    )
    problem = problems[0]
    feedback = FeedbackService(
        db=db_session,
        feedback_agent=FeedbackAgent(settings=settings),
        search_service=search_service,
        artifact_publisher=artifact_publisher,
    ).submit_answer(
        problem_id=problem.id,
        user_id=user_id,
        request=SubmitAnswerRequest(answer={"choice_id": problem.answer["choice_id"]}),
    )

    assert problem.document_id == document_id
    assert problem.source_chunk_ids
    assert feedback.problem_id == problem.id
    assert feedback.source_chunk_ids == problem.source_chunk_ids
