from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agents import FeedbackAgent
from app.config import Settings, get_settings
from app.llm import safety_identifier_for_user
from app.models import Feedback, Problem
from app.repositories.feedback_repository import FeedbackRepository
from app.repositories.mistake_remediation_event_repository import MistakeRemediationEventRepository
from app.repositories.problem_hint_repository import ProblemHintRepository
from app.repositories.problem_item_analytics_repository import ProblemItemAnalyticsRepository
from app.repositories.problem_regeneration_candidate_repository import ProblemRegenerationCandidateRepository
from app.repositories.problem_repository import ProblemRepository
from app.repositories.problem_template_analytics_repository import ProblemTemplateAnalyticsRepository
from app.repositories.submission_repository import SubmissionRepository
from app.repositories.usage_ledger_repository import UsageLedgerRepository
from app.repositories.user_concept_stat_repository import UserConceptStatRepository
from app.schemas.integration_contracts import RetrievedChunk, UserConceptUpdatePayload
from app.schemas.problems import LearningState, ProblemType, SubmitAnswerRequest
from app.services.generated_artifact_publisher import GeneratedArtifactPublisher
from app.services.search_service import SearchAgentError, SearchService


@dataclass(frozen=True)
class FeedbackSubmissionResult:
    feedback: Feedback
    user_concept_update: UserConceptUpdatePayload


class DuplicateSubmissionError(RuntimeError):
    """Raised when a user tries to submit an already completed problem."""


