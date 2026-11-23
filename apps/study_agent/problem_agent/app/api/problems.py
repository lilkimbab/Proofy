from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import (
    get_assessment_session_readiness_service,
    get_feedback_service,
    get_generated_artifact_publisher,
    get_learning_content_repository,
    get_problem_service,
    get_user_id,
)
from app.llm import LLMServiceError
from app.models import AssessmentSession, Feedback, Problem
from app.repositories.feedback_action_event_repository import FeedbackActionEventRepository
from app.repositories.learning_content_repository import LearningContentRepository
from app.repositories.mistake_remediation_event_repository import MistakeRemediationEventRepository
from app.repositories.problem_regeneration_candidate_repository import ProblemRegenerationCandidateRepository
from app.repositories.usage_ledger_repository import UsageLedgerRepository
from app.repositories.user_quality_report_repository import UserQualityReportRepository
from app.schemas import (
    AssessmentReadinessStatus,
    AssessmentSessionConceptResult,
    AssessmentSessionDetailResponse,
    AssessmentSessionGenerateRequest,
    AssessmentSessionGenerateResponse,
    AssessmentSessionHistoryAttempt,
    AssessmentSessionHistoryResponse,
    AssessmentSessionProblemResult,
    AssessmentSessionReportResponse,
    AssessmentSessionReadinessReport,
    AssessmentSessionStatus,
    AssessmentSessionSubmitRequest,
    AssessmentSessionSubmitResponse,
    ChoiceFeedbackDiagnostic,
    FeedbackActionEventListResponse,
    FeedbackActionEventRequest,
    FeedbackActionEventResponse,
    FeedbackResponse,
    GenerationQualitySummary,
    GenerateProblemRequest,
    GenerateProblemResponse,
    ProblemItemAnalyticsListResponse,
    ProblemItemAnalyticsResponse,
    ProblemHintRequest,
    ProblemHintResponse,
    ProblemRegenerationCandidateListResponse,
    ProblemRegenerationCandidateResponse,
    ProblemRegenerationResultResponse,
    ProblemResponse,
    ProblemTemplateAnalyticsListResponse,
    ProblemTemplateAnalyticsResponse,
    QualityReportRequest,
    QualityReportResponse,
    QualityReportTargetType,
    SubmitAnswerRequest,
    UsageLedgerListResponse,
    UsageLedgerResponse,
    UsageLedgerSummaryResponse,
)
from app.schemas.learning_voice import FeedbackCopyInput, FeedbackSituation, NextActionType
from app.agents.feedback_agent import FeedbackAgent
from app.services.feedback_service import DuplicateSubmissionError, FeedbackService
from app.services.generated_artifact_publisher import GeneratedArtifactPublisher
from app.services.learning_voice_renderer import LearningVoiceRenderer
from app.services.assessment_session_readiness_service import AssessmentSessionReadinessService
from app.services.problem_service import ProblemService
from app.services.search_service import SearchAgentError

router = APIRouter(prefix="/api", tags=["problems"])
voice_renderer = LearningVoiceRenderer()
diagnostic_agent = FeedbackAgent()


def to_problem_response(
    problem: Problem,
    *,
    include_solution: bool,
    include_internal: bool = False,
) -> ProblemResponse:
    return ProblemResponse(
        id=problem.id,
        document_id=problem.document_id,
        type=problem.type,
        difficulty=problem.difficulty,
        bloom_level=problem.bloom_level,
        question=problem.question,
        choices=problem.choices,
        concepts=problem.concepts,
        source_chunk_ids=problem.source_chunk_ids,
        source_refs=problem.source_refs,
        source_grounding_notes=problem.source_grounding_notes or [],
        quality_status=problem.quality_status,
        created_at=problem.created_at,
        item_model_id=problem.item_model_id,
        item_design_brief=problem.item_design_brief if include_internal else None,
        difficulty_profile=problem.difficulty_profile if include_internal else None,
        teacher_review_checklist=problem.teacher_review_checklist if include_internal else None,
        professor_grade_score=problem.professor_grade_score if include_internal else None,
        student_response_simulation=problem.student_response_simulation if include_internal else None,
        explanation=problem.explanation if include_solution else None,
        answer=problem.answer if include_solution else None,
        choice_explanations=problem.choice_explanations if include_solution else None,
        choice_diagnostics=problem.choice_diagnostics if include_solution else None,
        rubric=problem.rubric if include_solution else None,
    )


def to_feedback_response(feedback: Feedback) -> FeedbackResponse:
    copy_input = FeedbackCopyInput(
        situation=_feedback_situation(feedback),
        concept=_feedback_concept(feedback),
        mistake_type=feedback.mistake_type,
        evidence_summary=_feedback_evidence_summary(feedback),
        confidence=_feedback_copy_confidence(feedback),
        next_action=_feedback_next_action(feedback),
    )
    response = FeedbackResponse.model_validate(feedback)
    return response.model_copy(
        update={
            "display_copy": voice_renderer.render_feedback(copy_input),
            "choice_diagnostic": _feedback_choice_diagnostic(feedback),
        }
    )


def _feedback_choice_diagnostic(feedback: Feedback) -> ChoiceFeedbackDiagnostic | None:
    if feedback.problem is None or feedback.submission is None:
        return None
    diagnostic = diagnostic_agent.multiple_choice_diagnostic_payload(
        problem=feedback.problem,
        submission=feedback.submission,
    )
    if diagnostic is None:
        return None
    return ChoiceFeedbackDiagnostic.model_validate(diagnostic)


