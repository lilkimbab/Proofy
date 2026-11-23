import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.db import get_db
from app.dependencies import get_generated_artifact_publisher, get_search_service
from app.main import create_app
from app.models import FeedbackActionEvent, MistakeRemediationEvent, Problem, ProblemItemAnalytics, Submission
from app.repositories.problem_regeneration_candidate_repository import ProblemRegenerationCandidateRepository


class RecordingArtifactPublisher:
    def __init__(self):
        self.problems = []
        self.feedbacks = []
        self.learning_signals = []

    def publish_problem(self, problem):
        self.problems.append(problem)
        return True

    def publish_feedback(self, feedback, *, problem=None):
        self.feedbacks.append((feedback, problem))
        return True

    def publish_user_concept_update(self, update, *, problem):
        self.learning_signals.append((update, problem))
        return True


@pytest.fixture(autouse=True)
def use_deterministic_llm_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LLM_FALLBACK_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.anyio
async def test_generate_problem_api_hides_answer_before_submission(db_session, fixed_search):
    app = create_app(auto_create_tables=False)
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async def override_search_service():
        return fixed_search

    app.dependency_overrides[get_search_service] = override_search_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/problems/generate",
            headers={"X-User-Id": "user_001"},
            json={
                "document_id": "doc_001",
                "concepts": ["뉴턴 제2법칙"],
                "type": "multiple_choice",
                "count": 1,
                "difficulty": "medium",
                "bloom_level": "understand",
            },
        )

    assert response.status_code == 200
    problem = response.json()["problems"][0]
    saved_problem = db_session.get(Problem, problem["id"])
    assert saved_problem is not None
    assert saved_problem.difficulty_profile is not None
    assert saved_problem.professor_grade_score is not None
    assert problem["source_chunk_ids"] == ["chunk_001"]
    assert problem["item_design_brief"] is None
    assert problem["difficulty_profile"] is None
    assert problem["teacher_review_checklist"] is None
    assert problem["professor_grade_score"] is None
    assert problem["student_response_simulation"] is None
    assert problem["answer"] is None
    assert problem["explanation"] is None
    assert problem["choice_explanations"] is None
    assert problem["choice_diagnostics"] is None
    assert problem["rubric"] is None
    body = response.json()
    assert body["learning_task_strategy"]["topic_label"] == "뉴턴 제2법칙"
    assert "formula" in body["learning_task_strategy"]["content_forms"]
    assert body["material_readiness"]["level"] in {"sufficient", "limited"}
    assert body["blueprint"]["total_count"] == 1
    assert body["quality_summary"]["passed"] == 1
    performance = body["quality_summary"]["performance"]
    assert performance["total_ms"] >= 0
    assert performance["search_ms"] is not None
    assert performance["candidate_generation_total_ms"] is not None
    assert performance["quality_filter_total_ms"] is not None
    assert performance["db_write_ms"] is not None
    assert performance["db_commit_ms"] is not None
    assert performance["db_refresh_ms"] is not None
    assert performance["artifact_publish_success_count"] == 0
    assert performance["artifact_publish_failure_count"] == 0
    assert performance["actual_retry_count"] == 0
    assert performance["reject_rate"] == 0
    assert performance["pass_rate"] == 1


@pytest.mark.anyio
async def test_generate_short_answer_problem_api_hides_rubric_before_submission(db_session, fixed_search):
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
                "type": "short_answer",
                "count": 1,
                "difficulty": "medium",
                "bloom_level": "analyze",
            },
        )
        problem = generated.json()["problems"][0]
        fetched = await client.get(
            f"/api/problems/{problem['id']}",
            headers={"X-User-Id": "user_001"},
        )

    saved_problem = db_session.get(Problem, problem["id"])

    assert generated.status_code == 200
    assert saved_problem is not None
    assert saved_problem.answer
    assert saved_problem.explanation
    assert saved_problem.rubric
    assert problem["answer"] is None
    assert problem["explanation"] is None
    assert problem["rubric"] is None
    assert fetched.status_code == 200
    assert fetched.json()["answer"] is None
    assert fetched.json()["explanation"] is None
    assert fetched.json()["rubric"] is None
    assert fetched.json()["item_design_brief"] is None
    assert fetched.json()["difficulty_profile"] is None
    assert fetched.json()["teacher_review_checklist"] is None
    assert fetched.json()["professor_grade_score"] is None
    assert fetched.json()["student_response_simulation"] is None


