from datetime import datetime, timezone

import httpx
import pytest

from app.agents import FeedbackAgent, ProblemAgent, ProblemQualityChecker
from app.config import Settings
from app.models import Feedback, Problem
from app.schemas.learning_contents import LearningContentBase
from app.schemas.problems import (
    AssessmentSessionConceptResult,
    AssessmentSessionProblemResult,
    AssessmentSessionReportResponse,
    AssessmentSessionStatus,
    GenerateProblemRequest,
    SubmitAnswerRequest,
)
from app.schemas.quality import QualityStatus
from app.services.feedback_service import FeedbackService
from app.services.generated_artifact_publisher import (
    GeneratedArtifactPublishError,
    GeneratedArtifactPublisher,
    INDEX_CONTENT_CHAR_LIMIT,
)
from app.services.problem_service import ProblemService


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


def build_problem_service(db_session, fixed_search, publisher):
    settings = Settings(
        DATABASE_URL="sqlite+pysqlite://",
        OPENAI_API_KEY=None,
        LLM_FALLBACK_ENABLED=True,
    )
    return ProblemService(
        db=db_session,
        search_service=fixed_search,
        problem_agent=ProblemAgent(settings=settings),
        quality_checker=ProblemQualityChecker(),
        artifact_publisher=publisher,
        settings=settings,
    )


def build_feedback_service(db_session, fixed_search, publisher):
    return FeedbackService(
        db=db_session,
        feedback_agent=FeedbackAgent(),
        search_service=fixed_search,
        artifact_publisher=publisher,
    )


def test_problem_generation_publishes_generated_problem_metadata(db_session, fixed_search):
    publisher = RecordingArtifactPublisher()
    service = build_problem_service(db_session, fixed_search, publisher)

    result = service.generate_problem_batch(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
        ),
    )
    problems = result.problems

    assert publisher.problems == problems
    performance = result.quality_summary.performance
    assert performance is not None
    assert performance.artifact_publish_success_count == 1
    assert performance.artifact_publish_failure_count == 0


def test_feedback_submission_publishes_feedback_metadata(db_session, fixed_search):
    publisher = RecordingArtifactPublisher()
    problem_service = build_problem_service(db_session, fixed_search, publisher)
    feedback_service = build_feedback_service(db_session, fixed_search, publisher)
    problem = problem_service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
        ),
    )[0]

    feedback = feedback_service.submit_answer(
        problem_id=problem.id,
        user_id="user_001",
        request=SubmitAnswerRequest(answer={"choice_id": "C", "text": "C"}),
    )

    assert publisher.feedbacks == [(feedback, problem)]
    assert len(publisher.learning_signals) == 1
    update, update_problem = publisher.learning_signals[0]
    assert update.feedback_id == feedback.id
    assert update_problem == problem


def test_problem_index_payload_hides_answer_and_explanation(db_session, fixed_search):
    service = build_problem_service(db_session, fixed_search, RecordingArtifactPublisher())
    problem = service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
        ),
    )[0]
    payload = GeneratedArtifactPublisher().build_problem_payload(problem)

    assert payload.artifact_id == problem.id
    assert payload.artifact_type == "problem"
    assert payload.visibility == "hidden_until_submission"
    assert payload.user_id == "user_001"
    assert payload.document_id == "doc_001"
    assert payload.source_chunk_ids == ["chunk_001"]
    assert payload.metadata["source_chunk_ids"] == ["chunk_001"]
    assert payload.metadata["schema_version"] == "problem_artifact.v1"
    assert payload.metadata["producer"] == "problem_agent"
    assert payload.metadata["question"] == problem.question
    assert payload.metadata["answer_hidden_until_submission"] is True
    assert "answer" not in payload.metadata
    assert "explanation" not in payload.metadata
    assert problem.explanation not in payload.content