def _feedback_situation(feedback: Feedback) -> FeedbackSituation:
    if feedback.is_correct:
        return FeedbackSituation.correct
    if 0 < feedback.score < feedback.max_score:
        return FeedbackSituation.partially_correct
    return FeedbackSituation.wrong


def _feedback_concept(feedback: Feedback) -> str | None:
    for concept in [*feedback.weak_concepts, *feedback.recommended_review]:
        if concept and concept.strip():
            return concept.strip()
    return None


def _feedback_evidence_summary(feedback: Feedback) -> str | None:
    if feedback.is_correct:
        concept = _feedback_concept(feedback)
        if concept:
            return f"특히 {concept}의 조건을 놓치지 않은 점이 좋아요."
        return "조건을 놓치지 않고 잘 골랐어요."

    for line in str(feedback.feedback or "").splitlines():
        label, _, value = line.partition(":")
        if label.strip() == "올바른 개념" and value.strip():
            return _soften_feedback_line(value.strip())
    if feedback.summary:
        return _soften_feedback_line(feedback.summary)
    return None


def _feedback_copy_confidence(feedback: Feedback) -> str:
    if isinstance(feedback.evaluation_details, dict):
        confidence = feedback.evaluation_details.get("confidence")
        if confidence in {"low", "medium", "high"}:
            return str(confidence)
    return "high" if feedback.source_chunk_ids else "medium"


def _feedback_next_action(feedback: Feedback) -> NextActionType:
    if feedback.is_correct:
        return NextActionType.solve_similar
    if feedback.recommended_review:
        return NextActionType.review_concept_card
    return NextActionType.solve_similar


def _soften_feedback_line(text: str) -> str:
    return (
        text.replace("정답 여부:", "")
        .replace("헷갈린 지점:", "")
        .replace("올바른 개념:", "")
        .replace("복습 추천:", "")
        .replace("해당 개념", "이 개념")
        .strip()
    )


def _get_report_candidate_problem(
    *,
    request: QualityReportRequest,
    user_id: str,
    db: Session,
    learning_content_repository: LearningContentRepository,
) -> Problem | None:
    if request.target_type == QualityReportTargetType.problem:
        problem = db.get(Problem, request.target_id)
        if problem is None or problem.user_id != user_id:
            raise HTTPException(status_code=404, detail="Report target not found")
        return problem

    if request.target_type == QualityReportTargetType.feedback:
        feedback = db.get(Feedback, request.target_id)
        if feedback is None or feedback.user_id != user_id:
            raise HTTPException(status_code=404, detail="Report target not found")
        return feedback.problem

    if request.target_type == QualityReportTargetType.learning_content:
        content = learning_content_repository.get(request.target_id)
        if content is None or content.user_id != user_id:
            raise HTTPException(status_code=404, detail="Report target not found")
        return None

    raise HTTPException(status_code=422, detail="Unsupported report target type")


def _validate_feedback_action_targets(
    *,
    request: FeedbackActionEventRequest,
    user_id: str,
    db: Session,
    learning_content_repository: LearningContentRepository,
) -> None:
    if request.target_problem_id:
        problem = db.get(Problem, request.target_problem_id)
        if problem is None or problem.user_id != user_id:
            raise HTTPException(status_code=404, detail="Target problem not found")
    if request.target_content_id:
        content = learning_content_repository.get(request.target_content_id)
        if content is None or content.user_id != user_id:
            raise HTTPException(status_code=404, detail="Target learning content not found")


def _link_feedback_action_to_remediation(
    *,
    feedback: Feedback,
    request: FeedbackActionEventRequest,
    db: Session,
) -> None:
    if request.event_type.value != "followup_problem_completed":
        return
    if request.target_problem_id is None or request.is_successful is None:
        return
    MistakeRemediationEventRepository(db).record_followup_action_result(
        user_id=feedback.user_id,
        source_feedback_id=feedback.id,
        followup_problem_id=request.target_problem_id,
        is_successful=request.is_successful,
    )