@pytest.mark.anyio
async def test_get_problem_after_short_answer_feedback_shows_solution_but_hides_internal_fields(db_session, fixed_search):
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
                "type": "short_answer",
                "count": 1,
                "difficulty": "medium",
                "bloom_level": "understand",
            },
        )
        problem_id = generated.json()["problems"][0]["id"]
        feedback_response = await client.post(
            f"/api/problems/{problem_id}/submit",
            headers={"X-User-Id": "user_001"},
            json={"answer": {"text": "같은 힘에서는 질량이 클수록 가속도는 작아진다."}},
        )
        problem_response = await client.get(
            f"/api/problems/{problem_id}",
            headers={"X-User-Id": "user_001"},
        )

    assert feedback_response.status_code == 200
    assert problem_response.status_code == 200
    problem = problem_response.json()
    assert problem["answer"] is not None
    assert problem["explanation"] is not None
    assert problem["rubric"] is not None
    assert problem["choice_explanations"] is None
    assert problem["choice_diagnostics"] is None
    assert problem["item_design_brief"] is None
    assert problem["difficulty_profile"] is None
    assert problem["teacher_review_checklist"] is None
    assert problem["professor_grade_score"] is None
    assert problem["student_response_simulation"] is None


@pytest.mark.anyio
async def test_problem_and_feedback_api_use_artifact_publisher_dependency(db_session, fixed_search):
    app = create_app(auto_create_tables=False)
    publisher = RecordingArtifactPublisher()

    async def override_get_db():
        yield db_session

    async def override_search_service():
        return fixed_search

    async def override_artifact_publisher():
        return publisher

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_search_service] = override_search_service
    app.dependency_overrides[get_generated_artifact_publisher] = override_artifact_publisher

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

    assert generated.status_code == 200
    assert submitted.status_code == 200
    assert [problem.id for problem in publisher.problems] == [problem_id]
    assert [feedback.problem_id for feedback, _ in publisher.feedbacks] == [problem_id]
    assert [update.problem_id for update, _ in publisher.learning_signals] == [problem_id]


@pytest.mark.anyio
async def test_problem_api_requires_user_id_header(db_session, fixed_search):
    app = create_app(auto_create_tables=False)

    async def override_get_db():
        yield db_session

    async def override_search_service():
        return fixed_search

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_search_service] = override_search_service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/problems/generate",
            json={
                "document_id": "doc_001",
                "concepts": ["뉴턴 제2법칙"],
                "type": "multiple_choice",
                "count": 1,
            },
        )

    assert response.status_code == 401
    assert "X-User-Id header is required" in response.json()["detail"]