def test_feedback_index_payload_is_user_private(db_session, fixed_search):
    problem_service = build_problem_service(db_session, fixed_search, RecordingArtifactPublisher())
    feedback_service = build_feedback_service(db_session, fixed_search, RecordingArtifactPublisher())
    problem = problem_service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
        ),
    )[0]
    feedback = feedback_service.submit_answer(
        problem_id=problem.id,
        user_id="user_001",
        request=SubmitAnswerRequest(answer={"choice_id": "C", "text": "C"}),
    )

    payload = GeneratedArtifactPublisher().build_feedback_payload(feedback)

    assert payload.artifact_id == feedback.id
    assert payload.artifact_type == "feedback"
    assert payload.visibility == "private"
    assert payload.user_id == "user_001"
    assert payload.document_id == "doc_001"
    assert payload.metadata["problem_id"] == problem.id
    assert payload.metadata["schema_version"] == "feedback_artifact.v1"
    assert payload.metadata["producer"] == "problem_agent"
    assert payload.metadata["summary"] == feedback.summary
    assert payload.metadata["mistake_type"] == "concept_misunderstanding"
    assert "피드백" in payload.content


def test_feedback_payload_can_use_explicit_problem_without_lazy_relationship():
    problem = Problem(
        id="prob_001",
        user_id="user_001",
        document_id="doc_001",
        type="multiple_choice",
        difficulty="medium",
        bloom_level="understand",
        question="문제",
        choices=[{"id": "A", "text": "정답"}],
        answer={"choice_id": "A", "text": "정답"},
        explanation="해설",
        concepts=["개념"],
        source_chunk_ids=["chunk_001"],
        quality_status="passed",
    )
    feedback = Feedback(
        id="fb_001",
        submission_id="sub_001",
        problem_id="prob_001",
        user_id="user_001",
        is_correct=False,
        score=0,
        max_score=1,
        mistake_type="concept_misunderstanding",
        weak_concepts=["개념"],
        summary="요약",
        feedback="피드백",
        recommended_review=["개념"],
        source_chunk_ids=["chunk_001"],
    )

    payload = GeneratedArtifactPublisher().build_feedback_payload(feedback, problem=problem)

    assert payload.document_id == "doc_001"
    assert payload.visibility == "private"


def test_learning_signal_payload_is_private_user_update_without_answer(db_session, fixed_search):
    problem_service = build_problem_service(db_session, fixed_search, RecordingArtifactPublisher())
    feedback_service = build_feedback_service(db_session, fixed_search, RecordingArtifactPublisher())
    problem = problem_service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
        ),
    )[0]
    result = feedback_service.submit_answer_with_update(
        problem_id=problem.id,
        user_id="user_001",
        request=SubmitAnswerRequest(answer={"choice_id": "C", "text": "C"}),
    )

    payload = GeneratedArtifactPublisher().build_user_concept_update_payload(
        result.user_concept_update,
        problem=problem,
    )

    assert payload.artifact_id == f"learning_signal:{result.feedback.id}"
    assert payload.artifact_type == "learning_signal"
    assert payload.visibility == "private"
    assert payload.user_id == "user_001"
    assert payload.document_id == "doc_001"
    assert payload.source_chunk_ids == problem.source_chunk_ids
    assert payload.metadata["schema_version"] == "learning_signal_artifact.v1"
    assert payload.metadata["feedback_id"] == result.feedback.id
    assert payload.metadata["mastery_updates"]
    assert "answer" not in payload.metadata
    assert "explanation" not in payload.metadata
    assert str(problem.answer["choice_id"]) not in payload.content


def test_learning_content_payload_hides_auto_gradable_answer():
    content = LearningContentBase(
        id="content_001",
        user_id="user_001",
        document_id="doc_001",
        content_type="cloze",
        concepts=["뉴턴 제2법칙"],
        source_chunk_ids=["chunk_001"],
        difficulty="medium",
        bloom_level="understand",
        quality_status=QualityStatus.passed,
        quality_report={"status": "passed", "score": 0.9, "source_grounded": True},
        payload={
            "prompt": "힘은 질량과 ____의 곱이다.",
            "answer": "가속도",
            "acceptable_answers": ["가속도"],
            "explanation": "자료에서는 힘, 질량, 가속도의 관계를 설명한다.",
        },
    )

    payload = GeneratedArtifactPublisher().build_learning_content_payload(content)

    assert payload.artifact_id == "content_001"
    assert payload.artifact_type == "learning_content"
    assert payload.visibility == "private"
    assert payload.metadata["schema_version"] == "learning_content_artifact.v1"
    assert payload.metadata["content_type"] == "cloze"
    assert payload.metadata["private_payload_available"] is True
    assert "힘은 질량과 ____의 곱이다." in payload.content
    assert "가속도" not in payload.content
    assert "answer" not in payload.metadata
    assert "explanation" not in payload.metadata