def _create_assessment_session(
    *,
    db: Session,
    user_id: str,
    request: GenerateProblemRequest,
    result,
    readiness: AssessmentSessionReadinessReport,
    retry_of_session_id: str | None = None,
) -> AssessmentSession:
    session = AssessmentSession(
        user_id=user_id,
        document_id=request.document_id,
        status=AssessmentSessionStatus.generated.value,
        problem_ids=[problem.id for problem in result.problems],
        readiness=readiness.model_dump(mode="json"),
        generation_metadata={
            "learning_task_strategy": result.learning_task_strategy.model_dump(mode="json"),
            "material_readiness": result.material_readiness.model_dump(mode="json"),
            "blueprint": result.blueprint.model_dump(mode="json"),
            "high_rigor_profile": result.high_rigor_profile.model_dump(mode="json"),
            "quality_summary": result.quality_summary.model_dump(mode="json"),
            "time_limit_seconds": getattr(request, "time_limit_seconds", None),
            "generation_request": request.model_dump(mode="json"),
            "retry_of_session_id": retry_of_session_id,
        },
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _assessment_session_or_404(*, db: Session, session_id: str, user_id: str) -> AssessmentSession:
    session = db.get(AssessmentSession, session_id)
    if session is None or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Assessment session not found")
    return session


def _assessment_session_problems(*, db: Session, session: AssessmentSession) -> list[Problem]:
    if not session.problem_ids:
        return []
    problems = db.query(Problem).filter(Problem.id.in_(session.problem_ids)).all()
    problem_by_id = {problem.id: problem for problem in problems}
    return [problem_by_id[problem_id] for problem_id in session.problem_ids if problem_id in problem_by_id]


def _validate_assessment_session_submit_request(
    *,
    db: Session,
    session: AssessmentSession,
    request: AssessmentSessionSubmitRequest,
) -> None:
    problems = _assessment_session_problems(db=db, session=session)
    if len(problems) != len(session.problem_ids):
        raise HTTPException(status_code=409, detail="Assessment session contains missing problems")
    problem_by_id = {problem.id: problem for problem in problems}
    for item in request.submissions:
        problem = problem_by_id[item.problem_id]
        if problem.user_id != session.user_id:
            raise HTTPException(status_code=404, detail="Assessment session problem not found")
        if problem.type == "multiple_choice":
            if not item.answer.choice_id:
                raise HTTPException(status_code=422, detail="choice_id is required for multiple_choice problems")
            choice_ids = {choice.get("id") for choice in (problem.choices or [])}
            if item.answer.choice_id not in choice_ids:
                raise HTTPException(status_code=422, detail="choice_id must exist in problem choices")
        if problem.type == "short_answer" and not item.answer.text:
            raise HTTPException(status_code=422, detail="text is required for short_answer problems")


def _assessment_session_readiness(session: AssessmentSession) -> AssessmentSessionReadinessReport | None:
    if not session.readiness:
        return None
    return AssessmentSessionReadinessReport.model_validate(session.readiness)


def _assessment_session_quality_summary(session: AssessmentSession) -> GenerationQualitySummary | None:
    quality_summary = (session.generation_metadata or {}).get("quality_summary")
    if not quality_summary:
        return None
    return GenerationQualitySummary.model_validate(quality_summary)


def _assessment_session_time_limit_seconds(session: AssessmentSession) -> int | None:
    value = (session.generation_metadata or {}).get("time_limit_seconds")
    if value is None:
        return None
    return int(value)


def _assessment_session_retry_of_session_id(session: AssessmentSession) -> str | None:
    value = (session.generation_metadata or {}).get("retry_of_session_id")
    return str(value) if value else None


def _assessment_session_retry_request(*, db: Session, session: AssessmentSession) -> AssessmentSessionGenerateRequest:
    generation_request = (session.generation_metadata or {}).get("generation_request")
    if generation_request:
        return AssessmentSessionGenerateRequest.model_validate(generation_request)

    problems = _assessment_session_problems(db=db, session=session)
    if not problems:
        raise HTTPException(status_code=409, detail="Assessment session contains no problems to retry")
    first_problem = problems[0]
    concepts = list(dict.fromkeys(concept for problem in problems for concept in problem.concepts))
    return AssessmentSessionGenerateRequest(
        document_id=session.document_id,
        concepts=concepts or first_problem.concepts,
        type=first_problem.type,
        count=len(session.problem_ids),
        difficulty=first_problem.difficulty,
        bloom_level=first_problem.bloom_level,
        time_limit_seconds=_assessment_session_time_limit_seconds(session),
    )


def _assessment_session_report(
    *,
    db: Session,
    session: AssessmentSession,
    include_comparison: bool = True,
) -> AssessmentSessionReportResponse:
    feedbacks = []
    if session.problem_ids:
        feedbacks = (
            db.query(Feedback)
            .filter(Feedback.user_id == session.user_id, Feedback.problem_id.in_(session.problem_ids))
            .all()
        )
    feedback_by_problem_id = {feedback.problem_id: feedback for feedback in feedbacks}
    problem_by_id = {problem.id: problem for problem in _assessment_session_problems(db=db, session=session)}
    concept_stats: dict[str, dict] = {}
    results: list[AssessmentSessionProblemResult] = []
    weak_concepts: list[str] = []
    recommended_review: list[str] = []
    correct_count = 0
    total_score = 0.0
    max_score = 0.0
    elapsed_times: list[float] = []

    for problem_id in session.problem_ids:
        problem = problem_by_id.get(problem_id)
        problem_concepts = list(problem.concepts if problem is not None else [])
        for concept in problem_concepts:
            stat = concept_stats.setdefault(
                concept,
                {
                    "problem_count": 0,
                    "submitted_count": 0,
                    "correct_count": 0,
                    "total_score": 0.0,
                    "max_score": 0.0,
                },
            )
            stat["problem_count"] += 1
        feedback = feedback_by_problem_id.get(problem_id)
        if feedback is None:
            results.append(AssessmentSessionProblemResult(problem_id=problem_id, submitted=False))
            continue
        correct_count += 1 if feedback.is_correct else 0
        total_score += feedback.score
        max_score += feedback.max_score
        for concept in problem_concepts:
            stat = concept_stats[concept]
            stat["submitted_count"] += 1
            stat["correct_count"] += 1 if feedback.is_correct else 0
            stat["total_score"] += feedback.score
            stat["max_score"] += feedback.max_score
        if feedback.submission and feedback.submission.elapsed_time_sec is not None:
            elapsed_times.append(float(feedback.submission.elapsed_time_sec))
        weak_concepts.extend(feedback.weak_concepts)
        recommended_review.extend(feedback.recommended_review)
        results.append(
            AssessmentSessionProblemResult(
                problem_id=problem_id,
                submitted=True,
                feedback_id=feedback.id,
                is_correct=feedback.is_correct,
                score=feedback.score,
                max_score=feedback.max_score,
                mistake_type=feedback.mistake_type,
                weak_concepts=feedback.weak_concepts,
                recommended_review=feedback.recommended_review,
            )
        )

    problem_count = len(session.problem_ids)
    submitted_count = len(feedback_by_problem_id)
    completion_ratio = submitted_count / problem_count if problem_count else 0.0
    score_ratio = total_score / max_score if max_score > 0 else None
    total_elapsed_time_sec = round(sum(elapsed_times), 2) if elapsed_times else None
    time_limit_seconds = _assessment_session_time_limit_seconds(session)
    time_remaining_seconds = None
    time_over_limit = False
    if time_limit_seconds is not None and total_elapsed_time_sec is not None:
        time_remaining_seconds = max(0.0, round(float(time_limit_seconds) - total_elapsed_time_sec, 2))
        time_over_limit = total_elapsed_time_sec > time_limit_seconds
    status = (
        AssessmentSessionStatus.submitted
        if problem_count > 0 and submitted_count == problem_count
        else AssessmentSessionStatus(session.status)
    )
    weak_concepts = list(dict.fromkeys(weak_concepts))
    recommended_review = list(dict.fromkeys(recommended_review))
    concept_results: list[AssessmentSessionConceptResult] = []
    strong_concepts: list[str] = []
    for concept, stat in concept_stats.items():
        concept_max_score = float(stat["max_score"])
        concept_score_ratio = float(stat["total_score"]) / concept_max_score if concept_max_score > 0 else None
        if int(stat["submitted_count"]) == 0:
            concept_status = "incomplete"
        elif concept_score_ratio is not None and concept_score_ratio >= 0.8:
            concept_status = "strong"
            strong_concepts.append(concept)
        else:
            concept_status = "needs_review"
            weak_concepts.append(concept)
            recommended_review.append(concept)
        concept_results.append(
            AssessmentSessionConceptResult(
                concept=concept,
                problem_count=int(stat["problem_count"]),
                submitted_count=int(stat["submitted_count"]),
                correct_count=int(stat["correct_count"]),
                total_score=round(float(stat["total_score"]), 2),
                max_score=round(concept_max_score, 2),
                score_ratio=round(concept_score_ratio, 4) if concept_score_ratio is not None else None,
                status=concept_status,
            )
        )
    weak_concepts = list(dict.fromkeys(weak_concepts))
    recommended_review = list(dict.fromkeys(recommended_review))
    if submitted_count < problem_count:
        next_step = "아직 제출하지 않은 문제가 있어요. 남은 문제까지 풀면 전체 리포트를 볼 수 있어요."
    elif time_over_limit:
        next_step = "정답률과 함께 시간을 줄이는 연습이 필요해요. 같은 범위로 제한 시간을 조금 짧게 잡고 다시 풀어보세요."
    elif weak_concepts:
        next_step = f"{weak_concepts[0]}부터 다시 확인하고 비슷한 문제를 한 번 더 풀어보세요."
    else:
        next_step = "전체 세트를 잘 마쳤어요. 같은 자료에서 조금 더 어려운 응용 문제로 이어가도 좋아요."

    retry_of_session_id = _assessment_session_retry_of_session_id(session)
    previous_score_ratio = None
    score_delta = None
    previous_completion_ratio = None
    completion_delta = None
    concept_score_deltas: dict[str, float] = {}
    if include_comparison and retry_of_session_id:
        previous_session = db.get(AssessmentSession, retry_of_session_id)
        if previous_session is not None and previous_session.user_id == session.user_id:
            previous_report = _assessment_session_report(
                db=db,
                session=previous_session,
                include_comparison=False,
            )
            previous_score_ratio = previous_report.score_ratio
            previous_completion_ratio = previous_report.completion_ratio
            if score_ratio is not None and previous_score_ratio is not None:
                score_delta = round(score_ratio - previous_score_ratio, 4)
            completion_delta = round(completion_ratio - previous_completion_ratio, 4)
            previous_concept_ratios = {
                result.concept: result.score_ratio
                for result in previous_report.concept_results
                if result.score_ratio is not None
            }
            for result in concept_results:
                previous_ratio = previous_concept_ratios.get(result.concept)
                if result.score_ratio is not None and previous_ratio is not None:
                    concept_score_deltas[result.concept] = round(result.score_ratio - previous_ratio, 4)

    return AssessmentSessionReportResponse(
        session_id=session.id,
        status=status,
        document_id=session.document_id,
        retry_of_session_id=retry_of_session_id,
        previous_score_ratio=previous_score_ratio,
        score_delta=score_delta,
        previous_completion_ratio=previous_completion_ratio,
        completion_delta=completion_delta,
        concept_score_deltas=concept_score_deltas,
        problem_count=problem_count,
        submitted_count=submitted_count,
        correct_count=correct_count,
        total_score=round(total_score, 2),
        max_score=round(max_score, 2),
        score_ratio=round(score_ratio, 4) if score_ratio is not None else None,
        completion_ratio=round(completion_ratio, 4),
        total_elapsed_time_sec=total_elapsed_time_sec,
        time_limit_seconds=time_limit_seconds,
        time_remaining_seconds=time_remaining_seconds,
        time_over_limit=time_over_limit,
        strong_concepts=strong_concepts,
        weak_concepts=weak_concepts,
        recommended_review=recommended_review,
        concept_results=concept_results,
        results=results,
        next_step=next_step,
        created_at=session.created_at,
        submitted_at=session.submitted_at,
    )


def _assessment_session_detail(*, db: Session, session: AssessmentSession) -> AssessmentSessionDetailResponse:
    problems = _assessment_session_problems(db=db, session=session)
    report = _assessment_session_report(db=db, session=session)
    return AssessmentSessionDetailResponse(
        session_id=session.id,
        status=report.status,
        document_id=session.document_id,
        retry_of_session_id=_assessment_session_retry_of_session_id(session),
        problem_ids=session.problem_ids,
        problems=[to_problem_response(problem, include_solution=False, include_internal=False) for problem in problems],
        readiness=_assessment_session_readiness(session),
        quality_summary=_assessment_session_quality_summary(session),
        time_limit_seconds=_assessment_session_time_limit_seconds(session),
        submitted_count=report.submitted_count,
        created_at=session.created_at,
        submitted_at=session.submitted_at,
        report=report,
    )


def _assessment_session_history(*, db: Session, session: AssessmentSession) -> AssessmentSessionHistoryResponse:
    user_sessions = db.query(AssessmentSession).filter(AssessmentSession.user_id == session.user_id).all()
    session_by_id = {item.id: item for item in user_sessions}

    root = session
    seen: set[str] = set()
    while True:
        parent_id = _assessment_session_retry_of_session_id(root)
        if not parent_id or parent_id in seen:
            break
        parent = session_by_id.get(parent_id)
        if parent is None:
            break
        seen.add(root.id)
        root = parent

    children_by_parent_id: dict[str, list[AssessmentSession]] = {}
    for item in user_sessions:
        parent_id = _assessment_session_retry_of_session_id(item)
        if not parent_id:
            continue
        children_by_parent_id.setdefault(parent_id, []).append(item)
    for children in children_by_parent_id.values():
        children.sort(key=lambda item: (item.created_at, item.id))

    chain: list[AssessmentSession] = []

    def collect(item: AssessmentSession) -> None:
        chain.append(item)
        for child in children_by_parent_id.get(item.id, []):
            collect(child)

    collect(root)

    reports = {
        item.id: _assessment_session_report(db=db, session=item, include_comparison=False)
        for item in chain
    }
    attempts: list[AssessmentSessionHistoryAttempt] = []
    for index, item in enumerate(chain, start=1):
        report = reports[item.id]
        parent_report = reports.get(_assessment_session_retry_of_session_id(item) or "")
        score_delta_from_previous = None
        if report.score_ratio is not None and parent_report and parent_report.score_ratio is not None:
            score_delta_from_previous = round(report.score_ratio - parent_report.score_ratio, 4)
        attempts.append(
            AssessmentSessionHistoryAttempt(
                session_id=item.id,
                retry_of_session_id=_assessment_session_retry_of_session_id(item),
                attempt_number=index,
                status=report.status,
                score_ratio=report.score_ratio,
                score_delta_from_previous=score_delta_from_previous,
                completion_ratio=report.completion_ratio,
                submitted_count=report.submitted_count,
                problem_count=report.problem_count,
                strong_concepts=report.strong_concepts,
                weak_concepts=report.weak_concepts,
                created_at=item.created_at,
                submitted_at=item.submitted_at,
            )
        )

    scored_attempts = [attempt for attempt in attempts if attempt.score_ratio is not None]
    best_attempt = max(scored_attempts, key=lambda attempt: attempt.score_ratio) if scored_attempts else None
    first_score = scored_attempts[0].score_ratio if scored_attempts else None
    latest_score = scored_attempts[-1].score_ratio if scored_attempts else None
    latest_score_delta_from_first = None
    trend = "insufficient_data"
    if first_score is not None and latest_score is not None and len(scored_attempts) >= 2:
        latest_score_delta_from_first = round(latest_score - first_score, 4)
        if latest_score_delta_from_first > 0:
            trend = "improved"
        elif latest_score_delta_from_first < 0:
            trend = "declined"
        else:
            trend = "unchanged"

    return AssessmentSessionHistoryResponse(
        root_session_id=root.id,
        current_session_id=session.id,
        attempt_count=len(attempts),
        best_session_id=best_attempt.session_id if best_attempt else None,
        best_score_ratio=best_attempt.score_ratio if best_attempt else None,
        latest_score_ratio=latest_score,
        latest_score_delta_from_first=latest_score_delta_from_first,
        trend=trend,
        attempts=attempts,
    )


@router.post("/problems/generate", response_model=GenerateProblemResponse)
def generate_problems(
    request: GenerateProblemRequest,
    user_id: str = Depends(get_user_id),
    service: ProblemService = Depends(get_problem_service),
) -> GenerateProblemResponse:
    try:
        result = service.generate_problem_batch(user_id=user_id, request=request)
    except SearchAgentError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return GenerateProblemResponse(
        problems=[
            to_problem_response(problem, include_solution=False, include_internal=False)
            for problem in result.problems
        ],
        learning_task_strategy=result.learning_task_strategy,
        material_readiness=result.material_readiness,
        blueprint=result.blueprint,
        high_rigor_profile=result.high_rigor_profile,
        quality_summary=result.quality_summary,
    )


@router.post("/assessment-sessions/readiness", response_model=AssessmentSessionReadinessReport)
def evaluate_assessment_session_readiness(
    request: GenerateProblemRequest,
    user_id: str = Depends(get_user_id),
    service: AssessmentSessionReadinessService = Depends(get_assessment_session_readiness_service),
) -> AssessmentSessionReadinessReport:
    try:
        return service.evaluate(user_id=user_id, request=request)
    except SearchAgentError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/assessment-sessions/generate", response_model=AssessmentSessionGenerateResponse)
def generate_assessment_session(
    request: AssessmentSessionGenerateRequest,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
    readiness_service: AssessmentSessionReadinessService = Depends(get_assessment_session_readiness_service),
    problem_service: ProblemService = Depends(get_problem_service),
) -> AssessmentSessionGenerateResponse:
    try:
        readiness = readiness_service.evaluate(user_id=user_id, request=request)
        if readiness.status == AssessmentReadinessStatus.not_ready:
            raise ValueError("; ".join(readiness.blocking_reasons) or "Assessment session is not ready")
        result = problem_service.generate_problem_batch(user_id=user_id, request=request)
        session = _create_assessment_session(
            db=db,
            user_id=user_id,
            request=request,
            result=result,
            readiness=readiness,
        )
    except SearchAgentError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AssessmentSessionGenerateResponse(
        session_id=session.id,
        status=AssessmentSessionStatus(session.status),
        retry_of_session_id=_assessment_session_retry_of_session_id(session),
        created_at=session.created_at,
        time_limit_seconds=_assessment_session_time_limit_seconds(session),
        problems=[
            to_problem_response(problem, include_solution=False, include_internal=False)
            for problem in result.problems
        ],
        readiness=readiness,
        learning_task_strategy=result.learning_task_strategy,
        material_readiness=result.material_readiness,
        blueprint=result.blueprint,
        high_rigor_profile=result.high_rigor_profile,
        quality_summary=result.quality_summary,
    )


@router.post("/assessment-sessions/{session_id}/retry", response_model=AssessmentSessionGenerateResponse)
def retry_assessment_session(
    session_id: str,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
    readiness_service: AssessmentSessionReadinessService = Depends(get_assessment_session_readiness_service),
    problem_service: ProblemService = Depends(get_problem_service),
) -> AssessmentSessionGenerateResponse:
    source_session = _assessment_session_or_404(db=db, session_id=session_id, user_id=user_id)
    source_report = _assessment_session_report(db=db, session=source_session)
    if source_report.submitted_count == 0:
        raise HTTPException(status_code=422, detail="Assessment session retry requires at least one submitted answer")
    request = _assessment_session_retry_request(db=db, session=source_session)
    try:
        readiness = readiness_service.evaluate(user_id=user_id, request=request)
        if readiness.status == AssessmentReadinessStatus.not_ready:
            raise ValueError("; ".join(readiness.blocking_reasons) or "Assessment session is not ready")
        result = problem_service.generate_problem_batch(user_id=user_id, request=request)
        session = _create_assessment_session(
            db=db,
            user_id=user_id,
            request=request,
            result=result,
            readiness=readiness,
            retry_of_session_id=source_session.id,
        )
    except SearchAgentError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AssessmentSessionGenerateResponse(
        session_id=session.id,
        status=AssessmentSessionStatus(session.status),
        retry_of_session_id=source_session.id,
        created_at=session.created_at,
        time_limit_seconds=_assessment_session_time_limit_seconds(session),
        problems=[
            to_problem_response(problem, include_solution=False, include_internal=False)
            for problem in result.problems
        ],
        readiness=readiness,
        learning_task_strategy=result.learning_task_strategy,
        material_readiness=result.material_readiness,
        blueprint=result.blueprint,
        high_rigor_profile=result.high_rigor_profile,
        quality_summary=result.quality_summary,
    )


@router.get("/assessment-sessions/{session_id}/history", response_model=AssessmentSessionHistoryResponse)
def get_assessment_session_history(
    session_id: str,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
) -> AssessmentSessionHistoryResponse:
    session = _assessment_session_or_404(db=db, session_id=session_id, user_id=user_id)
    return _assessment_session_history(db=db, session=session)


@router.get("/assessment-sessions/{session_id}", response_model=AssessmentSessionDetailResponse)
def get_assessment_session(
    session_id: str,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
) -> AssessmentSessionDetailResponse:
    session = _assessment_session_or_404(db=db, session_id=session_id, user_id=user_id)
    return _assessment_session_detail(db=db, session=session)


@router.post("/assessment-sessions/{session_id}/submit", response_model=AssessmentSessionSubmitResponse)
def submit_assessment_session(
    session_id: str,
    request: AssessmentSessionSubmitRequest,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
    service: FeedbackService = Depends(get_feedback_service),
    artifact_publisher: GeneratedArtifactPublisher = Depends(get_generated_artifact_publisher),
) -> AssessmentSessionSubmitResponse:
    session = _assessment_session_or_404(db=db, session_id=session_id, user_id=user_id)
    expected_problem_ids = set(session.problem_ids)
    submitted_problem_ids = {item.problem_id for item in request.submissions}
    if not submitted_problem_ids.issubset(expected_problem_ids):
        raise HTTPException(status_code=422, detail="Assessment session submit includes problems outside the session")
    existing_feedbacks = (
        db.query(Feedback)
        .filter(Feedback.user_id == user_id, Feedback.problem_id.in_(session.problem_ids))
        .all()
    )
    existing_feedback_by_problem_id = {feedback.problem_id: feedback for feedback in existing_feedbacks}
    duplicate_problem_ids = sorted(submitted_problem_ids & set(existing_feedback_by_problem_id))
    if duplicate_problem_ids:
        raise HTTPException(status_code=409, detail="Assessment session already has submitted answers for some problems")
    if request.finalize and (set(existing_feedback_by_problem_id) | submitted_problem_ids) != expected_problem_ids:
        raise HTTPException(status_code=422, detail="Final assessment session submit must include every unsubmitted problem")
    _validate_assessment_session_submit_request(db=db, session=session, request=request)

    feedbacks: list[Feedback] = []
    submission_by_problem_id = {item.problem_id: item for item in request.submissions}
    try:
        for problem_id in session.problem_ids:
            if problem_id not in submission_by_problem_id:
                continue
            item = submission_by_problem_id[problem_id]
            feedbacks.append(
                service.submit_answer(
                    problem_id=problem_id,
                    user_id=user_id,
                    request=item.to_submit_answer_request(),
                )
            )
        completed_problem_ids = set(existing_feedback_by_problem_id) | submitted_problem_ids
        if completed_problem_ids == expected_problem_ids:
            session.status = AssessmentSessionStatus.submitted.value
            session.submitted_at = datetime.now(timezone.utc)
        else:
            session.status = AssessmentSessionStatus.in_progress.value
        db.commit()
        db.refresh(session)
    except DuplicateSubmissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SearchAgentError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    report = _assessment_session_report(db=db, session=session)
    if report.status == AssessmentSessionStatus.submitted:
        artifact_publisher.publish_assessment_report(report, user_id=user_id)
    return AssessmentSessionSubmitResponse(
        session_id=session.id,
        status=report.status,
        feedbacks=[to_feedback_response(feedback) for feedback in feedbacks],
        report=report,
    )


@router.get("/assessment-sessions/{session_id}/report", response_model=AssessmentSessionReportResponse)
def get_assessment_session_report(
    session_id: str,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
) -> AssessmentSessionReportResponse:
    session = _assessment_session_or_404(db=db, session_id=session_id, user_id=user_id)
    return _assessment_session_report(db=db, session=session)


@router.get("/problem-analytics", response_model=ProblemItemAnalyticsListResponse)
def list_problem_analytics(
    user_id: str = Depends(get_user_id),
    service: ProblemService = Depends(get_problem_service),
    document_id: str | None = Query(default=None, min_length=1, max_length=128),
    needs_review: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> ProblemItemAnalyticsListResponse:
    items, total = service.list_problem_analytics(
        user_id=user_id,
        document_id=document_id,
        needs_review=needs_review,
        limit=limit,
    )
    return ProblemItemAnalyticsListResponse(
        items=[ProblemItemAnalyticsResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
    )


@router.get("/problem-template-analytics", response_model=ProblemTemplateAnalyticsListResponse)
def list_problem_template_analytics(
    user_id: str = Depends(get_user_id),
    service: ProblemService = Depends(get_problem_service),
    document_id: str | None = Query(default=None, min_length=1, max_length=128),
    needs_review: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> ProblemTemplateAnalyticsListResponse:
    items, total = service.list_problem_template_analytics(
        user_id=user_id,
        document_id=document_id,
        needs_review=needs_review,
        limit=limit,
    )
    return ProblemTemplateAnalyticsListResponse(
        items=[ProblemTemplateAnalyticsResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
    )


@router.get("/problem-regeneration-candidates", response_model=ProblemRegenerationCandidateListResponse)
def list_problem_regeneration_candidates(
    user_id: str = Depends(get_user_id),
    service: ProblemService = Depends(get_problem_service),
    document_id: str | None = Query(default=None, min_length=1, max_length=128),
    status: str | None = Query(default="open", min_length=1, max_length=32),
    limit: int = Query(default=50, ge=1, le=100),
) -> ProblemRegenerationCandidateListResponse:
    items, total = service.list_problem_regeneration_candidates(
        user_id=user_id,
        document_id=document_id,
        status=status,
        limit=limit,
    )
    return ProblemRegenerationCandidateListResponse(
        items=[ProblemRegenerationCandidateResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
    )


@router.get("/usage-ledger", response_model=UsageLedgerListResponse)
def list_usage_ledger(
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
    feature: str | None = Query(default=None, min_length=1, max_length=80),
    limit: int = Query(default=100, ge=1, le=500),
) -> UsageLedgerListResponse:
    items, total = UsageLedgerRepository(db).list_for_user(
        user_id=user_id,
        feature=feature,
        limit=limit,
    )
    return UsageLedgerListResponse(
        items=[UsageLedgerResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
    )


@router.get("/usage-ledger/summary", response_model=UsageLedgerSummaryResponse)
def get_usage_ledger_summary(
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
    feature: str | None = Query(default=None, min_length=1, max_length=80),
) -> UsageLedgerSummaryResponse:
    return UsageLedgerSummaryResponse.model_validate(
        UsageLedgerRepository(db).summary_for_user(user_id=user_id, feature=feature)
    )


@router.post("/quality-reports", response_model=QualityReportResponse, status_code=201)
def create_quality_report(
    request: QualityReportRequest,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
    learning_content_repository: LearningContentRepository = Depends(get_learning_content_repository),
) -> QualityReportResponse:
    candidate_problem = _get_report_candidate_problem(
        request=request,
        user_id=user_id,
        db=db,
        learning_content_repository=learning_content_repository,
    )
    report = UserQualityReportRepository(db).create(user_id=user_id, request=request)
    if candidate_problem is not None:
        ProblemRegenerationCandidateRepository(db).upsert_from_quality_report(
            problem=candidate_problem,
            report=report,
        )
    db.commit()
    db.refresh(report)
    return QualityReportResponse.model_validate(report)


@router.post(
    "/problem-regeneration-candidates/{candidate_id}/regenerate",
    response_model=ProblemRegenerationResultResponse,
)
def regenerate_problem_candidate(
    candidate_id: str,
    user_id: str = Depends(get_user_id),
    service: ProblemService = Depends(get_problem_service),
) -> ProblemRegenerationResultResponse:
    try:
        problem, candidate = service.regenerate_problem_from_candidate(
            user_id=user_id,
            candidate_id=candidate_id,
        )
    except SearchAgentError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ProblemRegenerationResultResponse(
        candidate=ProblemRegenerationCandidateResponse.model_validate(candidate),
        problem=to_problem_response(problem, include_solution=False, include_internal=False),
        original_problem_id=candidate.problem_id,
        trigger_reasons=candidate.trigger_reasons,
        suggested_action=candidate.suggested_action,
    )


@router.get("/problems/{problem_id}", response_model=ProblemResponse)
def get_problem(
    problem_id: str,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
    service: ProblemService = Depends(get_problem_service),
) -> ProblemResponse:
    problem = service.get_problem(problem_id)
    if problem is None or problem.user_id != user_id:
        raise HTTPException(status_code=404, detail="Problem not found")
    has_feedback = (
        db.query(Feedback)
        .filter(Feedback.problem_id == problem_id, Feedback.user_id == user_id)
        .first()
        is not None
    )
    return to_problem_response(problem, include_solution=has_feedback, include_internal=False)


@router.get("/problems/{problem_id}/analytics", response_model=ProblemItemAnalyticsResponse)
def get_problem_analytics(
    problem_id: str,
    user_id: str = Depends(get_user_id),
    service: ProblemService = Depends(get_problem_service),
) -> ProblemItemAnalyticsResponse:
    problem = service.get_problem(problem_id)
    if problem is None or problem.user_id != user_id:
        raise HTTPException(status_code=404, detail="Problem not found")
    analytics = service.get_problem_analytics(problem_id)
    if analytics is None:
        raise HTTPException(status_code=404, detail="Problem analytics not found")
    return ProblemItemAnalyticsResponse.model_validate(analytics)


@router.post("/problems/{problem_id}/hints", response_model=ProblemHintResponse)
def create_problem_hint(
    problem_id: str,
    request: ProblemHintRequest,
    user_id: str = Depends(get_user_id),
    service: ProblemService = Depends(get_problem_service),
) -> ProblemHintResponse:
    try:
        return service.create_problem_hint(user_id=user_id, problem_id=problem_id, request=request)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/problems/{problem_id}/submit", response_model=FeedbackResponse)
def submit_answer(
    problem_id: str,
    request: SubmitAnswerRequest,
    user_id: str = Depends(get_user_id),
    service: FeedbackService = Depends(get_feedback_service),
) -> FeedbackResponse:
    try:
        feedback = service.submit_answer(problem_id=problem_id, user_id=user_id, request=request)
        return to_feedback_response(feedback)
    except DuplicateSubmissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SearchAgentError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/feedback/{feedback_id}", response_model=FeedbackResponse)
def get_feedback(
    feedback_id: str,
    user_id: str = Depends(get_user_id),
    service: FeedbackService = Depends(get_feedback_service),
) -> FeedbackResponse:
    feedback = service.get_feedback(feedback_id)
    if feedback is None or feedback.user_id != user_id:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return to_feedback_response(feedback)


@router.post("/feedback/{feedback_id}/actions", response_model=FeedbackActionEventResponse, status_code=201)
def create_feedback_action_event(
    feedback_id: str,
    request: FeedbackActionEventRequest,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
    learning_content_repository: LearningContentRepository = Depends(get_learning_content_repository),
) -> FeedbackActionEventResponse:
    feedback = db.get(Feedback, feedback_id)
    if feedback is None or feedback.user_id != user_id:
        raise HTTPException(status_code=404, detail="Feedback not found")
    _validate_feedback_action_targets(
        request=request,
        user_id=user_id,
        db=db,
        learning_content_repository=learning_content_repository,
    )
    event = FeedbackActionEventRepository(db).create(feedback=feedback, request=request)
    _link_feedback_action_to_remediation(feedback=feedback, request=request, db=db)
    db.commit()
    db.refresh(event)
    return FeedbackActionEventResponse.model_validate(event)


@router.get("/feedback/{feedback_id}/actions", response_model=FeedbackActionEventListResponse)
def list_feedback_action_events(
    feedback_id: str,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
) -> FeedbackActionEventListResponse:
    feedback = db.get(Feedback, feedback_id)
    if feedback is None or feedback.user_id != user_id:
        raise HTTPException(status_code=404, detail="Feedback not found")
    items, total = FeedbackActionEventRepository(db).list_for_feedback(
        feedback_id=feedback_id,
        user_id=user_id,
        limit=limit,
    )
    return FeedbackActionEventListResponse(
        items=[FeedbackActionEventResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
    )
