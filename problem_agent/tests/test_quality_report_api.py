import pytest
from httpx import ASGITransport, AsyncClient

from app.db import get_db
from app.dependencies import get_learning_content_repository, get_search_service
from app.main import create_app
from app.models import ProblemRegenerationCandidate, UserQualityReport
from app.repositories.learning_content_repository import LearningContentRepository
from app.schemas.learning_contents import LearningContentBase


def _learning_content() -> LearningContentBase:
    return LearningContentBase(
        document_id="doc_001",
        content_type="flashcard",
        concepts=["뉴턴 제2법칙"],
        source_chunk_ids=["chunk_001"],
        quality_status="passed",
        quality_report={"status": "passed", "score": 0.9},
        payload={
            "front": "뉴턴 제2법칙의 식은 무엇일까요?",
            "back": "$F=ma$",
            "explanation": "힘은 질량과 가속도의 곱으로 표현해요.",
        },
    )


def _app_with_overrides(db_session, fixed_search, learning_content_repository=None):
    app = create_app(auto_create_tables=False)

    async def override_get_db():
        yield db_session

    async def override_search_service():
        return fixed_search

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_search_service] = override_search_service

    if learning_content_repository is not None:
        async def override_learning_content_repository():
            return learning_content_repository

        app.dependency_overrides[get_learning_content_repository] = override_learning_content_repository

    return app


@pytest.mark.anyio
async def test_quality_report_api_stores_problem_report_and_creates_review_candidate(db_session, fixed_search):
    app = _app_with_overrides(db_session, fixed_search)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        generated = await client.post(
            "/api/problems/generate",
            headers={"X-User-Id": "user_001"},
            json={
                "document_id": "doc_001",
                "concepts": ["뉴턴 제2법칙"],
                "type": "multiple_choice",
                "count": 1,
            },
        )
        problem_id = generated.json()["problems"][0]["id"]

        response = await client.post(
            "/api/quality-reports",
            headers={"X-User-Id": "user_001"},
            json={
                "target_type": "problem",
                "target_id": problem_id,
                "reason": "answer_wrong",
                "message": "정답 근거가 이상해 보여요.",
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["target_type"] == "problem"
    assert body["target_id"] == problem_id
    assert body["reason"] == "answer_wrong"
    assert body["status"] == "open"

    report = db_session.query(UserQualityReport).one()
    assert report.user_id == "user_001"
    candidate = db_session.query(ProblemRegenerationCandidate).one()
    assert candidate.problem_id == problem_id
    assert "quality_report:answer_wrong" in candidate.trigger_reasons
    assert candidate.suggested_action == "check_ambiguity_or_source_grounding"
    assert candidate.source_metrics["quality_report_id"] == report.id


@pytest.mark.anyio
async def test_quality_report_api_rejects_inaccessible_problem(db_session, fixed_search):
    app = _app_with_overrides(db_session, fixed_search)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        generated = await client.post(
            "/api/problems/generate",
            headers={"X-User-Id": "owner_user"},
            json={
                "document_id": "doc_001",
                "concepts": ["뉴턴 제2법칙"],
                "type": "multiple_choice",
                "count": 1,
            },
        )
        problem_id = generated.json()["problems"][0]["id"]

        response = await client.post(
            "/api/quality-reports",
            headers={"X-User-Id": "other_user"},
            json={
                "target_type": "problem",
                "target_id": problem_id,
                "reason": "not_grounded",
            },
        )

    assert response.status_code == 404
    assert db_session.query(UserQualityReport).count() == 0
    assert db_session.query(ProblemRegenerationCandidate).count() == 0


@pytest.mark.anyio
async def test_quality_report_api_stores_feedback_tone_report_without_regeneration_candidate(db_session, fixed_search):
    app = _app_with_overrides(db_session, fixed_search)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        generated = await client.post(
            "/api/problems/generate",
            headers={"X-User-Id": "user_001"},
            json={
                "document_id": "doc_001",
                "concepts": ["뉴턴 제2법칙"],
                "type": "multiple_choice",
                "count": 1,
            },
        )
        problem_id = generated.json()["problems"][0]["id"]
        submitted = await client.post(
            f"/api/problems/{problem_id}/submit",
            headers={"X-User-Id": "user_001"},
            json={"answer": {"choice_id": "C", "text": "C"}},
        )
        feedback_id = submitted.json()["id"]

        response = await client.post(
            "/api/quality-reports",
            headers={"X-User-Id": "user_001"},
            json={
                "target_type": "feedback",
                "target_id": feedback_id,
                "reason": "tone_awkward",
                "message": "말투가 조금 어색해요.",
            },
        )

    assert response.status_code == 201
    assert response.json()["target_type"] == "feedback"
    assert db_session.query(UserQualityReport).count() == 1
    assert db_session.query(ProblemRegenerationCandidate).count() == 0


@pytest.mark.anyio
async def test_quality_report_api_adds_grading_context_for_feedback_report(db_session, fixed_search):
    app = _app_with_overrides(db_session, fixed_search)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        generated = await client.post(
            "/api/problems/generate",
            headers={"X-User-Id": "user_001"},
            json={
                "document_id": "doc_001",
                "concepts": ["뉴턴 제2법칙"],
                "type": "short_answer",
                "count": 1,
            },
        )
        problem_id = generated.json()["problems"][0]["id"]
        submitted = await client.post(
            f"/api/problems/{problem_id}/submit",
            headers={"X-User-Id": "user_001"},
            json={
                "answer": {
                    "input_mode": "tablet_ocr",
                    "ocr_text": "뉴턴 제2법칙은 힘과 질량의 관계를 설명한다.",
                    "ocr_confidence": 0.42,
                    "tablet_image_url": "https://example.test/submission.png",
                }
            },
        )
        feedback_id = submitted.json()["id"]

        response = await client.post(
            "/api/quality-reports",
            headers={"X-User-Id": "user_001"},
            json={
                "target_type": "feedback",
                "target_id": feedback_id,
                "reason": "grading_unfair",
                "message": "OCR 때문에 rubric 채점이 애매해 보여요.",
            },
        )

    assert response.status_code == 201
    candidate = db_session.query(ProblemRegenerationCandidate).one()
    assert candidate.problem_id == problem_id
    assert candidate.suggested_action == "revise_rubric_or_prompt"
    assert "quality_report:grading_unfair" in candidate.trigger_reasons
    assert candidate.source_metrics["quality_report_target_id"] == feedback_id
    assert candidate.source_metrics["reported_feedback_id"] == feedback_id
    assert candidate.source_metrics["reported_feedback_evaluation_confidence"] == "low"
    assert candidate.source_metrics["reported_feedback_needs_grading_review"] is True
    assert candidate.source_metrics["reported_feedback_grading_review_reasons"]
    assert candidate.source_metrics["reported_feedback_rubric_criteria_count"] > 0
    assert candidate.source_metrics["reported_feedback_low_confidence_criteria"]


@pytest.mark.anyio
async def test_quality_report_api_accepts_owned_learning_content(db_session, fixed_search):
    repository = LearningContentRepository()
    saved_content = repository.create_many(user_id="user_001", contents=[_learning_content()])[0]
    app = _app_with_overrides(db_session, fixed_search, learning_content_repository=repository)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/quality-reports",
            headers={"X-User-Id": "user_001"},
            json={
                "target_type": "learning_content",
                "target_id": saved_content.id,
                "reason": "explanation_unclear",
            },
        )

    assert response.status_code == 201
    assert response.json()["target_type"] == "learning_content"
    assert db_session.query(UserQualityReport).count() == 1
    assert db_session.query(ProblemRegenerationCandidate).count() == 0