def test_learning_content_index_content_is_bounded_for_large_payload():
    pairs = [
        {
            "left": f"개념 {index} " + ("왼쪽 설명 " * 18),
            "right": f"정의 {index} " + ("오른쪽 설명 " * 28),
        }
        for index in range(12)
    ]
    content = LearningContentBase(
        id="content_001",
        user_id="user_001",
        document_id="doc_001",
        content_type="matching",
        concepts=["뉴턴 제2법칙"],
        source_chunk_ids=["chunk_001"],
        difficulty="medium",
        bloom_level="understand",
        quality_status=QualityStatus.passed,
        quality_report={"status": "passed", "score": 0.9, "source_grounded": True},
        payload={
            "prompt": "자료의 개념과 설명을 연결하세요. " * 40,
            "pairs": pairs,
            "explanation": "각 개념은 자료의 정의와 연결됩니다.",
        },
    )

    payload = GeneratedArtifactPublisher().build_learning_content_payload(content)

    assert len(payload.content) <= INDEX_CONTENT_CHAR_LIMIT
    assert payload.content.endswith("[truncated for index]")


def test_assessment_report_payload_keeps_only_learning_summary():
    now = datetime(2026, 5, 12, tzinfo=timezone.utc)
    report = AssessmentSessionReportResponse(
        session_id="asess_001",
        status=AssessmentSessionStatus.submitted,
        document_id="doc_001",
        retry_of_session_id="asess_000",
        previous_score_ratio=0.25,
        score_delta=0.5,
        concept_score_deltas={"뉴턴 제2법칙": 0.5},
        problem_count=2,
        submitted_count=2,
        correct_count=1,
        total_score=1,
        max_score=2,
        score_ratio=0.5,
        completion_ratio=1,
        total_elapsed_time_sec=330,
        time_limit_seconds=300,
        time_remaining_seconds=0,
        time_over_limit=True,
        strong_concepts=["힘"],
        weak_concepts=["뉴턴 제2법칙"],
        recommended_review=["뉴턴 제2법칙"],
        concept_results=[
            AssessmentSessionConceptResult(
                concept="뉴턴 제2법칙",
                problem_count=2,
                submitted_count=2,
                correct_count=1,
                total_score=1,
                max_score=2,
                score_ratio=0.5,
                status="needs_review",
            )
        ],
        results=[
            AssessmentSessionProblemResult(
                problem_id="prob_001",
                submitted=True,
                feedback_id="fb_001",
                is_correct=False,
                score=0,
                max_score=1,
                weak_concepts=["뉴턴 제2법칙"],
                recommended_review=["뉴턴 제2법칙"],
            )
        ],
        next_step="뉴턴 제2법칙을 다시 확인해 보세요.",
        created_at=now,
        submitted_at=now,
    )

    payload = GeneratedArtifactPublisher().build_assessment_report_payload(report, user_id="user_001")

    assert payload.artifact_id == "assessment_report:asess_001"
    assert payload.artifact_type == "assessment_report"
    assert payload.visibility == "private"
    assert payload.user_id == "user_001"
    assert payload.document_id == "doc_001"
    assert payload.metadata["schema_version"] == "assessment_report_artifact.v1"
    assert payload.metadata["time_over_limit"] is True
    assert payload.metadata["weak_concepts"] == ["뉴턴 제2법칙"]
    assert payload.metadata["concept_summary"] == [
        {
            "concept": "뉴턴 제2법칙",
            "status": "needs_review",
            "score_ratio": 0.5,
            "submitted_count": 2,
            "problem_count": 2,
        }
    ]
    assert "results" not in payload.metadata
    assert "feedback_id" not in repr(payload.metadata)
    assert "answer" not in payload.content.lower()
    assert "explanation" not in payload.content.lower()
    assert "answer" not in repr(payload.metadata).lower()
    assert "explanation" not in repr(payload.metadata).lower()


