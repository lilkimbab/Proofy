import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.agents import FeedbackAgent, ProblemAgent, ProblemQualityChecker
from app.config import Settings
from app.models import Feedback, MistakeRemediationEvent, Problem, ProblemHintEvent, ProblemItemAnalytics, ProblemRegenerationCandidate, Submission
from app.repositories.feedback_repository import FeedbackRepository
from app.repositories.mistake_remediation_event_repository import MistakeRemediationEventRepository
from app.repositories.problem_regeneration_candidate_repository import ProblemRegenerationCandidateRepository
from app.repositories.problem_repository import ProblemRepository
from app.repositories.submission_repository import SubmissionRepository
from app.schemas.problems import GenerateProblemRequest, HintLevel, LearningState, ProblemHintRequest, SubmitAnswerRequest
from app.services.feedback_service import DuplicateSubmissionError, FeedbackService
from app.services.problem_service import ProblemService


def build_problem_service(db_session, fixed_search):
    return ProblemService(
        db=db_session,
        search_service=fixed_search,
        problem_agent=ProblemAgent(),
        quality_checker=ProblemQualityChecker(),
    )


def build_feedback_service(db_session, fixed_search):
    return FeedbackService(
        db=db_session,
        feedback_agent=FeedbackAgent(),
        search_service=fixed_search,
    )


def test_generate_multiple_choice_saves_source_chunks(db_session, fixed_search):
    service = build_problem_service(db_session, fixed_search)

    problems = service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
            difficulty="medium",
            bloom_level="understand",
        ),
    )

    assert len(problems) == 1
    assert problems[0].source_chunk_ids == ["chunk_001"]
    assert problems[0].source_evidence_snapshot[0]["chunk_id"] == "chunk_001"
    assert "F = ma" in problems[0].source_evidence_snapshot[0]["content"]
    assert problems[0].answer["choice_id"] == "A"
    assert len(problems[0].choices) == 4


def test_visual_context_is_requested_only_for_visual_problem_requirements(db_session, fixed_search):
    service = build_problem_service(db_session, fixed_search)

    assert service._visual_context_requested(
        GenerateProblemRequest(
            document_id="doc_001",
            concepts=["힙 정렬"],
            type="multiple_choice",
            user_requirements="힙 트리 그림을 보고 판단하는 문제",
        )
    )
    assert not service._visual_context_requested(
        GenerateProblemRequest(
            document_id="doc_001",
            concepts=["힙 정렬"],
            type="multiple_choice",
            user_requirements="핵심 개념 문제",
        )
    )


def test_gemini_generation_does_not_expand_hard_request_candidates(db_session, fixed_search):
    settings = Settings(LLM_PROVIDER="gemini", GEMINI_API_KEY="test-key")
    service = ProblemService(
        db=db_session,
        search_service=fixed_search,
        problem_agent=ProblemAgent(settings=settings),
        quality_checker=ProblemQualityChecker(),
        settings=settings,
    )

    candidate_count = service._candidate_generation_count(
        GenerateProblemRequest(
            document_id="doc_001",
            concepts=["힙 정렬"],
            type="short_answer",
            count=1,
            difficulty="hard",
        )
    )

    assert candidate_count == 1


def test_generated_document_id_is_normalized_to_request(db_session, fixed_search):
    service = build_problem_service(db_session, fixed_search)

    problem_data = service._with_request_document_id(
        {"document_id": "Lecture 6_ Heapsort.pdf", "question": "힙 정렬이란?"},
        GenerateProblemRequest(
            document_id="string",
            concepts=["heapsort"],
            type="short_answer",
        ),
    )

    assert problem_data["document_id"] == "string"
    assert problem_data["question"] == "힙 정렬이란?"


def test_generate_default_problem_count_uses_distinct_fallback_questions(db_session, fixed_search):
    service = build_problem_service(db_session, fixed_search)

    problems = service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
        ),
    )

    questions = [problem.question for problem in problems]
    assert len(problems) == 3
    assert len(set(questions)) == 3


def test_generate_same_request_avoids_reusing_existing_problem(db_session, fixed_search):
    service = build_problem_service(db_session, fixed_search)
    request = GenerateProblemRequest(
        document_id="doc_001",
        concepts=["뉴턴 제2법칙"],
        type="multiple_choice",
        count=1,
    )
    first_problem = service.generate_problems(user_id="user_001", request=request)[0]

    second_problem = service.generate_problems(user_id="user_001", request=request)[0]

    assert second_problem.id != first_problem.id
    assert second_problem.question != first_problem.question


