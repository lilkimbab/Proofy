from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import UserConceptStat
from app.schemas.integration_contracts import ConceptMasteryUpdatePayload, UserConceptStatUpdateResult
from app.schemas.problems import LearningState


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return min(max(value, lower), upper)


class UserConceptStatRepository:
    def __init__(self, db: Session):
        self.db = db

    def update_for_feedback(
        self,
        *,
        user_id: str,
        concepts: list[str],
        is_correct: bool,
        mistake_type: str | None,
        hint_count: int = 0,
        confidence_level: int | None = None,
        score: float | None = None,
        max_score: float | None = None,
        learning_state: LearningState = LearningState.unreported,
    ) -> UserConceptStatUpdateResult:
        review_queue: list[str] = []
        mastery_updates: list[ConceptMasteryUpdatePayload] = []
        now = datetime.now(timezone.utc)
        for concept in dict.fromkeys(concept.strip() for concept in concepts if concept.strip()):
            stat = self.db.get(UserConceptStat, {"user_id": user_id, "concept": concept})
            if stat is None:
                stat = UserConceptStat(user_id=user_id, concept=concept)
                self.db.add(stat)
                self.db.flush()

            stat.attempts += 1
            if is_correct:
                stat.correct_count += 1
                stat.mastery = clamp(
                    stat.mastery + self._correct_delta(hint_count, confidence_level=confidence_level)
                )
            else:
                stat.wrong_count += 1
                stat.mastery = clamp(
                    stat.mastery
                    - self._wrong_delta(
                        hint_count,
                        confidence_level=confidence_level,
                        score=score,
                        max_score=max_score,
                        learning_state=learning_state,
                    )
                )
                if mistake_type and mistake_type not in stat.mistake_types:
                    stat.mistake_types = [*stat.mistake_types, mistake_type]
                if stat.wrong_count >= 2:
                    review_queue.append(concept)
            stat.last_attempt_at = now
            mastery_updates.append(
                ConceptMasteryUpdatePayload(
                    concept=stat.concept,
                    attempts=stat.attempts,
                    correct_count=stat.correct_count,
                    wrong_count=stat.wrong_count,
                    mastery=stat.mastery,
                    mistake_types=stat.mistake_types,
                    should_review=concept in review_queue,
                    last_attempt_at=stat.last_attempt_at,
                )
            )
        self.db.flush()
        return UserConceptStatUpdateResult(
            recommended_review=review_queue,
            mastery_updates=mastery_updates,
        )

    def _correct_delta(self, hint_count: int, *, confidence_level: int | None = None) -> float:
        base = max(0.01, 0.05 - min(max(hint_count, 0), 4) * 0.01)
        if confidence_level is None:
            return base
        if confidence_level >= 3:
            return min(0.07, round(base * 1.1, 4))
        return max(0.01, round(base * 0.7, 4))

    def _wrong_delta(
        self,
        hint_count: int,
        *,
        confidence_level: int | None = None,
        score: float | None = None,
        max_score: float | None = None,
        learning_state: LearningState = LearningState.unreported,
    ) -> float:
        base = min(0.11, 0.08 + min(max(hint_count, 0), 3) * 0.01)
        if confidence_level is None:
            return base
        if learning_state == LearningState.high_confidence_misconception:
            return min(0.13, round(base + 0.02, 4))
        if learning_state == LearningState.partial_understanding:
            score_ratio = self._score_ratio(score=score, max_score=max_score)
            return max(0.03, round(base * (1 - min(score_ratio, 0.8) * 0.5), 4))
        return base

    def _score_ratio(self, *, score: float | None, max_score: float | None) -> float:
        if score is None or max_score is None or max_score <= 0:
            return 0.0
        return min(max(float(score) / float(max_score), 0.0), 1.0)