@pytest.mark.anyio
async def test_submit_answer_api_reveals_private_problem_fields(db_session, fixed_search):
    app = create_app(auto_create_tables=False)
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async def override_search_service():
        return fixed_search

    app.dependency_overrides[get_search_service] = override_search_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        generated = await client.post(
            "/api/problems/generate",
            headers={"X-User-Id": "user_001"},
            json={
                "document_id": "doc_001",
                "concepts": ["뉴턴 제2법칙"],
                "type": "multiple_choice",
                "count": 1,
                "difficulty": "medium",
                "bloom_level": "understand",
            },
        )
        problem_id = generated.json()["problems"][0]["id"]

        feedback_response = await client.post(
            f"/api/problems/{problem_id}/submit",
            headers={"X-User-Id": "user_001"},
            json={"answer": {"choice_id": "C", "text": "C"}},
        )

        problem_response = await client.get(
            f"/api/problems/{problem_id}",
            headers={"X-User-Id": "user_001"},
        )

    assert feedback_response.status_code == 200
    feedback = feedback_response.json()
    assert feedback["is_correct"] is False
    assert feedback["mistake_type"] == "concept_misunderstanding"
    assert feedback["recommended_review"] == ["뉴턴 제2법칙"]
    assert feedback["choice_diagnostic"]["selected_choice_id"] == "C"
    assert feedback["choice_diagnostic"]["correct_choice_id"] == "A"
    assert feedback["choice_diagnostic"]["selected_choice_text"]
    assert feedback["choice_diagnostic"]["selected_choice_text"] in feedback["choice_diagnostic"]["misconception"]
    assert feedback["choice_diagnostic"]["repair_strategy"]
    assert feedback["copy"]["title"] == "개념의 방향이 조금 헷갈리셨군요 🤔"
    assert feedback["copy"]["next_action_type"] == "review_concept_card"
    assert feedback["copy"]["next_action_label"] == "개념 카드로 30초 복습"
    assert feedback["copy"]["secondary_action_type"] == "solve_similar"
    assert "오답입니다" not in feedback["copy"]["title"] + feedback["copy"]["body"]

    assert problem_response.status_code == 200
    problem = problem_response.json()
    assert problem["answer"]["choice_id"] == "A"
    assert problem["explanation"] is not None
    assert problem["choice_explanations"] is not None
    assert problem["choice_diagnostics"] is not None
    assert problem["rubric"] is None
    assert problem["item_design_brief"] is None
    assert problem["difficulty_profile"] is None
    assert problem["teacher_review_checklist"] is None
    assert problem["professor_grade_score"] is None
    assert problem["student_response_simulation"] is None
    assert {item["choice_id"] for item in problem["choice_diagnostics"]} == {"A", "B", "C", "D"}


