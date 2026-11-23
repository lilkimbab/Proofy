from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from app.models import Feedback, Problem, ProblemTemplateAnalytics, Submission
from app.models.entities import utcnow
from app.schemas.problems import ProblemType


class ProblemTemplateAnalyticsRepository:
    MIN_ATTEMPTS_FOR_REVIEW = 5
    WARMING_UP_ATTEMPTS = 30

    def __init__(self, db: Session):
        self.db = db

    def get(self, template_key: str) -> ProblemTemplateAnalytics | None:
        return self.db.get(ProblemTemplateAnalytics, template_key)

    def get_for_problem(self, problem: Problem) -> ProblemTemplateAnalytics | None:
        return self.get(self.template_key_for_problem(problem))

    def list_for_user(
        self,
        *,
        user_id: str,
        document_id: str | None = None,
        needs_review: bool | None = None,
        limit: int = 50,
    ) -> tuple[list[ProblemTemplateAnalytics], int]:
        query = self.db.query(ProblemTemplateAnalytics).filter(ProblemTemplateAnalytics.user_id == user_id)
        if document_id:
            query = query.filter(ProblemTemplateAnalytics.document_id == document_id)
        if needs_review is not None:
            query = query.filter(ProblemTemplateAnalytics.needs_review == needs_review)
        total = query.count()
        items = (
            query.order_by(
                ProblemTemplateAnalytics.needs_review.desc(),
                ProblemTemplateAnalytics.updated_at.desc(),
            )
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
    ) -> ProblemTemplateAnalytics:
        analytics = self.get_for_problem(problem)
        if analytics is None:
            analytics = ProblemTemplateAnalytics(
                template_key=self.template_key_for_problem(problem),
                user_id=problem.user_id,
                document_id=problem.document_id,
                item_model_id=self._item_model_id(problem),
                concept=self._primary_concept(problem),
                difficulty=problem.difficulty,
                problem_type=problem.type,
                max_score=float(feedback.max_score),
            )
            self.db.add(analytics)
            self.db.flush()

        previous_attempts = analytics.total_attempts
        previous_problem_count = analytics.problem_count
        problem_ids = list(analytics.problem_ids or [])
        is_new_problem = problem.id not in problem_ids
        if is_new_problem:
            problem_ids.append(problem.id)
        analytics.problem_ids = problem_ids
        analytics.problem_count = len(problem_ids)

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
        analytics.usage_quality_score = self._usage_quality_score(analytics)
        self._record_behavior(analytics=analytics, submission=submission)
        self._record_mistake_type(analytics=analytics, feedback=feedback)
        self._record_rubric_attempt(analytics=analytics, feedback_payload=feedback_payload)

        if is_new_problem:
            self._record_item_quality(
                analytics=analytics,
                problem=problem,
                previous_problem_count=previous_problem_count,
            )
        self._refresh_reliability_fields(analytics)
        analytics.needs_review, analytics.review_reasons = self._review_status(analytics)
        analytics.updated_at = utcnow()
        self.db.flush()
        return analytics

    def template_key_for_problem(self, problem: Problem) -> str:
        raw_key = "|".join(
            [
                problem.user_id,
                problem.document_id,
                self._item_model_id(problem),
                self._normalize_key_part(self._primary_concept(problem)),
                str(problem.difficulty),
                str(problem.type),
            ]
        )
        digest = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:20]
        return f"tpl_{digest}"

    def _item_model_id(self, problem: Problem) -> str:
        return str(problem.item_model_id or "unknown_model").strip() or "unknown_model"

    def _primary_concept(self, problem: Problem) -> str:
        for concept in problem.concepts or []:
            concept_text = str(concept).strip()
            if concept_text:
                return concept_text
        return "unknown_concept"

    def _normalize_key_part(self, value: str) -> str:
        return " ".join(value.casefold().split())

    def _record_behavior(self, *, analytics: ProblemTemplateAnalytics, submission: Submission) -> None:
        if int(submission.hint_count or 0) > 0:
            analytics.hint_usage_count = int(analytics.hint_usage_count or 0) + 1
        analytics.hint_usage_rate = self._ratio(analytics.hint_usage_count, analytics.total_attempts)

    def _record_mistake_type(self, *, analytics: ProblemTemplateAnalytics, feedback: Feedback) -> None:
        mistake_type = str(feedback.mistake_type or "").strip()
        if not mistake_type or mistake_type == "none":
            return
        analytics.mistake_type_counts = self._increment_count(analytics.mistake_type_counts or {}, mistake_type)
        analytics.common_mistake_types = self._top_keys(analytics.mistake_type_counts)

    def _record_rubric_attempt(self, *, analytics: ProblemTemplateAnalytics, feedback_payload: dict) -> None:
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

    def _record_item_quality(
        self,
        *,
        analytics: ProblemTemplateAnalytics,
        problem: Problem,
        previous_problem_count: int,
    ) -> None:
        score = self._professor_grade_final_score(problem)
        if score is None:
            return
        analytics.item_quality_average = self._rolling_average(
            previous_average=float(analytics.item_quality_average or 0),
            previous_count=previous_problem_count,
            new_value=score,
        )

    def _refresh_reliability_fields(self, analytics: ProblemTemplateAnalytics) -> None:
        status, confidence, note = self._sample_size_signal(analytics.total_attempts)
        analytics.sample_size_status = status
        analytics.statistics_confidence = confidence
        analytics.statistics_note = note

        if status != "reliable" and analytics.item_quality_average is not None:
            analytics.quality_score_for_review = round(float(analytics.item_quality_average), 3)
            analytics.quality_score_source = "template_item_quality"
            return

        analytics.quality_score_for_review = analytics.usage_quality_score
        analytics.quality_score_source = "template_usage_statistics"

    def _sample_size_signal(self, total_attempts: int) -> tuple[str, str, str]:
        if total_attempts < self.MIN_ATTEMPTS_FOR_REVIEW:
            return (
                "insufficient",
                "low",
                "템플릿 풀이 데이터가 아직 적어서 참고용으로만 봅니다. 문항 자체 품질 점수를 우선 확인합니다.",
            )
        if total_attempts < self.WARMING_UP_ATTEMPTS:
            return (
                "warming_up",
                "medium",
                "같은 유형의 풀이 데이터가 쌓이는 중입니다. 정답률은 보정값과 함께 봅니다.",
            )
        return (
            "reliable",
            "high",
            "같은 유형의 풀이 데이터가 충분히 쌓여 템플릿 통계를 주요 판단 기준으로 볼 수 있습니다.",
        )

    def _review_status(self, analytics: ProblemTemplateAnalytics) -> tuple[bool, list[str]]:
        if analytics.total_attempts < self.MIN_ATTEMPTS_FOR_REVIEW:
            return False, []
        reasons: list[str] = []
        if analytics.correct_rate <= 0.2:
            reasons.append("template_very_low_correct_rate")
        if analytics.correct_rate >= 0.95:
            reasons.append("template_very_high_correct_rate")
        if self._top_count(analytics.mistake_type_counts or {}) >= 3:
            reasons.append("repeated_template_mistake_type")
        if analytics.problem_type == ProblemType.short_answer.value and self._top_count(
            analytics.missed_rubric_criteria_counts or {}
        ) >= 3:
            reasons.append("repeated_template_missed_rubric")
        return bool(reasons), reasons

    def _top_count(self, counts: dict[str, int]) -> int:
        if not counts:
            return 0
        return max(int(value or 0) for value in counts.values())

    def _professor_grade_final_score(self, problem: Problem) -> float | None:
        score_payload = problem.professor_grade_score or {}
        try:
            score = float(score_payload.get("final_score"))
        except (TypeError, ValueError):
            return None
        if score < 0 or score > 1:
            return None
        return round(score, 3)

    def _usage_quality_score(self, analytics: ProblemTemplateAnalytics) -> float:
        return round(float(analytics.discrimination_proxy or 0), 3)

    def _rolling_average(self, *, previous_average: float, previous_count: int, new_value: float) -> float:
        if previous_count <= 0:
            return round(new_value, 3)
        return round(((previous_average * previous_count) + new_value) / (previous_count + 1), 3)

    def _ratio(self, numerator: int | float, denominator: int | float) -> float:
        if denominator <= 0:
            return 0.0
        return round(float(numerator) / float(denominator), 3)

    def _smoothed_correct_rate(self, *, correct_count: int, total_attempts: int) -> float:
        return round((correct_count + 1) / (total_attempts + 2), 3)

    def _increment_count(self, counts: dict, key: str) -> dict[str, int]:
        updated = dict(counts)
        updated[key] = int(updated.get(key) or 0) + 1
        return updated

    def _top_keys(self, counts: dict[str, int], *, limit: int = 5) -> list[str]:
        return [key for key, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]]

    def _discrimination_proxy(self, correct_rate: float) -> float:
        return round(1 - abs(0.5 - correct_rate) * 2, 3)
