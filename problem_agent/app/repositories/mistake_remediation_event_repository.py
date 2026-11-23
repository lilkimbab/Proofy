from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import MistakeRemediationEvent
from app.models.entities import utcnow
from app.schemas.integration_contracts import MistakeRemediationEventPayload


class MistakeRemediationEventRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, event_data: dict) -> MistakeRemediationEvent:
        payload = MistakeRemediationEventPayload.model_validate(event_data)
        event = MistakeRemediationEvent(**payload.model_dump(mode="json"))
        self.db.add(event)
        self.db.flush()
        return event

    def get(self, event_id: str) -> MistakeRemediationEvent | None:
        return self.db.get(MistakeRemediationEvent, event_id)

    def get_for_followup_problem(self, *, user_id: str, followup_problem_id: str) -> MistakeRemediationEvent | None:
        return (
            self.db.query(MistakeRemediationEvent)
            .filter(
                MistakeRemediationEvent.user_id == user_id,
                MistakeRemediationEvent.followup_problem_id == followup_problem_id,
            )
            .order_by(MistakeRemediationEvent.created_at.desc())
            .first()
        )

    def get_for_feedback_and_followup_problem(
        self,
        *,
        user_id: str,
        source_feedback_id: str,
        followup_problem_id: str,
    ) -> MistakeRemediationEvent | None:
        return (
            self.db.query(MistakeRemediationEvent)
            .filter(
                MistakeRemediationEvent.user_id == user_id,
                MistakeRemediationEvent.source_feedback_id == source_feedback_id,
                MistakeRemediationEvent.followup_problem_id == followup_problem_id,
            )
            .order_by(MistakeRemediationEvent.created_at.desc())
            .first()
        )

    def set_followup_content_id(self, *, event_id: str, followup_content_id: str) -> MistakeRemediationEvent | None:
        event = self.get(event_id)
        if event is None:
            return None
        event.followup_content_id = followup_content_id
        self.db.flush()
        return event

    def record_followup_result(
        self,
        *,
        user_id: str,
        followup_problem_id: str,
        is_correct: bool,
        score: float,
        max_score: float,
        mistake_type: str | None,
    ) -> MistakeRemediationEvent | None:
        event = self.get_for_followup_problem(user_id=user_id, followup_problem_id=followup_problem_id)
        if event is None:
            return None

        resolved = is_correct or (max_score > 0 and score / max_score >= 0.8)
        if resolved:
            event.resolved = True
            event.resolved_at = utcnow()
        else:
            event.resolved = False
            if mistake_type and event.target_mistake_type and mistake_type == event.target_mistake_type:
                event.repeated_count += 1

        self.db.flush()
        return event

    def record_followup_action_result(
        self,
        *,
        user_id: str,
        source_feedback_id: str,
        followup_problem_id: str,
        is_successful: bool,
    ) -> MistakeRemediationEvent | None:
        event = self.get_for_feedback_and_followup_problem(
            user_id=user_id,
            source_feedback_id=source_feedback_id,
            followup_problem_id=followup_problem_id,
        )
        if event is None:
            return None

        if is_successful:
            event.resolved = True
            event.resolved_at = event.resolved_at or utcnow()
        elif event.resolved is None:
            event.resolved = False
            event.repeated_count += 1

        self.db.flush()
        return event

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()
