import pytest
from httpx import ASGITransport, AsyncClient

from app.db import get_db
from app.dependencies import get_search_service
from app.main import create_app
from app.models import ProblemRegenerationCandidate, ProblemTemplateAnalytics
from app.schemas.problems import GenerateProblemRequest, SubmitAnswerRequest
from app.services.feedback_service import FeedbackService
from app.services.problem_service import ProblemService
from app.agents import FeedbackAgent, ProblemAgent, ProblemQualityChecker


def _problem_service(db_session, fixed_search) -> ProblemService:
    return ProblemService(
        db=db_session,
        search_service=fixed_search,
        problem_agent=ProblemAgent(),
        quality_checker=ProblemQualityChecker(),
    )


def _feedback_service(db_session, fixed_search) -> FeedbackService:
    return FeedbackService(
        db=db_session,
        feedback_agent=FeedbackAgent(),
        search_service=fixed_search,
    )


def _wrong_choice_id(problem) -> str:
    for diagnostic in problem.choice_diagnostics or []:
        if not diagnostic["is_correct"]:
            return diagnostic["choice_id"]
    raise AssertionError("Expected an incorrect choice diagnostic")


def test_template_analytics_groups_same_item_model_concept_and_difficulty(db_session, fixed_search):
    problem_service = _problem_service(db_session, fixed_search)
    feedback_service = _feedback_service(db_session, fixed_search)
    problems = problem_service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=2,
        ),
    )

    feedback_service.submit_answer(
        problem_id=problems[0].id,
        user_id="user_001",
        request=SubmitAnswerRequest(
            answer={"choice_id": _wrong_choice_id(problems[0]), "text": _wrong_choice_id(problems[0])},
            hint_count=1,
        ),
    )
    feedback_service.submit_answer(
        problem_id=problems[1].id,
        user_id="user_001",
        request=SubmitAnswerRequest(
            answer={
                "choice_id": problems[1].answer["choice_id"],
                "text": problems[1].answer["choice_id"],
            },
        ),
    )

    analytics = db_session.query(ProblemTemplateAnalytics).one()
    assert analytics.user_id == "user_001"
    assert analytics.document_id == "doc_001"
    assert analytics.item_model_id == problems[0].item_model_id
    assert analytics.concept == "뉴턴 제2법칙"
    assert analytics.problem_type == "multiple_choice"
    assert analytics.problem_count == 2
    assert set(analytics.problem_ids) == {problems[0].id, problems[1].id}
    assert analytics.total_attempts == 2
    assert analytics.correct_count == 1
    assert analytics.incorrect_count == 1
    assert analytics.correct_rate == 0.5
    assert analytics.correct_rate_smoothed == 0.5
    assert analytics.hint_usage_count == 1
    assert analytics.hint_usage_rate == 0.5
    assert analytics.sample_size_status == "insufficient"
    assert analytics.statistics_confidence == "low"
    assert analytics.quality_score_source == "template_item_quality"
    assert analytics.item_quality_average is not None


def test_template_analytics_marks_repeated_low_correct_template_for_review(db_session, fixed_search):
    problem_service = _problem_service(db_session, fixed_search)
    feedback_service = _feedback_service(db_session, fixed_search)
    problems = problem_service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=5,
        ),
    )

    for problem in problems:
        wrong_choice_id = _wrong_choice_id(problem)
        feedback_service.submit_answer(
            problem_id=problem.id,
            user_id="user_001",
            request=SubmitAnswerRequest(answer={"choice_id": wrong_choice_id, "text": wrong_choice_id}),
        )

    analytics = db_session.query(ProblemTemplateAnalytics).one()
    assert analytics.total_attempts == 5
    assert analytics.correct_rate == 0
    assert analytics.correct_rate_smoothed == pytest.approx(0.143)
    assert analytics.sample_size_status == "warming_up"
    assert analytics.statistics_confidence == "medium"
    assert analytics.needs_review is True
    assert "template_very_low_correct_rate" in analytics.review_reasons
    assert "repeated_template_mistake_type" in analytics.review_reasons
    candidates = db_session.query(ProblemRegenerationCandidate).all()
    assert candidates
    assert any("template:template_very_low_correct_rate" in candidate.trigger_reasons for candidate in candidates)
    assert any(candidate.suggested_action == "check_ambiguity_or_source_grounding" for candidate in candidates)


@pytest.mark.anyio
async def test_problem_template_analytics_api_lists_current_user_templates(db_session, fixed_search):
    app = create_app(auto_create_tables=False)

    async def override_get_db():
        yield db_session

    async def override_search_service():
        return fixed_search

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_search_service] = override_search_service

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
        problem = generated.json()["problems"][0]
        await client.post(
            f"/api/problems/{problem['id']}/submit",
            headers={"X-User-Id": "user_001"},
            json={"answer": {"choice_id": "C", "text": "C"}},
        )

        owner_response = await client.get(
            "/api/problem-template-analytics?document_id=doc_001",
            headers={"X-User-Id": "user_001"},
        )
        other_response = await client.get(
            "/api/problem-template-analytics",
            headers={"X-User-Id": "other_user"},
        )

    assert owner_response.status_code == 200
    body = owner_response.json()
    assert body["total"] == 1
    assert body["items"][0]["document_id"] == "doc_001"
    assert body["items"][0]["concept"] == "뉴턴 제2법칙"
    assert body["items"][0]["problem_count"] == 1
    assert body["items"][0]["sample_size_status"] == "insufficient"
    assert other_response.status_code == 200
    assert other_response.json()["items"] == []
