from sqlalchemy.orm import Session

from app.models import ProblemHintEvent


class ProblemHintRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        problem_id: str,
        user_id: str,
        level: int,
        mode: str,
        hint_text: str,
        answer_revealed: bool = False,
    ) -> ProblemHintEvent:
        event = ProblemHintEvent(
            problem_id=problem_id,
            user_id=user_id,
            level=level,
            mode=mode,
            hint_text=hint_text,
            answer_revealed=answer_revealed,
        )
        self.db.add(event)
        self.db.flush()
        return event

    def count_for_problem_user(self, *, problem_id: str, user_id: str) -> int:
        return (
            self.db.query(ProblemHintEvent)
            .filter(
                ProblemHintEvent.problem_id == problem_id,
                ProblemHintEvent.user_id == user_id,
            )
            .count()
        )
