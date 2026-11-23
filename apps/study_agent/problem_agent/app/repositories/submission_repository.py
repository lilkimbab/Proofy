from sqlalchemy.orm import Session

from app.models import Submission
from app.schemas.integration_contracts import SubmissionStoragePayload


class SubmissionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        problem_id: str,
        user_id: str,
        answer: dict,
        solution_steps: str | None,
        elapsed_time_sec: float | None = None,
        hint_count: int = 0,
        confidence_level: int | None = None,
    ) -> Submission:
        payload = SubmissionStoragePayload.model_validate(
            {
                "problem_id": problem_id,
                "user_id": user_id,
                "answer": answer,
                "solution_steps": solution_steps,
                "elapsed_time_sec": elapsed_time_sec,
                "hint_count": hint_count,
                "confidence_level": confidence_level,
            }
        )
        submission = Submission(**payload.model_dump(mode="json"))
        self.db.add(submission)
        self.db.flush()
        return submission
