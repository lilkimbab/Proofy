from sqlalchemy.orm import Session

from app.models import Feedback, FeedbackActionEvent
from app.schemas.problems import FeedbackActionEventRequest


class FeedbackActionEventRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, feedback: Feedback, request: FeedbackActionEventRequest) -> FeedbackActionEvent:
        event = FeedbackActionEvent(
            feedback_id=feedback.id,
            problem_id=feedback.problem_id,
            user_id=feedback.user_id,
            event_type=request.event_type.value,
            action_type=request.action_type.value if request.action_type else None,
            target_problem_id=request.target_problem_id,
            target_content_id=request.target_content_id,
            is_successful=request.is_successful,
            helpful_rating=request.helpful_rating,
            event_metadata=request.event_metadata,
        )
        self.db.add(event)
        self.db.flush()
        return event

    def list_for_feedback(
        self,
        *,
        feedback_id: str,
        user_id: str,
        limit: int = 50,
    ) -> tuple[list[FeedbackActionEvent], int]:
        query = self.db.query(FeedbackActionEvent).filter(
            FeedbackActionEvent.feedback_id == feedback_id,
            FeedbackActionEvent.user_id == user_id,
        )
        total = query.count()
        items = query.order_by(FeedbackActionEvent.created_at.asc()).limit(limit).all()
        return items, total