def test_problem_reuse_gate_rejects_question_with_same_tokens(db_session, fixed_search):
    service = build_problem_service(db_session, fixed_search)
    previous = {
        "type": "multiple_choice",
        "question": "뉴턴 제2법칙에서 힘과 질량이 주어질 때 가속도를 구하시오.",
        "concepts": ["뉴턴 제2법칙"],
        "choices": [{"id": "A", "text": "$a = F / m$"}],
        "answer": {"choice_id": "A", "text": "$a = F / m$"},
    }
    current = {
        "type": "multiple_choice",
        "question": "뉴턴 제2법칙에서 힘과 질량이 주어질 때, 가속도를 구하시오!",
        "concepts": ["뉴턴 제2법칙"],
        "choices": [{"id": "A", "text": "$a = F / m$"}],
        "answer": {"choice_id": "A", "text": "$a = F / m$"},
    }

    assert service._is_reused_problem(
        problem_data=current,
        seen_fingerprints=[service._problem_fingerprint(previous)],
    )


def test_submit_wrong_multiple_choice_returns_feedback(db_session, fixed_search):
    problem_service = build_problem_service(db_session, fixed_search)
    feedback_service = build_feedback_service(db_session, fixed_search)
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

    assert feedback.is_correct is False
    assert feedback.score == 0
    assert feedback.mistake_type == "concept_misunderstanding"
    assert feedback.weak_concepts == ["뉴턴 제2법칙"]
    assert feedback.recommended_review == ["뉴턴 제2법칙"]
    assert feedback.learning_state == LearningState.unreported


def test_submit_correct_low_confidence_marks_fragile_mastery(db_session, fixed_search):
    problem_service = build_problem_service(db_session, fixed_search)
    feedback_service = build_feedback_service(db_session, fixed_search)
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
        request=SubmitAnswerRequest(answer={"choice_id": "A", "text": "A"}, confidence_level=1),
    )

    submission = db_session.query(Submission).filter(Submission.problem_id == problem.id).one()
    assert submission.confidence_level == 1
    assert result.feedback.learning_state == LearningState.fragile_mastery
    assert result.user_concept_update.learning_state == LearningState.fragile_mastery
    assert result.user_concept_update.mastery_updates[0].mastery == pytest.approx(0.535)


def test_submit_wrong_high_confidence_marks_high_confidence_misconception(db_session, fixed_search):
    problem_service = build_problem_service(db_session, fixed_search)
    feedback_service = build_feedback_service(db_session, fixed_search)
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
        request=SubmitAnswerRequest(answer={"choice_id": "C", "text": "C"}, confidence_level=4),
    )

    assert result.feedback.learning_state == LearningState.high_confidence_misconception
    assert result.user_concept_update.learning_state == LearningState.high_confidence_misconception
    assert result.user_concept_update.mastery_updates[0].mastery == pytest.approx(0.4)


def test_submit_multiple_choice_updates_post_use_item_analytics(db_session, fixed_search):
    problem_service = build_problem_service(db_session, fixed_search)
    feedback_service = build_feedback_service(db_session, fixed_search)
    problem = problem_service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
        ),
    )[0]

    feedback_service.submit_answer(
        problem_id=problem.id,
        user_id="user_001",
        request=SubmitAnswerRequest(answer={"choice_id": "C", "text": "C"}, elapsed_time_sec=42.5, hint_count=2),
    )

    analytics = db_session.get(ProblemItemAnalytics, problem.id)
    assert analytics is not None
    assert analytics.total_attempts == 1
    assert analytics.correct_count == 0
    assert analytics.incorrect_count == 1
    assert analytics.correct_rate == 0
    assert analytics.correct_rate_smoothed == pytest.approx(0.333)
    assert analytics.sample_size_status == "insufficient"
    assert analytics.statistics_confidence == "low"
    assert "참고용" in analytics.statistics_note
    assert analytics.quality_score_source == "item_quality"
    assert analytics.quality_score_for_review is not None
    assert analytics.average_score == 0
    assert analytics.timed_attempt_count == 1
    assert analytics.average_time_sec == 42.5
    assert analytics.hint_usage_count == 1
    assert analytics.hint_usage_rate == 1.0
    assert analytics.choice_selection_counts == {"C": 1}
    assert analytics.choice_selection_distribution == {"C": 1.0}
    assert analytics.choice_mistake_type_counts["C"]["concept_misunderstanding"] == 1
    assert analytics.common_mistake_types == ["concept_misunderstanding"]
    assert analytics.needs_review is False