class FeedbackService:
    def __init__(
        self,
        *,
        db: Session,
        feedback_agent: FeedbackAgent,
        search_service: SearchService,
        remediation_repository: MistakeRemediationEventRepository | None = None,
        item_analytics_repository: ProblemItemAnalyticsRepository | None = None,
        template_analytics_repository: ProblemTemplateAnalyticsRepository | None = None,
        regeneration_candidate_repository: ProblemRegenerationCandidateRepository | None = None,
        artifact_publisher: GeneratedArtifactPublisher | None = None,
        settings: Settings | None = None,
    ):
        self.settings = settings or getattr(feedback_agent, "settings", None) or get_settings()
        self.db = db
        self.feedback_agent = feedback_agent
        self.search_service = search_service
        self.problem_repo = ProblemRepository(db)
        self.submission_repo = SubmissionRepository(db)
        self.feedback_repo = FeedbackRepository(db)
        self.stat_repo = UserConceptStatRepository(db)
        self.remediation_repo = remediation_repository or MistakeRemediationEventRepository(db)
        self.hint_repo = ProblemHintRepository(db)
        self.item_analytics_repo = item_analytics_repository or ProblemItemAnalyticsRepository(db)
        self.template_analytics_repo = template_analytics_repository or ProblemTemplateAnalyticsRepository(db)
        self.regeneration_candidate_repo = regeneration_candidate_repository or ProblemRegenerationCandidateRepository(db)
        self.artifact_publisher = artifact_publisher or GeneratedArtifactPublisher()
        self.usage_ledger_repo = UsageLedgerRepository(db, self.settings)

    def submit_answer(self, *, problem_id: str, user_id: str, request: SubmitAnswerRequest) -> Feedback:
        return self.submit_answer_with_update(problem_id=problem_id, user_id=user_id, request=request).feedback

    def submit_answer_with_update(
        self,
        *,
        problem_id: str,
        user_id: str,
        request: SubmitAnswerRequest,
    ) -> FeedbackSubmissionResult:
        problem = self.problem_repo.get(problem_id)
        if problem is None or problem.user_id != user_id:
            raise LookupError("Problem not found")
        if self.feedback_repo.get_for_problem_and_user(problem_id=problem.id, user_id=user_id):
            raise DuplicateSubmissionError("Problem already submitted")
        self._validate_answer_for_problem(problem=problem, request=request)

        chunks: list[RetrievedChunk] = []
        if problem.type == ProblemType.short_answer.value:
            chunks = self._get_source_chunks_for_feedback(problem)
        self._enforce_feedback_llm_budget_if_needed(user_id=user_id, problem=problem)

        try:
            answer_dict = request.answer.model_dump(mode="json", exclude_none=True)
            effective_hint_count = max(
                int(request.hint_count or 0),
                self.hint_repo.count_for_problem_user(problem_id=problem.id, user_id=user_id),
            )
            submission = self.submission_repo.create(
                problem_id=problem.id,
                user_id=user_id,
                answer=answer_dict,
                solution_steps=request.answer.solution_steps,
                elapsed_time_sec=request.elapsed_time_sec,
                hint_count=effective_hint_count,
                confidence_level=request.confidence_level,
            )

            feedback_llm = getattr(self.feedback_agent, "llm", None)
            self._reset_llm_usage(feedback_llm)
            if problem.type == ProblemType.multiple_choice.value:
                feedback_payload = self._grade_multiple_choice(
                    problem=problem,
                    submission=submission,
                    safety_identifier=safety_identifier_for_user(user_id),
                )
            else:
                feedback_payload = self.feedback_agent.grade_short_answer(
                    problem=problem,
                    submission=submission,
                    chunks=chunks,
                    safety_identifier=safety_identifier_for_user(user_id),
                )
                feedback_payload = self._with_short_answer_evaluation_details(
                    feedback_payload,
                    problem=problem,
                    submission=submission,
                    chunks=chunks,
                )
            learning_state = self._learning_state(
                is_correct=feedback_payload["is_correct"],
                score=feedback_payload["score"],
                max_score=feedback_payload["max_score"],
                confidence_level=request.confidence_level,
            )
            feedback_payload["learning_state"] = learning_state.value
            self.usage_ledger_repo.create_from_llm_client(
                user_id=user_id,
                feature=self._usage_feature_for_problem(problem),
                client=feedback_llm,
                premium_reason=self._feedback_premium_reason(problem=problem, request=request),
            )

            stat_update = self.stat_repo.update_for_feedback(
                user_id=user_id,
                concepts=problem.concepts,
                is_correct=feedback_payload["is_correct"],
                mistake_type=feedback_payload.get("mistake_type"),
                hint_count=effective_hint_count,
                confidence_level=request.confidence_level,
                score=feedback_payload["score"],
                max_score=feedback_payload["max_score"],
                learning_state=learning_state,
            )
            recommended_review = list(
                dict.fromkeys([*feedback_payload.get("recommended_review", []), *stat_update.recommended_review])
            )
            feedback_payload["recommended_review"] = recommended_review

            feedback = self.feedback_repo.create(
                {
                    "submission_id": submission.id,
                    "problem_id": problem.id,
                    "user_id": user_id,
                    "source_chunk_ids": problem.source_chunk_ids,
                    **feedback_payload,
                }
            )
            analytics = self.item_analytics_repo.record_attempt(
                problem=problem,
                submission=submission,
                feedback=feedback,
                feedback_payload=feedback_payload,
            )
            template_analytics = self.template_analytics_repo.record_attempt(
                problem=problem,
                submission=submission,
                feedback=feedback,
                feedback_payload=feedback_payload,
            )
            self.regeneration_candidate_repo.upsert_from_analytics(problem=problem, analytics=analytics)
            self.regeneration_candidate_repo.upsert_from_template_analytics(
                problem=problem,
                analytics=template_analytics,
            )
            self.remediation_repo.record_followup_result(
                user_id=user_id,
                followup_problem_id=problem.id,
                is_correct=feedback_payload["is_correct"],
                score=feedback_payload["score"],
                max_score=feedback_payload["max_score"],
                mistake_type=feedback_payload.get("mistake_type"),
            )
            user_concept_update = UserConceptUpdatePayload(
                user_id=user_id,
                problem_id=problem.id,
                submission_id=submission.id,
                feedback_id=feedback.id,
                concepts=problem.concepts,
                is_correct=feedback_payload["is_correct"],
                score=feedback_payload["score"],
                max_score=feedback_payload["max_score"],
                mistake_type=feedback_payload.get("mistake_type"),
                weak_concepts=feedback_payload.get("weak_concepts", []),
                recommended_review=recommended_review,
                mastery_updates=stat_update.mastery_updates,
                learning_state=learning_state,
            )
            self.db.commit()
            self.db.refresh(feedback)
            self.artifact_publisher.publish_feedback(feedback, problem=problem)
            self.artifact_publisher.publish_user_concept_update(user_concept_update, problem=problem)
            return FeedbackSubmissionResult(feedback=feedback, user_concept_update=user_concept_update)
        except Exception:
            self.db.rollback()
            raise

    def get_feedback(self, feedback_id: str) -> Feedback | None:
        return self.feedback_repo.get(feedback_id)

    def _reset_llm_usage(self, client: object) -> None:
        reset = getattr(client, "reset_last_call", None)
        if callable(reset):
            reset()

    def _usage_feature_for_problem(self, problem: Problem) -> str:
        if problem.type == ProblemType.multiple_choice.value:
            return "multiple_choice_feedback"
        return "short_answer_grading"

    def _enforce_feedback_llm_budget_if_needed(self, *, user_id: str, problem: Problem) -> None:
        if not self._feedback_will_use_llm(problem):
            return
        if not self.settings.llm_enforce_monthly_budget or self.settings.llm_monthly_user_budget_krw <= 0:
            return
        budget_summary = self.usage_ledger_repo.summary_for_user(
            user_id=user_id,
            since=self._current_month_start(),
        )
        if budget_summary["budget_status"] == "exceeded":
            raise ValueError("monthly LLM budget exceeded")

    def _feedback_will_use_llm(self, problem: Problem) -> bool:
        feedback_llm = getattr(self.feedback_agent, "llm", None)
        if not getattr(feedback_llm, "available", False):
            return False
        if problem.type == ProblemType.short_answer.value:
            return True
        return bool(self.settings.multiple_choice_feedback_llm_enabled)

    def _current_month_start(self) -> datetime:
        now = datetime.now(timezone.utc)
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def _feedback_premium_reason(self, *, problem: Problem, request: SubmitAnswerRequest) -> str:
        answer = request.answer
        return (
            f"problem_type={problem.type}, "
            f"difficulty={problem.difficulty}, "
            f"bloom_level={problem.bloom_level}, "
            f"input_mode={answer.input_mode.value}, "
            f"ocr_confidence={answer.ocr_confidence}, "
            f"confidence_level={request.confidence_level}"
        )

    def _learning_state(
        self,
        *,
        is_correct: bool,
        score: float,
        max_score: float,
        confidence_level: int | None,
    ) -> LearningState:
        if confidence_level is None:
            return LearningState.unreported
        score_ratio = score / max_score if max_score > 0 else 0
        high_confidence = confidence_level >= 3
        if is_correct:
            return LearningState.secure_mastery if high_confidence else LearningState.fragile_mastery
        if score_ratio > 0:
            return LearningState.partial_understanding
        return LearningState.high_confidence_misconception if high_confidence else LearningState.knowledge_gap

    def _with_short_answer_evaluation_details(
        self,
        feedback_payload: dict,
        *,
        problem: Problem,
        submission,
        chunks: list[RetrievedChunk],
    ) -> dict:
        confidence = self._short_answer_overall_confidence(
            feedback_payload=feedback_payload,
            submission=submission,
            chunks=chunks,
        )
        rubric_results = self._short_answer_rubric_results_with_confidence_cap(
            rubric_results=feedback_payload.get("rubric_results") or [],
            overall_confidence=confidence,
        )
        if not rubric_results:
            return feedback_payload
        feedback_payload = {
            **feedback_payload,
            "confidence": confidence,
            "rubric_results": rubric_results,
        }
        grading_review_reasons = self._short_answer_grading_review_reasons(
            feedback_payload=feedback_payload,
            chunks=chunks,
        )
        return {
            **feedback_payload,
            "evaluation_details": {
                "confidence": confidence,
                "confidence_reasons": self._short_answer_confidence_reasons(
                    feedback_payload=feedback_payload,
                    problem=problem,
                    submission=submission,
                    chunks=chunks,
                ),
                "needs_grading_review": bool(grading_review_reasons),
                "grading_review_reasons": grading_review_reasons,
                "rubric_results": rubric_results,
            },
        }

    def _short_answer_overall_confidence(
        self,
        *,
        feedback_payload: dict,
        submission,
        chunks: list[RetrievedChunk],
    ) -> str:
        answer = submission.answer or {}
        if answer.get("input_mode") == "tablet_ocr":
            ocr_confidence = answer.get("ocr_confidence")
            if ocr_confidence is None or float(ocr_confidence) < 0.75:
                return "low"
        if not chunks:
            return "low"
        confidence = feedback_payload.get("confidence") or "medium"
        if str(confidence) not in {"low", "medium", "high"}:
            confidence = "medium"
        rubric_confidences = {
            str(result.get("confidence") or "")
            for result in (feedback_payload.get("rubric_results") or [])
            if isinstance(result, dict)
        }
        if "low" in rubric_confidences:
            return "low"
        if confidence == "high" and "medium" in rubric_confidences:
            return "medium"
        return str(confidence)

    def _short_answer_rubric_results_with_confidence_cap(
        self,
        *,
        rubric_results: list[dict],
        overall_confidence: str,
    ) -> list[dict]:
        if overall_confidence != "low":
            return rubric_results
        return [
            {
                **result,
                "confidence": "low",
            }
            if isinstance(result, dict)
            else result
            for result in rubric_results
        ]

    def _short_answer_grading_review_reasons(
        self,
        *,
        feedback_payload: dict,
        chunks: list[RetrievedChunk],
    ) -> list[str]:
        reasons: list[str] = []
        confidence = str(feedback_payload.get("confidence") or "")
        score = float(feedback_payload.get("score") or 0)
        max_score = float(feedback_payload.get("max_score") or 0)
        if confidence == "low":
            reasons.append("채점 confidence가 낮아 상위 모델 또는 운영자 재검토 후보입니다.")
        if not chunks:
            reasons.append("근거 chunk가 없어 source 기반 채점 재검토가 필요합니다.")
        if max_score > 0:
            score_ratio = score / max_score
            if 0.4 <= score_ratio <= 0.6:
                reasons.append("부분 점수가 통과/오답 경계에 가까워 rubric 판단 재검토가 필요합니다.")
        low_rubric_criteria = [
            str(result.get("criterion") or "")
            for result in (feedback_payload.get("rubric_results") or [])
            if isinstance(result, dict) and str(result.get("confidence") or "") == "low"
        ]
        if low_rubric_criteria:
            reasons.append("low confidence rubric 기준: " + ", ".join(low_rubric_criteria[:3]))
        return list(dict.fromkeys(reasons))[:10]

    def _short_answer_confidence_reasons(
        self,
        *,
        feedback_payload: dict,
        problem: Problem,
        submission,
        chunks: list[RetrievedChunk],
    ) -> list[str]:
        reasons: list[str] = []
        answer = submission.answer or {}
        if answer.get("input_mode") == "tablet_ocr":
            ocr_confidence = answer.get("ocr_confidence")
            if ocr_confidence is None:
                reasons.append("OCR 신뢰도 값이 없어 채점 결과를 조심스럽게 봐야 합니다.")
            elif float(ocr_confidence) < 0.75:
                reasons.append("OCR 신뢰도가 낮아 학생 답안 인식 오류 가능성이 있습니다.")
            else:
                reasons.append("OCR 신뢰도가 충분해 인식된 답안을 기준으로 채점했습니다.")

        if chunks:
            reasons.append("문제의 근거 chunk를 다시 확인해 rubric 채점 기준과 비교했습니다.")
        else:
            reasons.append("근거 chunk가 없어 source 기반 채점 신뢰도가 낮습니다.")

        score = float(feedback_payload.get("score") or 0)
        max_score = float(feedback_payload.get("max_score") or 0)
        if 0 < score < max_score:
            reasons.append("일부 rubric만 충족되어 부분 점수 판단으로 처리했습니다.")
        elif score == max_score:
            reasons.append("모든 rubric 기준이 충족되어 높은 신뢰도로 정답 처리했습니다.")
        else:
            reasons.append("충족된 rubric 기준이 없어 오답 판단 근거가 비교적 명확합니다.")

        low_rubric_confidence = any(
            str(result.get("confidence") or "") == "low"
            for result in (feedback_payload.get("rubric_results") or [])
            if isinstance(result, dict)
        )
        if low_rubric_confidence:
            reasons.append("일부 rubric 항목의 판단 신뢰도가 낮아 재검토가 필요할 수 있습니다.")

        if problem.rubric and len(feedback_payload.get("rubric_results") or []) == len(problem.rubric):
            reasons.append("rubric 항목 수와 채점 결과 항목 수가 일치합니다.")

        return list(dict.fromkeys(reasons))[:10]

    def _grade_multiple_choice(self, *, problem: Problem, submission, safety_identifier: str | None) -> dict:
        selected = submission.answer.get("choice_id")
        is_correct = selected == problem.answer.get("choice_id")
        return self.feedback_agent.multiple_choice_feedback(
            problem=problem,
            submission=submission,
            is_correct=is_correct,
            safety_identifier=safety_identifier,
        )

    def _validate_answer_for_problem(self, *, problem: Problem, request: SubmitAnswerRequest) -> None:
        if problem.type == ProblemType.multiple_choice.value and not request.answer.choice_id:
            raise ValueError("choice_id is required for multiple_choice problems")
        if problem.type == ProblemType.multiple_choice.value:
            choice_ids = {choice.get("id") for choice in (problem.choices or [])}
            if request.answer.choice_id not in choice_ids:
                raise ValueError("choice_id must exist in problem choices")
        if problem.type == ProblemType.short_answer.value and not request.answer.text:
            raise ValueError("text is required for short_answer problems")

    def _get_source_chunks_for_feedback(self, problem: Problem) -> list[RetrievedChunk]:
        if problem.source_evidence_snapshot:
            chunks = self._source_chunks_from_snapshot(problem)
            return self._validate_and_order_source_chunks(
                problem=problem,
                chunks=chunks,
                source_label="Stored source evidence snapshot",
            )

        chunks = self.search_service.get_chunks_by_ids(
            document_id=problem.document_id,
            chunk_ids=problem.source_chunk_ids,
        )
        return self._validate_and_order_source_chunks(
            problem=problem,
            chunks=chunks,
            source_label="Search Agent",
        )

    def _source_chunks_from_snapshot(self, problem: Problem) -> list[RetrievedChunk]:
        try:
            return [RetrievedChunk.model_validate(chunk) for chunk in problem.source_evidence_snapshot or []]
        except Exception as exc:
            raise SearchAgentError(f"Stored source evidence snapshot is invalid: {exc}") from exc

    def _validate_and_order_source_chunks(
        self,
        *,
        problem: Problem,
        chunks: list[RetrievedChunk],
        source_label: str,
    ) -> list[RetrievedChunk]:
        returned_chunk_ids = [chunk.chunk_id for chunk in chunks]
        if len(set(returned_chunk_ids)) != len(returned_chunk_ids):
            raise SearchAgentError(f"{source_label} returned duplicate source chunks")

        unexpected_ids = [chunk.chunk_id for chunk in chunks if chunk.chunk_id not in problem.source_chunk_ids]
        if unexpected_ids:
            raise SearchAgentError(f"{source_label} returned unexpected source chunks: {', '.join(unexpected_ids)}")

        returned_ids = set(returned_chunk_ids)
        missing_ids = [chunk_id for chunk_id in problem.source_chunk_ids if chunk_id not in returned_ids]
        if missing_ids:
            raise SearchAgentError(f"{source_label} did not return source chunks: {', '.join(missing_ids)}")
        mismatched_document_ids = [
            chunk.chunk_id
            for chunk in chunks
            if chunk.chunk_id in problem.source_chunk_ids and chunk.document_id != problem.document_id
        ]
        if mismatched_document_ids:
            raise SearchAgentError(
                f"{source_label} returned chunks from a different document: {', '.join(mismatched_document_ids)}"
            )
        chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        return [chunk_by_id[chunk_id] for chunk_id in problem.source_chunk_ids]