def test_assessment_report_payload_caps_large_learning_summary():
    now = datetime(2026, 5, 12, tzinfo=timezone.utc)
    concepts = [f"개념{i:02d}" for i in range(25)]
    report = AssessmentSessionReportResponse(
        session_id="asess_001",
        status=AssessmentSessionStatus.submitted,
        document_id="doc_001",
        problem_count=25,
        submitted_count=25,
        correct_count=5,
        total_score=5,
        max_score=25,
        score_ratio=0.2,
        completion_ratio=1,
        weak_concepts=concepts,
        recommended_review=concepts,
        concept_score_deltas={concept: -0.1 for concept in concepts},
        concept_results=[
            AssessmentSessionConceptResult(
                concept=concept,
                problem_count=1,
                submitted_count=1,
                correct_count=0,
                total_score=0,
                max_score=1,
                score_ratio=0,
                status="needs_review",
            )
            for concept in concepts
        ],
        results=[],
        next_step="약점 개념부터 다시 확인해 보세요.",
        created_at=now,
        submitted_at=now,
    )

    payload = GeneratedArtifactPublisher().build_assessment_report_payload(report, user_id="user_001")

    assert len(payload.metadata["weak_concepts"]) == 20
    assert len(payload.metadata["recommended_review"]) == 20
    assert len(payload.metadata["concept_score_deltas"]) == 20
    assert len(payload.metadata["concept_summary"]) == 20
    assert "개념24" not in payload.content


def test_disabled_publisher_is_noop_without_building_payload():
    publisher = GeneratedArtifactPublisher(
        Settings(
            DATABASE_URL="sqlite+pysqlite://",
            GENERATED_ARTIFACT_PUBLISH_ENABLED=False,
            GENERATED_ARTIFACT_INDEX_URL=None,
        )
    )

    assert publisher.publish_feedback(object()) is False


def test_enabled_publisher_posts_generated_artifact_payload(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json={"ok": True})

    monkeypatch.setattr(httpx, "post", fake_post)
    settings = Settings(
        DATABASE_URL="sqlite+pysqlite://",
        GENERATED_ARTIFACT_PUBLISH_ENABLED=True,
        GENERATED_ARTIFACT_INDEX_URL="http://rag-agent/generated-artifacts/index",
        OPENAI_TIMEOUT_SECONDS=7,
        GENERATED_ARTIFACT_TIMEOUT_SECONDS=2.5,
    )
    publisher = GeneratedArtifactPublisher(settings)
    payload = {
        "artifact_id": "prob_001",
        "artifact_type": "problem",
        "user_id": "user_001",
        "document_id": "doc_001",
        "content": "문제: 예시 문제",
        "metadata": {"answer_hidden_until_submission": True},
        "source_chunk_ids": ["chunk_001"],
        "visibility": "hidden_until_submission",
    }

    assert publisher._post(publisher.build_problem_payload(type("ProblemStub", (), {
        "id": "prob_001",
        "user_id": "user_001",
        "document_id": "doc_001",
        "question": "예시 문제",
        "choices": [],
        "type": "short_answer",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "concepts": ["개념"],
        "source_refs": [],
        "quality_status": "passed",
        "item_model_id": None,
        "source_chunk_ids": ["chunk_001"],
        "created_at": None,
    })())) is True
    assert captured["url"] == "http://rag-agent/generated-artifacts/index"
    assert captured["timeout"] == 2.5
    assert captured["json"]["artifact_id"] == payload["artifact_id"]
    assert captured["json"]["visibility"] == "hidden_until_submission"


def test_enabled_publisher_can_send_auth_header(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout, headers):
        captured["url"] = url
        captured["headers"] = headers
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json={"ok": True})

    monkeypatch.setattr(httpx, "post", fake_post)
    publisher = GeneratedArtifactPublisher(
        Settings(
            DATABASE_URL="sqlite+pysqlite://",
            GENERATED_ARTIFACT_PUBLISH_ENABLED=True,
            GENERATED_ARTIFACT_INDEX_URL="http://rag-agent/generated-artifacts/index",
            GENERATED_ARTIFACT_API_KEY="secret-key",
            GENERATED_ARTIFACT_API_KEY_HEADER="X-RAG-API-Key",
        )
    )

    problem = type(
        "ProblemStub",
        (),
        {
            "id": "prob_001",
            "user_id": "user_001",
            "document_id": "doc_001",
            "question": "예시 문제",
            "choices": [],
            "type": "short_answer",
            "difficulty": "hard",
            "bloom_level": "analyze",
            "concepts": ["개념"],
            "source_refs": [],
            "quality_status": "passed",
            "item_model_id": None,
            "source_chunk_ids": ["chunk_001"],
            "created_at": None,
        },
    )()

    assert publisher.publish_problem(problem) is True
    assert captured["headers"] == {"X-RAG-API-Key": "secret-key"}