def test_hint_requests_are_counted_and_reduce_correct_mastery_gain(db_session, fixed_search):
    problem_service = build_problem_service(db_session, fixed_search)
    feedback_service = build_feedback_service(db_session, fixed_search)
    problem = problem_service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
        ),
    )[0]

    for level in [HintLevel.restate_question, HintLevel.recall_concept, HintLevel.first_step_question]:
        hint = problem_service.create_problem_hint(
            user_id="user_001",
            problem_id=problem.id,
            request=ProblemHintRequest(level=level),
        )
        assert hint.answer_revealed is False

    result = feedback_service.submit_answer_with_update(
        problem_id=problem.id,
        user_id="user_001",
        request=SubmitAnswerRequest(answer={"choice_id": "A", "text": "A"}),
    )

    submission = db_session.query(Submission).filter(Submission.problem_id == problem.id).one()
    analytics = db_session.get(ProblemItemAnalytics, problem.id)
    assert db_session.query(ProblemHintEvent).count() == 3
    assert submission.hint_count == 3
    assert analytics.hint_usage_count == 1
    assert analytics.hint_usage_rate == 1.0
    assert result.user_concept_update.mastery_updates[0].mastery == pytest.approx(0.52)


def test_problem_regeneration_candidate_is_created_from_reviewed_analytics(db_session, fixed_search):
    problem_service = build_problem_service(db_session, fixed_search)
    feedback_service = build_feedback_service(db_session, fixed_search)
    candidate_repo = ProblemRegenerationCandidateRepository(db_session)
    problem = problem_service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
        ),
    )[0]
    feedback_service.submit_answer(
        problem_id=problem.id,
        user_id="user_001",
        request=SubmitAnswerRequest(answer={"choice_id": "C", "text": "C"}),
    )
    analytics = db_session.get(ProblemItemAnalytics, problem.id)
    analytics.total_attempts = 5
    analytics.correct_count = 0
    analytics.incorrect_count = 5
    analytics.correct_rate = 0
    analytics.needs_review = True
    analytics.review_reasons = ["very_low_correct_rate"]

    candidate = candidate_repo.upsert_from_analytics(problem=problem, analytics=analytics)

    assert candidate is not None
    assert candidate.problem_id == problem.id
    assert candidate.trigger_reasons == ["very_low_correct_rate"]
    assert candidate.suggested_action == "check_ambiguity_or_source_grounding"
    assert candidate.source_metrics["correct_rate"] == 0
    assert db_session.query(ProblemRegenerationCandidate).count() == 1


def test_regenerate_problem_from_candidate_creates_new_problem_and_resolves_candidate(db_session, fixed_search):
    problem_service = build_problem_service(db_session, fixed_search)
    feedback_service = build_feedback_service(db_session, fixed_search)
    candidate_repo = ProblemRegenerationCandidateRepository(db_session)
    source_problem = problem_service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
        ),
    )[0]
    feedback_service.submit_answer(
        problem_id=source_problem.id,
        user_id="user_001",
        request=SubmitAnswerRequest(answer={"choice_id": "C", "text": "C"}),
    )
    analytics = db_session.get(ProblemItemAnalytics, source_problem.id)
    analytics.total_attempts = 5
    analytics.correct_count = 0
    analytics.incorrect_count = 5
    analytics.correct_rate = 0
    analytics.needs_review = True
    analytics.review_reasons = ["very_low_correct_rate"]
    candidate = candidate_repo.upsert_from_analytics(problem=source_problem, analytics=analytics)

    regenerated_problem, resolved_candidate = problem_service.regenerate_problem_from_candidate(
        user_id="user_001",
        candidate_id=candidate.id,
    )

    assert regenerated_problem.id != source_problem.id
    assert regenerated_problem.question != source_problem.question
    assert resolved_candidate.status == "resolved"
    assert resolved_candidate.generated_problem_id == regenerated_problem.id
    assert resolved_candidate.resolution_notes
    assert db_session.query(Problem).count() == 2


