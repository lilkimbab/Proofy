from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Feedback, Problem, ProblemItemAnalytics, ProblemRegenerationCandidate, ProblemTemplateAnalytics, UserQualityReport
from app.models.entities import utcnow


class ProblemRegenerationCandidateRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_for_user(
        self,
        *,
        user_id: str,
        document_id: str | None = None,
        status: str | None = "open",
        limit: int = 50,
    ) -> tuple[list[ProblemRegenerationCandidate], int]:
        query = self.db.query(ProblemRegenerationCandidate).filter(ProblemRegenerationCandidate.user_id == user_id)
        if document_id:
            query = query.filter(ProblemRegenerationCandidate.document_id == document_id)
        if status:
            query = query.filter(ProblemRegenerationCandidate.status == status)
        total = query.count()
        items = query.order_by(ProblemRegenerationCandidate.updated_at.desc()).limit(limit).all()
        return items, total

    def upsert_from_analytics(
        self,
        *,
        problem: Problem,
        analytics: ProblemItemAnalytics,
    ) -> ProblemRegenerationCandidate | None:
        if not analytics.needs_review:
            return None
        trigger_reasons = list(dict.fromkeys(analytics.review_reasons or []))
        if not trigger_reasons:
            return None

        candidate = self._get_open_for_problem(problem_id=problem.id)
        if candidate is None:
            candidate = ProblemRegenerationCandidate(
                problem_id=problem.id,
                user_id=problem.user_id,
                document_id=problem.document_id,
            )
            self.db.add(candidate)
            self.db.flush()

        candidate.trigger_reasons = trigger_reasons
        candidate.source_metrics = self._source_metrics(analytics)
        candidate.suggested_action = self._suggested_action(trigger_reasons)
        candidate.updated_at = utcnow()
        self.db.flush()
        return candidate

    def upsert_from_template_analytics(
        self,
        *,
        problem: Problem,
        analytics: ProblemTemplateAnalytics,
    ) -> ProblemRegenerationCandidate | None:
        if not analytics.needs_review:
            return None
        trigger_reasons = [f"template:{reason}" for reason in list(dict.fromkeys(analytics.review_reasons or []))]
        if not trigger_reasons:
            return None

        candidate = self._get_open_for_problem(problem_id=problem.id)
        if candidate is None:
            candidate = ProblemRegenerationCandidate(
                problem_id=problem.id,
                user_id=problem.user_id,
                document_id=problem.document_id,
            )
            self.db.add(candidate)
            self.db.flush()

        candidate.trigger_reasons = list(dict.fromkeys([*(candidate.trigger_reasons or []), *trigger_reasons]))
        candidate.source_metrics = {
            **(candidate.source_metrics or {}),
            "template_key": analytics.template_key,
            "template_problem_count": analytics.problem_count,
            "template_total_attempts": analytics.total_attempts,
            "template_correct_rate": analytics.correct_rate,
            "template_correct_rate_smoothed": analytics.correct_rate_smoothed,
            "template_sample_size_status": analytics.sample_size_status,
            "template_statistics_confidence": analytics.statistics_confidence,
            "template_quality_score_for_review": analytics.quality_score_for_review,
            "template_quality_score_source": analytics.quality_score_source,
            "template_common_mistake_types": analytics.common_mistake_types or [],
            "template_common_missed_rubric_criteria": analytics.common_missed_rubric_criteria or [],
        }
        candidate.suggested_action = self._suggested_action(candidate.trigger_reasons)
        candidate.updated_at = utcnow()
        self.db.flush()
        return candidate

    def upsert_from_quality_report(
        self,
        *,
        problem: Problem,
        report: UserQualityReport,
    ) -> ProblemRegenerationCandidate | None:
        if report.reason == "tone_awkward":
            return None

        trigger_reason = f"quality_report:{report.reason}"
        candidate = self._get_open_for_problem(problem_id=problem.id)
        if candidate is None:
            candidate = ProblemRegenerationCandidate(
                problem_id=problem.id,
                user_id=problem.user_id,
                document_id=problem.document_id,
            )
            self.db.add(candidate)
            self.db.flush()

        candidate.trigger_reasons = list(dict.fromkeys([*(candidate.trigger_reasons or []), trigger_reason]))
        candidate.source_metrics = {
            **(candidate.source_metrics or {}),
            "quality_report_id": report.id,
            "quality_report_reason": report.reason,
            "quality_report_target_type": report.target_type,
            "quality_report_target_id": report.target_id,
            "quality_report_message_present": bool(report.message),
            **self._quality_report_target_metrics(problem=problem, report=report),
        }
        candidate.suggested_action = self._suggested_action(candidate.trigger_reasons)
        candidate.updated_at = utcnow()
        self.db.flush()
        return candidate

    def get_for_user(self, *, candidate_id: str, user_id: str) -> ProblemRegenerationCandidate | None:
        return (
            self.db.query(ProblemRegenerationCandidate)
            .filter(
                ProblemRegenerationCandidate.id == candidate_id,
                ProblemRegenerationCandidate.user_id == user_id,
            )
            .first()
        )

    def mark_resolved(
        self,
        *,
        candidate: ProblemRegenerationCandidate,
        generated_problem_id: str,
        notes: list[str] | None = None,
    ) -> ProblemRegenerationCandidate:
        candidate.status = "resolved"
        candidate.generated_problem_id = generated_problem_id
        candidate.resolution_notes = list(dict.fromkeys(notes or []))
        candidate.updated_at = utcnow()
        self.db.flush()
        return candidate

    def _get_open_for_problem(self, *, problem_id: str) -> ProblemRegenerationCandidate | None:
        return (
            self.db.query(ProblemRegenerationCandidate)
            .filter(
                ProblemRegenerationCandidate.problem_id == problem_id,
                ProblemRegenerationCandidate.status == "open",
            )
            .first()
        )

    def _source_metrics(self, analytics: ProblemItemAnalytics) -> dict:
        return {
            "total_attempts": analytics.total_attempts,
            "correct_rate": analytics.correct_rate,
            "correct_rate_smoothed": analytics.correct_rate_smoothed,
            "sample_size_status": analytics.sample_size_status,
            "statistics_confidence": analytics.statistics_confidence,
            "quality_score_for_review": analytics.quality_score_for_review,
            "quality_score_source": analytics.quality_score_source,
            "non_functioning_distractors": analytics.non_functioning_distractors or [],
            "common_missed_rubric_criteria": analytics.common_missed_rubric_criteria or [],
            "common_mistake_types": analytics.common_mistake_types or [],
        }

    def _quality_report_target_metrics(self, *, problem: Problem, report: UserQualityReport) -> dict:
        if report.target_type != "feedback":
            return {}
        feedback = self.db.get(Feedback, report.target_id)
        if feedback is None or feedback.problem_id != problem.id:
            return {}
        evaluation_details = feedback.evaluation_details or {}
        rubric_results = [
            result for result in (evaluation_details.get("rubric_results") or []) if isinstance(result, dict)
        ]
        return {
            "reported_feedback_id": feedback.id,
            "reported_feedback_score": feedback.score,
            "reported_feedback_max_score": feedback.max_score,
            "reported_feedback_mistake_type": feedback.mistake_type,
            "reported_feedback_learning_state": feedback.learning_state,
            "reported_feedback_evaluation_confidence": evaluation_details.get("confidence"),
            "reported_feedback_needs_grading_review": bool(evaluation_details.get("needs_grading_review")),
            "reported_feedback_grading_review_reasons": evaluation_details.get("grading_review_reasons") or [],
            "reported_feedback_rubric_criteria_count": len(rubric_results),
            "reported_feedback_low_confidence_criteria": [
                str(result.get("criterion") or "")
                for result in rubric_results
                if str(result.get("confidence") or "") == "low"
            ],
            "reported_feedback_missed_criteria": [
                str(result.get("criterion") or "")
                for result in rubric_results
                if not bool(result.get("matched"))
            ],
        }

    def _suggested_action(self, reasons: list[str]) -> str:
        reason_set = set(reasons)
        if {"quality_report:answer_wrong", "quality_report:not_grounded", "quality_report:copyright_concern"} & reason_set:
            return "check_ambiguity_or_source_grounding"
        if {"quality_report:grading_unfair", "quality_report:explanation_unclear"} & reason_set:
            return "revise_rubric_or_prompt"
        if "quality_report:too_easy" in reason_set:
            return "increase_cognitive_demand"
        if "quality_report:too_hard" in reason_set:
            return "check_ambiguity_or_source_grounding"
        if "non_functioning_distractors" in reason_set:
            return "rewrite_distractors"
        if "common_missed_rubric_criteria" in reason_set or "template:repeated_template_missed_rubric" in reason_set:
            return "revise_rubric_or_prompt"
        if "very_high_correct_rate" in reason_set or "template:template_very_high_correct_rate" in reason_set:
            return "increase_cognitive_demand"
        if "very_low_correct_rate" in reason_set or "template:template_very_low_correct_rate" in reason_set:
            return "check_ambiguity_or_source_grounding"
        if "template:repeated_template_mistake_type" in reason_set:
            return "revise_misconception_targeting"
        return "review_item"