def test_publisher_can_send_problem_payload_to_rag_add(monkeypatch):
    captured = {}

    def fake_post(url, files, data, timeout):
        captured["url"] = url
        captured["files"] = files
        captured["data"] = data
        captured["timeout"] = timeout
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json={"title": data["title"]})

    monkeypatch.setattr(httpx, "post", fake_post)
    publisher = GeneratedArtifactPublisher(
        Settings(
            DATABASE_URL="sqlite+pysqlite://",
            GENERATED_ARTIFACT_ADD_URL="http://rag-agent/add",
            GENERATED_ARTIFACT_TIMEOUT_SECONDS=4,
        )
    )
    problem = type(
        "ProblemStub",
        (),
        {
            "id": "prob_001",
            "user_id": "user_001",
            "document_id": "doc_001",
            "question": "예시 문제",
            "choices": [{"id": "A", "text": "보기 A"}],
            "type": "multiple_choice",
            "difficulty": "hard",
            "bloom_level": "analyze",
            "concepts": ["개념"],
            "source_refs": [],
            "quality_status": "passed",
            "item_model_id": "case_based_application",
            "source_chunk_ids": ["chunk_001"],
            "created_at": None,
            "answer": {"choice_id": "A"},
            "explanation": "숨겨야 하는 해설",
        },
    )()

    assert publisher.publish_problem_to_rag_add(problem) is True

    file_name, body_bytes, content_type = captured["files"]["file"]
    body = body_bytes.decode("utf-8")
    assert captured["url"] == "http://rag-agent/add"
    assert captured["data"]["title"] == "generated_artifact__doc_001__problem"
    assert captured["timeout"] == 4
    assert file_name == "problem_prob_001.txt"
    assert content_type == "text/plain"
    assert "artifact_id: prob_001" in body
    assert "artifact_type: problem" in body
    assert "user_id: user_001" in body
    assert "document_id: doc_001" in body
    assert "visibility: hidden_until_submission" in body
    assert "예시 문제" in body
    assert "숨겨야 하는 해설" not in body
    assert '"answer_hidden_until_submission": true' in body


def test_problem_publish_defaults_to_rag_agent_add_when_enabled(monkeypatch):
    captured = {}

    def fake_post(url, files, data, timeout):
        captured["url"] = url
        captured["data"] = data
        captured["body"] = files["file"][1].decode("utf-8")
        captured["timeout"] = timeout
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json={"title": data["title"]})

    monkeypatch.setattr(httpx, "post", fake_post)
    publisher = GeneratedArtifactPublisher(
        Settings(
            DATABASE_URL="sqlite+pysqlite://",
            RAG_AGENT_URL="http://rag-agent",
            GENERATED_ARTIFACT_PUBLISH_ENABLED=False,
            GENERATED_ARTIFACT_INDEX_URL=None,
            GENERATED_ARTIFACT_ADD_URL=None,
            GENERATED_PROBLEM_RAG_UPLOAD_ENABLED=True,
            GENERATED_ARTIFACT_TIMEOUT_SECONDS=4,
        )
    )
    problem = type(
        "ProblemStub",
        (),
        {
            "id": "prob_001",
            "user_id": "user_001",
            "document_id": "doc_001",
            "question": "업로드할 생성 문제",
            "choices": [{"id": "A", "text": "보기 A"}],
            "type": "multiple_choice",
            "difficulty": "hard",
            "bloom_level": "analyze",
            "concepts": ["개념"],
            "source_refs": [],
            "quality_status": "passed",
            "item_model_id": "case_based_application",
            "source_chunk_ids": ["chunk_001"],
            "created_at": None,
            "answer": {"choice_id": "A"},
            "explanation": "검색에 노출되면 안 되는 해설",
        },
    )()

    assert publisher.publish_problem(problem) is True

    assert captured["url"] == "http://rag-agent/add"
    assert captured["data"]["title"] == "generated_artifact__doc_001__problem"
    assert captured["timeout"] == 4
    assert "artifact_type: problem" in captured["body"]
    assert "업로드할 생성 문제" in captured["body"]
    assert "검색에 노출되면 안 되는 해설" not in captured["body"]