@pytest.mark.anyio
async def test_regenerate_problem_candidate_api_creates_new_hidden_problem(db_session, fixed_search):
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
        source_problem_id = generated.json()["problems"][0]["id"]
        await client.post(
            f"/api/problems/{source_problem_id}/submit",
            headers={"X-User-Id": "user_001"},
            json={"answer": {"choice_id": "C", "text": "C"}},
        )

        source_problem = db_session.get(Problem, source_problem_id)
        analytics = db_session.get(ProblemItemAnalytics, source_problem_id)
        analytics.total_attempts = 5
        analytics.correct_count = 0
        analytics.incorrect_count = 5
        analytics.correct_rate = 0
        analytics.needs_review = True
        analytics.review_reasons = ["very_low_correct_rate"]
        candidate = ProblemRegenerationCandidateRepository(db_session).upsert_from_analytics(
            problem=source_problem,
            analytics=analytics,
        )
        db_session.commit()

        response = await client.post(
            f"/api/problem-regeneration-candidates/{candidate.id}/regenerate",
            headers={"X-User-Id": "user_001"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["original_problem_id"] == source_problem_id
    assert body["candidate"]["status"] == "resolved"
    assert body["candidate"]["generated_problem_id"] == body["problem"]["id"]
    assert body["problem"]["id"] != source_problem_id
    assert body["problem"]["question"] != source_problem.question
    assert body["problem"]["answer"] is None
    assert body["problem"]["explanation"] is None


@pytest.mark.anyio
async def test_problem_hint_api_blocks_leakage_and_full_solution_until_submission(db_session, fixed_search):
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
        problem_id = problem["id"]

        hint_response = await client.post(
            f"/api/problems/{problem_id}/hints",
            headers={"X-User-Id": "user_001"},
            json={"level": 0, "mode": "practice"},
        )
        exam_response = await client.post(
            f"/api/problems/{problem_id}/hints",
            headers={"X-User-Id": "user_001"},
            json={"level": 0, "mode": "exam"},
        )
        full_solution_before_submit = await client.post(
            f"/api/problems/{problem_id}/hints",
            headers={"X-User-Id": "user_001"},
            json={"level": 6, "mode": "practice"},
        )
        await client.post(
            f"/api/problems/{problem_id}/submit",
            headers={"X-User-Id": "user_001"},
            json={"answer": {"choice_id": "C", "text": "C"}},
        )
        full_solution_after_submit = await client.post(
            f"/api/problems/{problem_id}/hints",
            headers={"X-User-Id": "user_001"},
            json={"level": 6, "mode": "practice"},
        )

    assert hint_response.status_code == 200
    hint = hint_response.json()
    assert hint["level"] == 0
    assert hint["next_level"] == 1
    assert hint["hint_count"] == 1
    assert hint["answer_revealed"] is False
    assert "정답은" not in hint["hint"]
    assert "choice_id" not in hint["hint"]
    assert exam_response.status_code == 403
    assert full_solution_before_submit.status_code == 403
    assert full_solution_after_submit.status_code == 200
    assert full_solution_after_submit.json()["answer_revealed"] is True


@pytest.mark.anyio
async def test_get_feedback_api_returns_existing_feedback_for_owner(db_session, fixed_search):
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
        problem_id = generated.json()["problems"][0]["id"]
        submitted = await client.post(
            f"/api/problems/{problem_id}/submit",
            headers={"X-User-Id": "user_001"},
            json={"answer": {"choice_id": "C", "text": "C"}},
        )
        feedback_id = submitted.json()["id"]

        owner_response = await client.get(
            f"/api/feedback/{feedback_id}",
            headers={"X-User-Id": "user_001"},
        )
        other_user_response = await client.get(
            f"/api/feedback/{feedback_id}",
            headers={"X-User-Id": "other_user"},
        )

    assert owner_response.status_code == 200
    feedback = owner_response.json()
    assert feedback["id"] == feedback_id
    assert feedback["problem_id"] == problem_id
    assert feedback["source_chunk_ids"] == ["chunk_001"]
    assert feedback["copy"]["next_action_type"]
    assert feedback["copy"]["next_action_label"]
    assert other_user_response.status_code == 404


@pytest.mark.anyio
async def test_feedback_action_event_api_records_next_action_click(db_session, fixed_search):
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
        problem_id = generated.json()["problems"][0]["id"]
        submitted = await client.post(
            f"/api/problems/{problem_id}/submit",
            headers={"X-User-Id": "user_001"},
            json={"answer": {"choice_id": "C", "text": "C"}},
        )
        feedback_id = submitted.json()["id"]
        next_action_type = submitted.json()["copy"]["next_action_type"]

        action_response = await client.post(
            f"/api/feedback/{feedback_id}/actions",
            headers={"X-User-Id": "user_001"},
            json={
                "event_type": "next_action_clicked",
                "action_type": next_action_type,
                "event_metadata": {"surface": "feedback_card"},
            },
        )
        list_response = await client.get(
            f"/api/feedback/{feedback_id}/actions",
            headers={"X-User-Id": "user_001"},
        )

    assert action_response.status_code == 201
    action = action_response.json()
    assert action["feedback_id"] == feedback_id
    assert action["problem_id"] == problem_id
    assert action["event_type"] == "next_action_clicked"
    assert action["action_type"] == "review_concept_card"
    assert action["event_metadata"] == {"surface": "feedback_card"}
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert db_session.query(FeedbackActionEvent).count() == 1


@pytest.mark.anyio
async def test_feedback_action_event_api_validates_owner_and_payload(db_session, fixed_search):
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
        problem_id = generated.json()["problems"][0]["id"]
        submitted = await client.post(
            f"/api/problems/{problem_id}/submit",
            headers={"X-User-Id": "user_001"},
            json={"answer": {"choice_id": "C", "text": "C"}},
        )
        feedback_id = submitted.json()["id"]

        missing_action_type = await client.post(
            f"/api/feedback/{feedback_id}/actions",
            headers={"X-User-Id": "user_001"},
            json={"event_type": "next_action_clicked"},
        )
        other_user = await client.post(
            f"/api/feedback/{feedback_id}/actions",
            headers={"X-User-Id": "other_user"},
            json={"event_type": "helpful_rating", "helpful_rating": 4},
        )
        valid_rating = await client.post(
            f"/api/feedback/{feedback_id}/actions",
            headers={"X-User-Id": "user_001"},
            json={"event_type": "helpful_rating", "helpful_rating": 4},
        )
        missing_followup_target = await client.post(
            f"/api/feedback/{feedback_id}/actions",
            headers={"X-User-Id": "user_001"},
            json={"event_type": "followup_problem_completed", "is_successful": True},
        )
        valid_specific_action = await client.post(
            f"/api/feedback/{feedback_id}/actions",
            headers={"X-User-Id": "user_001"},
            json={"event_type": "next_action_clicked", "action_type": "mark_conditions"},
        )

    assert missing_action_type.status_code == 422
    assert other_user.status_code == 404
    assert valid_rating.status_code == 201
    assert valid_rating.json()["helpful_rating"] == 4
    assert missing_followup_target.status_code == 422
    assert valid_specific_action.status_code == 201
    assert valid_specific_action.json()["action_type"] == "mark_conditions"


@pytest.mark.anyio
async def test_followup_completion_action_updates_remediation_event(db_session, fixed_search):
    app = create_app(auto_create_tables=False)

    async def override_get_db():
        yield db_session

    async def override_search_service():
        return fixed_search

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_search_service] = override_search_service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        seed = await client.post(
            "/api/problems/generate",
            headers={"X-User-Id": "user_001"},
            json={
                "document_id": "doc_001",
                "concepts": ["뉴턴 제2법칙"],
                "type": "multiple_choice",
                "count": 1,
            },
        )
        seed_problem_id = seed.json()["problems"][0]["id"]
        submitted = await client.post(
            f"/api/problems/{seed_problem_id}/submit",
            headers={"X-User-Id": "user_001"},
            json={"answer": {"choice_id": "C", "text": "C"}},
        )
        source_feedback_id = submitted.json()["id"]
        followup = await client.post(
            "/api/problems/generate",
            headers={"X-User-Id": "user_001"},
            json={
                "document_id": "doc_001",
                "concepts": ["뉴턴 제2법칙"],
                "type": "multiple_choice",
                "count": 1,
            },
        )
        followup_problem_id = followup.json()["problems"][0]["id"]
        remediation_event = MistakeRemediationEvent(
            user_id="user_001",
            source_feedback_id=source_feedback_id,
            source_problem_id=seed_problem_id,
            followup_problem_id=followup_problem_id,
            target_concepts=["뉴턴 제2법칙"],
            target_mistake_type="concept_misunderstanding",
        )
        db_session.add(remediation_event)
        db_session.commit()

        action_response = await client.post(
            f"/api/feedback/{source_feedback_id}/actions",
            headers={"X-User-Id": "user_001"},
            json={
                "event_type": "followup_problem_completed",
                "target_problem_id": followup_problem_id,
                "is_successful": True,
                "event_metadata": {"surface": "followup_result"},
            },
        )

    assert action_response.status_code == 201
    action = action_response.json()
    assert action["event_type"] == "followup_problem_completed"
    assert action["target_problem_id"] == followup_problem_id
    assert action["is_successful"] is True
    db_session.refresh(remediation_event)
    assert remediation_event.resolved is True
    assert remediation_event.resolved_at is not None


@pytest.mark.anyio
async def test_problem_analytics_api_returns_post_use_stats_for_owner(db_session, fixed_search):
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
        problem_id = generated.json()["problems"][0]["id"]

        before_submit = await client.get(
            f"/api/problems/{problem_id}/analytics",
            headers={"X-User-Id": "user_001"},
        )
        list_before_submit = await client.get(
            "/api/problem-analytics",
            headers={"X-User-Id": "user_001"},
        )
        await client.post(
            f"/api/problems/{problem_id}/submit",
            headers={"X-User-Id": "user_001"},
            json={"answer": {"choice_id": "C", "text": "C"}, "elapsed_time_sec": 35.0, "hint_count": 1},
        )
        owner_response = await client.get(
            f"/api/problems/{problem_id}/analytics",
            headers={"X-User-Id": "user_001"},
        )
        other_user_response = await client.get(
            f"/api/problems/{problem_id}/analytics",
            headers={"X-User-Id": "other_user"},
        )
        owner_list_response = await client.get(
            "/api/problem-analytics?document_id=doc_001&needs_review=false",
            headers={"X-User-Id": "user_001"},
        )
        other_user_list_response = await client.get(
            "/api/problem-analytics",
            headers={"X-User-Id": "other_user"},
        )
        candidate_list_response = await client.get(
            "/api/problem-regeneration-candidates",
            headers={"X-User-Id": "user_001"},
        )

    assert before_submit.status_code == 404
    assert list_before_submit.status_code == 200
    assert list_before_submit.json()["items"] == []
    assert owner_response.status_code == 200
    analytics = owner_response.json()
    assert analytics["problem_id"] == problem_id
    assert analytics["problem_type"] == "multiple_choice"
    assert analytics["total_attempts"] == 1
    assert analytics["incorrect_count"] == 1
    assert analytics["correct_rate"] == 0
    assert analytics["correct_rate_smoothed"] == 0.333
    assert analytics["sample_size_status"] == "insufficient"
    assert analytics["statistics_confidence"] == "low"
    assert "참고용" in analytics["statistics_note"]
    assert analytics["quality_score_source"] == "item_quality"
    assert analytics["quality_score_for_review"] is not None
    assert analytics["timed_attempt_count"] == 1
    assert analytics["average_time_sec"] == 35.0
    assert analytics["hint_usage_count"] == 1
    assert analytics["hint_usage_rate"] == 1.0
    assert analytics["choice_selection_counts"] == {"C": 1}
    assert analytics["choice_mistake_type_counts"]["C"]["concept_misunderstanding"] == 1
    assert analytics["common_mistake_types"] == ["concept_misunderstanding"]
    assert other_user_response.status_code == 404
    assert owner_list_response.status_code == 200
    analytics_list = owner_list_response.json()
    assert analytics_list["total"] == 1
    assert analytics_list["limit"] == 50
    assert analytics_list["items"][0]["problem_id"] == problem_id
    assert analytics_list["items"][0]["sample_size_status"] == "insufficient"
    assert analytics_list["items"][0]["choice_selection_counts"] == {"C": 1}
    assert other_user_list_response.status_code == 200
    assert other_user_list_response.json()["items"] == []
    assert candidate_list_response.status_code == 200
    assert candidate_list_response.json()["items"] == []


@pytest.mark.anyio
async def test_submit_answer_api_rejects_duplicate_submission(db_session, fixed_search):
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
        problem_id = generated.json()["problems"][0]["id"]

        first_response = await client.post(
            f"/api/problems/{problem_id}/submit",
            headers={"X-User-Id": "user_001"},
            json={"answer": {"choice_id": "C", "text": "C"}},
        )
        second_response = await client.post(
            f"/api/problems/{problem_id}/submit",
            headers={"X-User-Id": "user_001"},
            json={"answer": {"choice_id": "A", "text": "A"}},
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert "Problem already submitted" in second_response.json()["detail"]
    assert db_session.query(Submission).count() == 1


@pytest.mark.anyio
async def test_submit_answer_rejects_problem_owned_by_another_user(db_session, fixed_search):
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
            f"/api/problems/{problem_id}/submit",
            headers={"X-User-Id": "other_user"},
            json={"answer": {"choice_id": "A", "text": "A"}},
        )

    assert response.status_code == 404
    assert db_session.query(Submission).count() == 0


@pytest.mark.anyio
async def test_problem_api_keeps_answer_hidden_when_submission_has_no_feedback(db_session, fixed_search):
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
        problem_id = generated.json()["problems"][0]["id"]
        db_session.add(
            Submission(
                problem_id=problem_id,
                user_id="user_001",
                answer={"choice_id": "A"},
                solution_steps=None,
            )
        )
        db_session.commit()

        response = await client.get(
            f"/api/problems/{problem_id}",
            headers={"X-User-Id": "user_001"},
        )

    assert response.status_code == 200
    problem = response.json()
    assert problem["answer"] is None
    assert problem["explanation"] is None


@pytest.mark.anyio
async def test_submit_multiple_choice_requires_choice_id(db_session, fixed_search):
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
        problem_id = generated.json()["problems"][0]["id"]

        response = await client.post(
            f"/api/problems/{problem_id}/submit",
            headers={"X-User-Id": "user_001"},
            json={"answer": {"text": "A"}},
        )

    assert response.status_code == 422
    assert "choice_id is required" in response.json()["detail"]
    assert db_session.query(Submission).count() == 0


@pytest.mark.anyio
async def test_submit_multiple_choice_rejects_unknown_choice_id(db_session, fixed_search):
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
        problem_id = generated.json()["problems"][0]["id"]

        response = await client.post(
            f"/api/problems/{problem_id}/submit",
            headers={"X-User-Id": "user_001"},
            json={"answer": {"choice_id": "Z", "text": "Z"}},
        )

    assert response.status_code == 422
    assert "choice_id must exist in problem choices" in response.json()["detail"]
    assert db_session.query(Submission).count() == 0


@pytest.mark.anyio
async def test_submit_short_answer_api_accepts_typed_answer(db_session, fixed_search):
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
                "type": "short_answer",
                "count": 1,
            },
        )
        problem_id = generated.json()["problems"][0]["id"]

        response = await client.post(
            f"/api/problems/{problem_id}/submit",
            headers={"X-User-Id": "user_001"},
            json={"answer": {"input_mode": "typed", "text": "뉴턴 제2법칙은 힘과 질량의 관계를 설명한다."}},
        )

    assert response.status_code == 200
    feedback = response.json()
    assert feedback["max_score"] == 4
    assert "recommended_review" in feedback
    assert feedback["evaluation_details"] is not None
    assert feedback["evaluation_details"]["rubric_results"]
    assert feedback["evaluation_details"]["confidence_reasons"]
    assert "needs_grading_review" in feedback["evaluation_details"]
    assert "grading_review_reasons" in feedback["evaluation_details"]