def test_submit_answer_with_update_returns_user_concept_event(db_session, fixed_search):
    problem_service = build_problem_service(db_session, fixed_search)
    feedback_service = build_feedback_service(db_session, fixed_search)
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

    assert result.feedback.id == result.user_concept_update.feedback_id
    assert result.user_concept_update.problem_id == problem.id
    assert result.user_concept_update.concepts == ["뉴턴 제2법칙"]
    assert result.user_concept_update.mastery_updates[0].concept == "뉴턴 제2법칙"
    assert result.user_concept_update.mastery_updates[0].mastery == pytest.approx(0.42)


def test_wrong_followup_submission_marks_remediation_unresolved_and_repeated(db_session, fixed_search):
    problem_service = build_problem_service(db_session, fixed_search)
    feedback_service = build_feedback_service(db_session, fixed_search)
    remediation_repo = MistakeRemediationEventRepository(db_session)
    seed_problem = problem_service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
        ),
    )[0]
    source_feedback = feedback_service.submit_answer(
        problem_id=seed_problem.id,
        user_id="user_001",
        request=SubmitAnswerRequest(answer={"choice_id": "C", "text": "C"}),
    )
    followup_problem = problem_service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
        ),
    )[0]
    event = remediation_repo.create(
        {
            "user_id": "user_001",
            "source_feedback_id": source_feedback.id,
            "source_problem_id": seed_problem.id,
            "followup_problem_id": followup_problem.id,
            "target_concepts": ["뉴턴 제2법칙"],
            "target_mistake_type": "concept_misunderstanding",
        }
    )
    db_session.commit()

    repeated_choice_id = next(
        diagnostic["choice_id"]
        for diagnostic in (followup_problem.choice_diagnostics or [])
        if not diagnostic["is_correct"] and diagnostic["mistake_type"] == "concept_misunderstanding"
    )

    feedback_service.submit_answer(
        problem_id=followup_problem.id,
        user_id="user_001",
        request=SubmitAnswerRequest(answer={"choice_id": repeated_choice_id, "text": repeated_choice_id}),
    )

    db_session.refresh(event)
    assert event.resolved is False
    assert event.resolved_at is None
    assert event.repeated_count == 1
    assert db_session.query(MistakeRemediationEvent).count() == 1


def test_submit_answer_rejects_duplicate_problem_submission(db_session, fixed_search):
    problem_service = build_problem_service(db_session, fixed_search)
    feedback_service = build_feedback_service(db_session, fixed_search)
    problem = problem_service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
        ),
    )[0]

    feedback_service.submit_answer(
        problem_id=problem.id,
        user_id="user_001",
        request=SubmitAnswerRequest(answer={"choice_id": "C", "text": "C"}),
    )

    with pytest.raises(DuplicateSubmissionError, match="Problem already submitted"):
        feedback_service.submit_answer(
            problem_id=problem.id,
            user_id="user_001",
            request=SubmitAnswerRequest(answer={"choice_id": "A", "text": "A"}),
        )

    assert db_session.query(Submission).count() == 1
    assert db_session.query(Feedback).count() == 1


def test_short_answer_submission_returns_rubric_feedback(db_session, fixed_search):
    problem_service = build_problem_service(db_session, fixed_search)
    feedback_service = build_feedback_service(db_session, fixed_search)
    problem = problem_service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
            count=1,
        ),
    )[0]

    feedback = feedback_service.submit_answer(
        problem_id=problem.id,
        user_id="user_001",
        request=SubmitAnswerRequest(answer={"text": "힘과 질량의 관계를 설명한다."}),
    )

    assert feedback.max_score == 4
    assert feedback.mistake_type == "missing_key_concept"
    assert feedback.recommended_review == ["뉴턴 제2법칙"]
    assert feedback.evaluation_details is not None
    assert len(feedback.evaluation_details["rubric_results"]) == len(problem.rubric)
    assert feedback.score == sum(item["awarded_points"] for item in feedback.evaluation_details["rubric_results"])
    assert feedback.evaluation_details["confidence_reasons"]
    assert any("근거 chunk" in reason for reason in feedback.evaluation_details["confidence_reasons"])
    assert "needs_grading_review" in feedback.evaluation_details
    assert "grading_review_reasons" in feedback.evaluation_details