def test_problem_rag_upload_fallback_ignores_disabled_index_url(monkeypatch):
    captured = {}

    def fake_post(url, files, data, timeout):
        captured["url"] = url
        captured["body"] = files["file"][1].decode("utf-8")
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json={"title": data["title"]})

    monkeypatch.setattr(httpx, "post", fake_post)
    publisher = GeneratedArtifactPublisher(
        Settings(
            DATABASE_URL="sqlite+pysqlite://",
            RAG_AGENT_URL="http://rag-agent",
            GENERATED_ARTIFACT_PUBLISH_ENABLED=False,
            GENERATED_ARTIFACT_INDEX_URL="http://rag-agent/generated-artifacts/index",
            GENERATED_ARTIFACT_ADD_URL=None,
            GENERATED_PROBLEM_RAG_UPLOAD_ENABLED=True,
        )
    )

    assert publisher.publish_problem(problem_stub("prob_001")) is True

    assert captured["url"] == "http://rag-agent/add"
    assert "artifact_id: prob_001" in captured["body"]


def test_publish_problems_uses_rag_agent_add_fallback_for_generated_problems(monkeypatch):
    captured = {}

    def fake_post(url, files, data, timeout):
        captured["url"] = url
        captured["body"] = files["file"][1].decode("utf-8")
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json={"title": data["title"]})

    monkeypatch.setattr(httpx, "post", fake_post)
    publisher = GeneratedArtifactPublisher(
        Settings(
            DATABASE_URL="sqlite+pysqlite://",
            RAG_AGENT_URL="http://rag-agent/base",
            GENERATED_ARTIFACT_PUBLISH_ENABLED=False,
            GENERATED_ARTIFACT_INDEX_URL=None,
            GENERATED_ARTIFACT_ADD_URL=None,
            GENERATED_PROBLEM_RAG_UPLOAD_ENABLED=True,
            GENERATED_PROBLEM_RAG_ADD_PATH="add",
        )
    )

    result = publisher.publish_problems([problem_stub("prob_001")])

    assert result.attempted == 1
    assert result.succeeded == 1
    assert result.failed == 0
    assert captured["url"] == "http://rag-agent/base/add"
    assert "artifact_id: prob_001" in captured["body"]


def test_problem_rag_upload_fallback_does_not_publish_feedback_by_default(monkeypatch):
    def fake_post(*args, **kwargs):
        raise AssertionError("feedback should not be auto-published through generated problem fallback")

    monkeypatch.setattr(httpx, "post", fake_post)
    publisher = GeneratedArtifactPublisher(
        Settings(
            DATABASE_URL="sqlite+pysqlite://",
            RAG_AGENT_URL="http://rag-agent",
            GENERATED_ARTIFACT_PUBLISH_ENABLED=False,
            GENERATED_ARTIFACT_INDEX_URL=None,
            GENERATED_ARTIFACT_ADD_URL=None,
            GENERATED_PROBLEM_RAG_UPLOAD_ENABLED=True,
        )
    )
    feedback = Feedback(
        id="fb_001",
        submission_id="sub_001",
        problem_id="prob_001",
        user_id="user_001",
        is_correct=False,
        score=0,
        max_score=1,
        mistake_type="concept_misunderstanding",
        weak_concepts=["개념"],
        summary="요약",
        feedback="피드백 본문",
        recommended_review=["개념 다시 보기"],
        source_chunk_ids=["chunk_001"],
    )

    assert publisher.publish_feedback(feedback) is False


def test_enabled_publisher_falls_back_to_rag_add_when_index_url_is_absent(monkeypatch):
    captured = {}

    def fake_post(url, files, data, timeout):
        captured["url"] = url
        captured["data"] = data
        captured["body"] = files["file"][1].decode("utf-8")
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json={"title": data["title"]})

    monkeypatch.setattr(httpx, "post", fake_post)
    publisher = GeneratedArtifactPublisher(
        Settings(
            DATABASE_URL="sqlite+pysqlite://",
            GENERATED_ARTIFACT_PUBLISH_ENABLED=True,
            GENERATED_ARTIFACT_INDEX_URL=None,
            GENERATED_ARTIFACT_ADD_URL="http://rag-agent/add",
        )
    )
    problem = type(
        "ProblemStub",
        (),
        {
            "id": "prob_001",
            "user_id": "user_001",
            "document_id": "doc_001",
            "question": "예시 문제",
            "choices": [],
            "type": "short_answer",
            "difficulty": "hard",
            "bloom_level": "analyze",
            "concepts": ["개념"],
            "source_refs": [],
            "quality_status": "passed",
            "item_model_id": None,
            "source_chunk_ids": ["chunk_001"],
            "created_at": None,
        },
    )()

    assert publisher.publish_problem(problem) is True

    assert captured["url"] == "http://rag-agent/add"
    assert captured["data"]["title"] == "generated_artifact__doc_001__problem"
    assert "artifact_id: prob_001" in captured["body"]