@pytest.mark.anyio
async def test_submit_short_answer_api_accepts_tablet_ocr_answer(db_session, fixed_search):
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
                "type": "short_answer",
                "count": 1,
            },
        )
        problem_id = generated.json()["problems"][0]["id"]

        response = await client.post(
            f"/api/problems/{problem_id}/submit",
            headers={"X-User-Id": "user_001"},
            json={
                "answer": {
                    "input_mode": "tablet_ocr",
                    "ocr_text": "뉴턴 제2법칙은 힘과 질량과 가속도의 관계를 설명한다.",
                    "ocr_confidence": 0.91,
                    "tablet_image_url": "https://example.test/submission.png",
                }
            },
        )

    assert response.status_code == 200
    feedback = response.json()
    assert "recommended_review" in feedback
    assert feedback["evaluation_details"]["confidence_reasons"]
    assert any("OCR 신뢰도" in reason for reason in feedback["evaluation_details"]["confidence_reasons"])


@pytest.mark.anyio
async def test_low_confidence_short_answer_copy_is_cautious(db_session, fixed_search):
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
                "type": "short_answer",
                "count": 1,
            },
        )
        problem_id = generated.json()["problems"][0]["id"]

        response = await client.post(
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

    assert response.status_code == 200
    feedback = response.json()
    assert feedback["evaluation_details"]["confidence"] == "low"
    assert "OCR 신뢰도가 낮아" in " ".join(feedback["evaluation_details"]["confidence_reasons"])
    assert {item["confidence"] for item in feedback["evaluation_details"]["rubric_results"]} == {"low"}
    assert feedback["evaluation_details"]["needs_grading_review"] is True
    assert feedback["evaluation_details"]["grading_review_reasons"]
    assert "조금 애매할 수 있어요" in feedback["copy"]["body"]
    assert "low_confidence_feedback_copy" in feedback["copy"]["warnings"]


@pytest.mark.anyio
async def test_submit_short_answer_returns_503_when_source_chunks_are_missing(db_session, fixed_search):
    class MissingBatchSearchService:
        def search_chunks(self, **kwargs):
            return fixed_search.chunks

        def get_chunks_by_ids(self, **kwargs):
            return []

    app = create_app(auto_create_tables=False)

    async def override_get_db():
        yield db_session

    async def override_search_service():
        return MissingBatchSearchService()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_search_service] = override_search_service

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
        problem = db_session.get(Problem, problem_id)
        problem.source_evidence_snapshot = None
        db_session.commit()

        response = await client.post(
            f"/api/problems/{problem_id}/submit",
            headers={"X-User-Id": "user_001"},
            json={"answer": {"text": "뉴턴 제2법칙은 힘과 질량의 관계를 설명한다."}},
        )

    assert response.status_code == 503
    assert "did not return source chunks" in response.json()["detail"]
    assert db_session.query(Submission).count() == 0