def test_low_ocr_short_answer_caps_rubric_confidence(db_session, fixed_search):
    problem_service = build_problem_service(db_session, fixed_search)
    feedback_service = build_feedback_service(db_session, fixed_search)
    problem = problem_service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
            count=1,
        ),
    )[0]

    feedback = feedback_service.submit_answer(
        problem_id=problem.id,
        user_id="user_001",
        request=SubmitAnswerRequest(
            answer={
                "input_mode": "tablet_ocr",
                "ocr_text": "뉴턴 제2법칙은 힘과 질량의 관계를 설명한다.",
                "ocr_confidence": 0.42,
                "tablet_image_url": "https://example.test/submission.png",
            }
        ),
    )

    assert feedback.evaluation_details["confidence"] == "low"
    assert {result["confidence"] for result in feedback.evaluation_details["rubric_results"]} == {"low"}
    assert any("rubric 항목의 판단 신뢰도가 낮아" in reason for reason in feedback.evaluation_details["confidence_reasons"])
    assert feedback.evaluation_details["needs_grading_review"] is True
    assert any("confidence" in reason for reason in feedback.evaluation_details["grading_review_reasons"])


def test_boundary_short_answer_score_marks_grading_review(db_session, fixed_search):
    feedback_service = build_feedback_service(db_session, fixed_search)

    reasons = feedback_service._short_answer_grading_review_reasons(
        feedback_payload={
            "confidence": "medium",
            "score": 2,
            "max_score": 4,
            "rubric_results": [],
        },
        chunks=fixed_search.chunks,
    )

    assert any("경계" in reason for reason in reasons)


def test_short_answer_overall_confidence_uses_lowest_rubric_confidence(db_session, fixed_search):
    feedback_service = build_feedback_service(db_session, fixed_search)
    confidence = feedback_service._short_answer_overall_confidence(
        feedback_payload={
            "confidence": "high",
            "rubric_results": [
                {"criterion": "공식 적용", "confidence": "high"},
                {"criterion": "근거 설명", "confidence": "low"},
            ],
        },
        submission=Submission(answer={"text": "F = ma"}),
        chunks=fixed_search.chunks,
    )

    assert confidence == "low"


def test_submit_short_answer_updates_missed_rubric_analytics(db_session, fixed_search):
    problem_service = build_problem_service(db_session, fixed_search)
    feedback_service = build_feedback_service(db_session, fixed_search)
    problem = problem_service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
            count=1,
        ),
    )[0]

    feedback_service.submit_answer(
        problem_id=problem.id,
        user_id="user_001",
        request=SubmitAnswerRequest(answer={"text": "힘과 질량의 관계를 설명한다."}),
    )

    analytics = db_session.get(ProblemItemAnalytics, problem.id)
    assert analytics is not None
    assert analytics.total_attempts == 1
    assert analytics.problem_type == "short_answer"
    assert analytics.mistake_type_counts["missing_key_concept"] == 1
    assert analytics.common_mistake_types == ["missing_key_concept"]
    assert analytics.missed_rubric_criteria_counts
    assert analytics.common_missed_rubric_criteria


def test_short_answer_feedback_uses_stored_source_snapshot(db_session, fixed_search):
    class BrokenBatchSearchService:
        def search_chunks(self, **kwargs):
            return fixed_search.chunks

        def get_chunks_by_ids(self, **kwargs):
            raise AssertionError("stored source evidence snapshot should avoid batch lookup")

    problem_service = build_problem_service(db_session, BrokenBatchSearchService())
    problem = problem_service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
            count=1,
        ),
    )[0]
    feedback_service = build_feedback_service(db_session, BrokenBatchSearchService())

    feedback = feedback_service.submit_answer(
        problem_id=problem.id,
        user_id="user_001",
        request=SubmitAnswerRequest(answer={"text": "뉴턴 제2법칙은 F = ma라고 설명한다."}),
    )

    assert feedback.source_chunk_ids == ["chunk_001"]


def test_quality_checker_rejects_problem_without_source_chunks():
    checker = ProblemQualityChecker()

    is_valid, errors = checker.validate(
        {
            "document_id": "doc_001",
            "type": "multiple_choice",
            "difficulty": "medium",
            "bloom_level": "understand",
            "question": "질문",
            "choices": [
                {"id": "A", "text": "A"},
                {"id": "B", "text": "B"},
                {"id": "C", "text": "C"},
                {"id": "D", "text": "D"},
            ],
            "answer": {"choice_id": "A"},
            "explanation": "해설",
            "choice_explanations": {"A": "정답"},
            "concepts": ["개념"],
            "source_chunk_ids": [],
        }
    )

    assert is_valid is False
    assert "source_chunk_ids is required" in errors


