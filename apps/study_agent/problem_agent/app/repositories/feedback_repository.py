from sqlalchemy.orm import Session

from app.models import Feedback
from app.schemas.integration_contracts import FeedbackStoragePayload


class FeedbackRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, feedback_data: dict) -> Feedback:
        payload = FeedbackStoragePayload.model_validate(feedback_data)
        feedback = Feedback(**payload.model_dump(mode="json"))
        self.db.add(feedback)
        self.db.flush()
        return feedback

    def get(self, feedback_id: str) -> Feedback | None:
        return self.db.get(Feedback, feedback_id)

    def get_for_problem_and_user(self, *, problem_id: str, user_id: str) -> Feedback | None:
        return (
            self.db.query(Feedback)
            .filter(Feedback.problem_id == problem_id, Feedback.user_id == user_id)
            .order_by(Feedback.created_at.asc())
            .first()
        )
