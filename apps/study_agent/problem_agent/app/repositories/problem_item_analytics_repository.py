from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Feedback, Problem, ProblemItemAnalytics, Submission
from app.models.entities import utcnow
from app.schemas.integration_contracts import ProblemItemStatPayload
from app.schemas.problems import ProblemType


class ProblemItemAnalyticsRepository:
    MIN_ATTEMPTS_FOR_REVIEW = 5
    WARMING_UP_ATTEMPTS = 20

    def __init__(self, db: Session):
        self.db = db

    def get(self, problem_id: str) -> ProblemItemAnalytics | None:
        return self.db.get(ProblemItemAnalytics, problem_id)

    def list_for_user(
        self,
        *,
        user_id: str,
        document_id: str | None = None,
        needs_review: bool | None = None,
        limit: int = 50,
    ) -> tuple[list[ProblemItemAnalytics], int]:
        query = (
            self.db.query(ProblemItemAnalytics)
            .join(Problem, Problem.id == ProblemItemAnalytics.problem_id)
            .filter(Problem.user_id == user_id)
        )
        if document_id:
            query = query.filter(ProblemItemAnalytics.document_id == document_id)
        if needs_review is not None:
            query = query.filter(ProblemItemAnalytics.needs_review == needs_review)
        total = query.count()
        items = (
            query.order_by(ProblemItemAnalytics.needs_review.desc(), ProblemItemAnalytics.updated_at.desc())
            .limit(limit)
            .all()
        )
        return items, total

    def record_attempt(
        self,
        *,
        problem: Problem,
        submission: Submission,
        feedback: Feedback,
        feedback_payload: dict,
    ) -> ProblemItemAnalytics:
        analytics = self.get(problem.id)
        if analytics is None:
            analytics = ProblemItemAnalytics(
                problem_id=problem.id,
                document_id=problem.document_id,
                problem_type=problem.type,
                max_score=float(feedback.max_score),
            )
            self.db.add(analytics)
            self.db.flush()

        previous_attempts = analytics.total_attempts
        analytics.total_attempts += 1
        if feedback.is_correct:
            analytics.correct_count += 1
        else:
            analytics.incorrect_count += 1
        analytics.correct_rate = self._ratio(analytics.correct_count, analytics.total_attempts)
        analytics.correct_rate_smoothed = self._smoothed_correct_rate(
            correct_count=analytics.correct_count,
            total_attempts=analytics.total_attempts,
        )
        analytics.average_score = self._rolling_average(
            previous_average=analytics.average_score,
            previous_count=previous_attempts,
            new_value=float(feedback.score),
        )
        analytics.max_score = max(float(analytics.max_score or 0), float(feedback.max_score))
        analytics.discrimination_proxy = self._discrimination_proxy(analytics.correct_rate)
        self._record_attempt_behavior(analytics=analytics, submission=submission)

        if problem.type == ProblemType.multiple_choice.value:
            self._record_choice_attempt(analytics=analytics, submission=submission, feedback_payload=feedback_payload)
        else:
            self._record_rubric_attempt(analytics=analytics, feedback_payload=feedback_payload)

        mistake_type = str(feedback.mistake_type or "").strip()
        if mistake_type and mistake_type != "none":
            analytics.mistake_type_counts = self._increment_count(analytics.mistake_type_counts or {}, mistake_type)
            analytics.common_mistake_types = self._top_keys(analytics.mistake_type_counts)

        analytics.non_functioning_distractors = self._non_functioning_distractors(problem=problem, analytics=analytics)
        analytics.needs_review, analytics.review_reasons = self._review_status(problem=problem, analytics=analytics)
        self._refresh_reliability_fields(problem=problem, analytics=analytics)
        analytics.updated_at = utcnow()
        self._validate(analytics)
        self.db.flush()
        return analytics

    def _record_choice_attempt(
        self,
        *,
        analytics: ProblemItemAnalytics,
        submission: Submission,
        feedback_payload: dict,
    ) -> None:
        selected_choice_id = str(submission.answer.get("choice_id") or "").strip()
        if not selected_choice_id:
            return
        analytics.choice_selection_counts = self._increment_count(analytics.choice_selection_counts or {}, selected_choice_id)
        analytics.choice_selection_distribution = {
            choice_id: self._ratio(count, analytics.total_attempts)
            for choice_id, count in sorted(analytics.choice_selection_counts.items())
        }
        choice_diagnostic = feedback_payload.get("choice_diagnostic") or {}
        mistake_type = str(choice_diagnostic.get("mistake_type") or feedback_payload.get("mistake_type") or "").strip()
        if mistake_type and mistake_type != "none":
            choice_counts = dict(analytics.choice_mistake_type_counts or {})
            per_choice = dict(choice_counts.get(selected_choice_id) or {})
            per_choice = self._increment_count(per_choice, mistake_type)
            choice_counts[selected_choice_id] = per_choice
            analytics.choice_mistake_type_counts = choice_counts

    def _record_rubric_attempt(self, *, analytics: ProblemItemAnalytics, feedback_payload: dict) -> None:
        evaluation_details = feedback_payload.get("evaluation_details") or {}
        rubric_results = evaluation_details.get("rubric_results") or feedback_payload.get("rubric_results") or []
        counts = dict(analytics.missed_rubric_criteria_counts or {})
        for result in rubric_results:
            if not isinstance(result, dict):
                continue
            try:
                awarded = float(result.get("awarded_points") or 0)
                max_points = float(result.get("max_points") or 0)
            except (TypeError, ValueError):
                continue
            if max_points <= 0 or awarded >= max_points:
                continue
            criterion = str(result.get("criterion") or "").strip()
            if criterion:
                counts = self._increment_count(counts, criterion)
        analytics.missed_rubric_criteria_counts = counts
        analytics.common_missed_rubric_criteria = self._top_keys(counts)

    def _record_attempt_behavior(self, *, analytics: ProblemItemAnalytics, submission: Submission) -> None:
        if submission.elapsed_time_sec is not None:
            previous_timed_attempts = int(analytics.timed_attempt_count or 0)
            analytics.average_time_sec = self._rolling_average(
                previous_average=float(analytics.average_time_sec or 0),
                previous_count=previous_timed_attempts,
                new_value=float(submission.elapsed_time_sec),
            )
            analytics.timed_attempt_count = previous_timed_attempts + 1
        if int(submission.hint_count or 0) > 0:
            analytics.hint_usage_count = int(analytics.hint_usage_count or 0) + 1
        analytics.hint_usage_rate = self._ratio(analytics.hint_usage_count, analytics.total_attempts)

    def _review_status(self, *, problem: Problem, analytics: ProblemItemAnalytics) -> tuple[bool, list[str]]:
        if analytics.total_attempts < self.MIN_ATTEMPTS_FOR_REVIEW:
            return False, []
        reasons: list[str] = []
        if analytics.correct_rate <= 0.2:
            reasons.append("very_low_correct_rate")
        if analytics.correct_rate >= 0.95:
            reasons.append("very_high_correct_rate")
        if analytics.non_functioning_distractors:
            reasons.append("non_functioning_distractors")
        if problem.type == ProblemType.short_answer.value and analytics.common_missed_rubric_criteria:
            reasons.append("common_missed_rubric_criteria")
        return bool(reasons), reasons

    def _refresh_reliability_fields(self, *, problem: Problem, analytics: ProblemItemAnalytics) -> None:
        status, confidence, note = self._sample_size_signal(analytics.total_attempts)
        analytics.sample_size_status = status
        analytics.statistics_confidence = confidence
        analytics.statistics_note = note

        item_quality_score = self._professor_grade_final_score(problem)
        if status != "reliable" and item_quality_score is not None:
            analytics.quality_score_for_review = item_quality_score
            analytics.quality_score_source = "item_quality"
            return

        analytics.quality_score_for_review = self._usage_quality_score(analytics)
        analytics.quality_score_source = "usage_statistics"

    def _sample_size_signal(self, total_attempts: int) -> tuple[str, str, str]:
        if total_attempts < self.MIN_ATTEMPTS_FOR_REVIEW:
            return (
                "insufficient",
                "low",
                "풀이 데이터가 아직 적어서 참고용으로만 봅니다. 문항 자체 품질 점수를 우선 확인합니다.",
            )
        if total_attempts < self.WARMING_UP_ATTEMPTS:
            return (
                "warming_up",
                "medium",
                "풀이 데이터가 쌓이는 중입니다. 정답률은 보정값과 함께 봅니다.",
            )
        return (
            "reliable",
            "high",
            "풀이 데이터가 충분히 쌓여 사용 통계를 주요 판단 기준으로 볼 수 있습니다.",
        )

    def _professor_grade_final_score(self, problem: Problem) -> float | None:
        score_payload = problem.professor_grade_score or {}
        try:
            score = float(score_payload.get("final_score"))
        except (TypeError, ValueError):
            return None
        if score < 0 or score > 1:
            return None
        return round(score, 3)

    def _usage_quality_score(self, analytics: ProblemItemAnalytics) -> float:
        return round(float(analytics.discrimination_proxy or 0), 3)

    def _non_functioning_distractors(self, *, problem: Problem, analytics: ProblemItemAnalytics) -> list[str]:
        if problem.type != ProblemType.multiple_choice.value or analytics.total_attempts < self.MIN_ATTEMPTS_FOR_REVIEW:
            return []
        answer_id = str((problem.answer or {}).get("choice_id") or "").strip()
        selected_ids = set((analytics.choice_selection_counts or {}).keys())
        distractor_ids = [
            str(choice.get("id") or "").strip()
            for choice in (problem.choices or [])
            if str(choice.get("id") or "").strip() and str(choice.get("id") or "").strip() != answer_id
        ]
        return [choice_id for choice_id in distractor_ids if choice_id not in selected_ids]

    def _validate(self, analytics: ProblemItemAnalytics) -> None:
        ProblemItemStatPayload.model_validate(
            {
                "problem_id": analytics.problem_id,
                "document_id": analytics.document_id,
                "problem_type": analytics.problem_type,
                "total_attempts": analytics.total_attempts,
                "correct_count": analytics.correct_count,
                "incorrect_count": analytics.incorrect_count,
                "correct_rate": analytics.correct_rate,
                "correct_rate_smoothed": analytics.correct_rate_smoothed,
                "average_score": analytics.average_score,
                "max_score": analytics.max_score,
                "discrimination_proxy": analytics.discrimination_proxy,
                "sample_size_status": analytics.sample_size_status,
                "statistics_confidence": analytics.statistics_confidence,
                "statistics_note": analytics.statistics_note,
                "quality_score_for_review": analytics.quality_score_for_review,
                "quality_score_source": analytics.quality_score_source,
                "timed_attempt_count": analytics.timed_attempt_count,
                "average_time_sec": analytics.average_time_sec,
                "hint_usage_count": analytics.hint_usage_count,
                "hint_usage_rate": analytics.hint_usage_rate,
                "choice_selection_counts": analytics.choice_selection_counts or {},
                "choice_selection_distribution": analytics.choice_selection_distribution or {},
                "choice_mistake_type_counts": analytics.choice_mistake_type_counts or {},
                "non_functioning_distractors": analytics.non_functioning_distractors or [],
                "mistake_type_counts": analytics.mistake_type_counts or {},
                "common_mistake_types": analytics.common_mistake_types or [],
                "missed_rubric_criteria_counts": analytics.missed_rubric_criteria_counts or {},
                "common_missed_rubric_criteria": analytics.common_missed_rubric_criteria or [],
                "needs_review": analytics.needs_review,
                "review_reasons": analytics.review_reasons or [],
            }
        )

    def _rolling_average(self, *, previous_average: float, previous_count: int, new_value: float) -> float:
        if previous_count <= 0:
            return round(new_value, 3)
        return round(((previous_average * previous_count) + new_value) / (previous_count + 1), 3)

    def _ratio(self, numerator: int | float, denominator: int | float) -> float:
        if denominator <= 0:
            return 0.0
        return round(float(numerator) / float(denominator), 3)

    def _smoothed_correct_rate(self, *, correct_count: int, total_attempts: int) -> float:
        # Beta(1, 1) smoothing keeps early 0% or 100% rates from being overread.
        return round((correct_count + 1) / (total_attempts + 2), 3)

    def _increment_count(self, counts: dict, key: str) -> dict[str, int]:
        updated = dict(counts)
        updated[key] = int(updated.get(key) or 0) + 1
        return updated

    def _top_keys(self, counts: dict[str, int], *, limit: int = 5) -> list[str]:
        return [key for key, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]]

    def _discrimination_proxy(self, correct_rate: float) -> float:
        # A cheap item-level proxy: items around 50% correct separate learners better than near-0/near-1 items.
        return round(1 - abs(0.5 - correct_rate) * 2, 3)