@pytest.mark.anyio
async def test_submit_short_answer_returns_503_when_source_chunk_document_mismatches(db_session, fixed_search):
    class MismatchedBatchSearchService:
        def search_chunks(self, **kwargs):
            return fixed_search.chunks

        def get_chunks_by_ids(self, **kwargs):
            chunk = fixed_search.chunks[0].model_copy(update={"document_id": "other_doc"})
            return [chunk]

    app = create_app(auto_create_tables=False)

    async def override_get_db():
        yield db_session

    async def override_search_service():
        return MismatchedBatchSearchService()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_search_service] = override_search_service

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
        problem = db_session.get(Problem, problem_id)
        problem.source_evidence_snapshot = None
        db_session.commit()

        response = await client.post(
            f"/api/problems/{problem_id}/submit",
            headers={"X-User-Id": "user_001"},
            json={"answer": {"text": "뉴턴 제2법칙은 힘과 질량의 관계를 설명한다."}},
        )

    assert response.status_code == 503
    assert "different document" in response.json()["detail"]
    assert db_session.query(Submission).count() == 0


@pytest.mark.anyio
async def test_submit_short_answer_returns_503_when_search_agent_returns_unexpected_source_chunk(db_session, fixed_search):
    class ExtraBatchSearchService:
        def search_chunks(self, **kwargs):
            return fixed_search.chunks

        def get_chunks_by_ids(self, **kwargs):
            extra_chunk = fixed_search.chunks[0].model_copy(update={"chunk_id": "extra_chunk_999"})
            return [fixed_search.chunks[0], extra_chunk]

    app = create_app(auto_create_tables=False)

    async def override_get_db():
        yield db_session

    async def override_search_service():
        return ExtraBatchSearchService()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_search_service] = override_search_service

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
        problem = db_session.get(Problem, problem_id)
        problem.source_evidence_snapshot = None
        db_session.commit()

        response = await client.post(
            f"/api/problems/{problem_id}/submit",
            headers={"X-User-Id": "user_001"},
            json={"answer": {"text": "뉴턴 제2법칙은 힘과 질량의 관계를 설명한다."}},
        )

    assert response.status_code == 503
    assert "unexpected source chunks" in response.json()["detail"]
    assert db_session.query(Submission).count() == 0