def test_publisher_can_send_feedback_payload_to_rag_add_with_auth_header(monkeypatch):
    captured = {}

    def fake_post(url, files, data, timeout, headers):
        captured["url"] = url
        captured["headers"] = headers
        captured["data"] = data
        captured["body"] = files["file"][1].decode("utf-8")
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json={"title": data["title"]})

    monkeypatch.setattr(httpx, "post", fake_post)
    publisher = GeneratedArtifactPublisher(
        Settings(
            DATABASE_URL="sqlite+pysqlite://",
            GENERATED_ARTIFACT_ADD_URL="http://rag-agent/add",
            GENERATED_ARTIFACT_API_KEY="secret-key",
            GENERATED_ARTIFACT_API_KEY_HEADER="X-RAG-API-Key",
        )
    )
    problem = Problem(
        id="prob_001",
        user_id="user_001",
        document_id="doc_001",
        type="multiple_choice",
        difficulty="medium",
        bloom_level="understand",
        question="문제",
        choices=[{"id": "A", "text": "정답"}],
        answer={"choice_id": "A", "text": "정답"},
        explanation="해설",
        concepts=["개념"],
        source_chunk_ids=["chunk_001"],
        quality_status="passed",
    )
    feedback = Feedback(
        id="fb_001",
        submission_id="sub_001",
        problem_id="prob_001",
        user_id="user_001",
        is_correct=False,
        score=0,
        max_score=1,
        mistake_type="concept_misunderstanding",
        weak_concepts=["개념"],
        summary="요약",
        feedback="피드백 본문",
        recommended_review=["개념 다시 보기"],
        source_chunk_ids=["chunk_001"],
    )

    assert publisher.publish_feedback_to_rag_add(feedback, problem=problem) is True

    assert captured["url"] == "http://rag-agent/add"
    assert captured["headers"] == {"X-RAG-API-Key": "secret-key"}
    assert captured["data"]["title"] == "generated_artifact__doc_001__feedback"
    assert "artifact_id: fb_001" in captured["body"]
    assert "피드백 본문" in captured["body"]
    assert '"problem_id": "prob_001"' in captured["body"]


def test_publisher_does_not_block_when_index_api_fails_by_default(monkeypatch):
    def fake_post(url, json, timeout):
        request = httpx.Request("POST", url)
        return httpx.Response(503, request=request, json={"detail": "index unavailable"})

    monkeypatch.setattr(httpx, "post", fake_post)
    publisher = GeneratedArtifactPublisher(
        Settings(
            DATABASE_URL="sqlite+pysqlite://",
            GENERATED_ARTIFACT_PUBLISH_ENABLED=True,
            GENERATED_ARTIFACT_INDEX_URL="http://rag-agent/generated-artifacts/index",
            GENERATED_ARTIFACT_PUBLISH_FAIL_FAST=False,
        )
    )

    problem = type(
        "ProblemStub",
        (),
        {
            "id": "prob_001",
            "user_id": "user_001",
            "document_id": "doc_001",
            "question": "예시 문제",
            "choices": [],
            "type": "short_answer",
            "difficulty": "hard",
            "bloom_level": "analyze",
            "concepts": ["개념"],
            "source_refs": [],
            "quality_status": "passed",
            "item_model_id": None,
            "source_chunk_ids": ["chunk_001"],
            "created_at": None,
        },
    )()

    assert publisher.publish_problem(problem) is False