def test_feedback_is_unique_per_submission(db_session):
    problem = Problem(
        user_id="user_001",
        document_id="doc_001",
        type="multiple_choice",
        difficulty="medium",
        bloom_level="understand",
        question="질문",
        choices=[{"id": "A", "text": "A"}, {"id": "B", "text": "B"}, {"id": "C", "text": "C"}, {"id": "D", "text": "D"}],
        answer={"choice_id": "A", "text": "A"},
        explanation="해설",
        choice_explanations={"A": "정답", "B": "오답", "C": "오답", "D": "오답"},
        rubric=None,
        concepts=["개념"],
        source_chunk_ids=["chunk_001"],
        quality_status="passed",
    )
    db_session.add(problem)
    db_session.commit()

    submission = Submission(problem_id=problem.id, user_id="user_001", answer={"choice_id": "A"})
    db_session.add(submission)
    db_session.commit()

    first_feedback = feedback_for_submission(submission_id=submission.id, problem_id=problem.id)
    db_session.add(first_feedback)
    db_session.commit()

    second_feedback = feedback_for_submission(submission_id=submission.id, problem_id=problem.id)
    db_session.add(second_feedback)
    try:
        db_session.commit()
    except IntegrityError:
        db_session.rollback()
    else:
        raise AssertionError("Expected unique feedback per submission")


def test_problem_repository_validates_storage_contract_before_save(db_session):
    repo = ProblemRepository(db_session)

    with pytest.raises(ValidationError, match="choice_explanations"):
        repo.create(
            user_id="user_001",
            problem_data={
                "document_id": "doc_001",
                "type": "multiple_choice",
                "difficulty": "medium",
                "bloom_level": "understand",
                "question": "질문",
                "choices": [
                    {"id": "A", "text": "A"},
                    {"id": "B", "text": "B"},
                    {"id": "C", "text": "C"},
                    {"id": "D", "text": "D"},
                ],
                "answer": {"choice_id": "A", "text": "A"},
                "explanation": "해설",
                "choice_explanations": None,
                "rubric": None,
                "concepts": ["개념"],
                "source_chunk_ids": ["chunk_001"],
                "quality_status": "passed",
            },
        )

    assert db_session.query(Problem).count() == 0


def test_submission_repository_validates_answer_contract_before_save(db_session):
    repo = SubmissionRepository(db_session)

    with pytest.raises(ValidationError, match="choice_id or text is required"):
        repo.create(
            problem_id="prob_001",
            user_id="user_001",
            answer={},
            solution_steps=None,
        )

    assert db_session.query(Submission).count() == 0


def test_feedback_repository_validates_score_contract_before_save(db_session):
    repo = FeedbackRepository(db_session)

    with pytest.raises(ValidationError, match="score cannot exceed max_score"):
        repo.create(
            {
                "submission_id": "sub_001",
                "problem_id": "prob_001",
                "user_id": "user_001",
                "is_correct": False,
                "score": 2,
                "max_score": 1,
                "mistake_type": "concept_misunderstanding",
                "weak_concepts": ["개념"],
                "summary": "점수가 잘못됐다.",
                "feedback": "정답 여부: 아직 정답은 아니야.\n헷갈린 지점: 점수 계약.\n올바른 개념: 총점을 넘으면 안 된다.\n복습 추천: 개념",
                "recommended_review": ["개념"],
                "source_chunk_ids": ["chunk_001"],
            }
        )

    assert db_session.query(Feedback).count() == 0


def feedback_for_submission(*, submission_id, problem_id):
    return Feedback(
        submission_id=submission_id,
        problem_id=problem_id,
        user_id="user_001",
        is_correct=True,
        score=1,
        max_score=1,
        mistake_type="none",
        weak_concepts=[],
        summary="정답이야.",
        feedback="정답 여부: 정답이야.\n헷갈린 지점: 없어.\n올바른 개념: 좋아.\n복습 추천: 넘어가도 괜찮아.",
        recommended_review=[],
        source_chunk_ids=["chunk_001"],
    )