def test_publisher_can_fail_fast_when_explicitly_enabled(monkeypatch):
    def fake_post(url, json, timeout):
        request = httpx.Request("POST", url)
        return httpx.Response(503, request=request, json={"detail": "index unavailable"})

    monkeypatch.setattr(httpx, "post", fake_post)
    publisher = GeneratedArtifactPublisher(
        Settings(
            DATABASE_URL="sqlite+pysqlite://",
            GENERATED_ARTIFACT_PUBLISH_ENABLED=True,
            GENERATED_ARTIFACT_INDEX_URL="http://rag-agent/generated-artifacts/index",
            GENERATED_ARTIFACT_PUBLISH_FAIL_FAST=True,
        )
    )

    problem = type(
        "ProblemStub",
        (),
        {
            "id": "prob_001",
            "user_id": "user_001",
            "document_id": "doc_001",
            "question": "예시 문제",
            "choices": [],
            "type": "short_answer",
            "difficulty": "hard",
            "bloom_level": "analyze",
            "concepts": ["개념"],
            "source_refs": [],
            "quality_status": "passed",
            "item_model_id": None,
            "source_chunk_ids": ["chunk_001"],
            "created_at": None,
        },
    )()

    with pytest.raises(GeneratedArtifactPublishError):
        publisher.publish_problem(problem)


def test_publish_problems_returns_batch_counts(monkeypatch):
    publisher = GeneratedArtifactPublisher(
        Settings(
            DATABASE_URL="sqlite+pysqlite://",
            GENERATED_ARTIFACT_PUBLISH_ENABLED=True,
            GENERATED_ARTIFACT_INDEX_URL="http://rag-agent/generated-artifacts/index",
            GENERATED_ARTIFACT_PUBLISH_FAIL_FAST=False,
        )
    )

    clients = []

    def fake_publish(client, payload):
        clients.append(client)
        return True

    monkeypatch.setattr(publisher, "_publish_payload_with_client", fake_publish)

    result = publisher.publish_problems([problem_stub("prob_001"), problem_stub("prob_002")])

    assert result.attempted == 2
    assert result.succeeded == 2
    assert result.failed == 0
    assert result.elapsed_ms >= 0
    assert result.errors == []
    assert len(clients) == 2
    assert len({id(client) for client in clients}) == 1


def test_publish_problems_collects_failure_when_fail_fast_disabled(monkeypatch):
    publisher = GeneratedArtifactPublisher(
        Settings(
            DATABASE_URL="sqlite+pysqlite://",
            GENERATED_ARTIFACT_PUBLISH_ENABLED=True,
            GENERATED_ARTIFACT_INDEX_URL="http://rag-agent/generated-artifacts/index",
            GENERATED_ARTIFACT_PUBLISH_FAIL_FAST=False,
            GENERATED_ARTIFACT_PUBLISH_CONCURRENCY=2,
        )
    )

    def fake_publish(client, payload):
        if payload.artifact_id == "prob_fail":
            raise RuntimeError("index unavailable")
        return True

    monkeypatch.setattr(publisher, "_publish_payload_with_client", fake_publish)

    result = publisher.publish_problems([problem_stub("prob_ok"), problem_stub("prob_fail")])

    assert result.attempted == 2
    assert result.succeeded == 1
    assert result.failed == 1
    assert any("index unavailable" in error for error in result.errors)


def test_publish_problems_raises_when_fail_fast_enabled(monkeypatch):
    publisher = GeneratedArtifactPublisher(
        Settings(
            DATABASE_URL="sqlite+pysqlite://",
            GENERATED_ARTIFACT_PUBLISH_ENABLED=True,
            GENERATED_ARTIFACT_INDEX_URL="http://rag-agent/generated-artifacts/index",
            GENERATED_ARTIFACT_PUBLISH_FAIL_FAST=True,
        )
    )

    def fake_publish(client, payload):
        raise GeneratedArtifactPublishError("index unavailable")

    monkeypatch.setattr(publisher, "_publish_payload_with_client", fake_publish)

    with pytest.raises(GeneratedArtifactPublishError):
        publisher.publish_problems([problem_stub("prob_fail"), problem_stub("prob_never")])


def problem_stub(problem_id: str):
    return type(
        "ProblemStub",
        (),
        {
            "id": problem_id,
            "user_id": "user_001",
            "document_id": "doc_001",
            "question": "예시 문제",
            "choices": [],
            "type": "short_answer",
            "difficulty": "hard",
            "bloom_level": "analyze",
            "concepts": ["개념"],
            "source_refs": [],
            "quality_status": "passed",
            "item_model_id": None,
            "source_chunk_ids": ["chunk_001"],
            "created_at": None,
        },
    )()
