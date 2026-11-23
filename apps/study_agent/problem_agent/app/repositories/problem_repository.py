from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Problem
from app.schemas.integration_contracts import ProblemStoragePayload


class ProblemRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, user_id: str, problem_data: dict) -> Problem:
        payload = ProblemStoragePayload.model_validate({"user_id": user_id, **problem_data})
        data = payload.model_dump(mode="json")
        problem_user_id = data.pop("user_id")
        problem = Problem(user_id=problem_user_id, **data)
        self.db.add(problem)
        self.db.flush()
        return problem

    def create_many(self, *, user_id: str, problems_data: list[dict]) -> list[Problem]:
        problems: list[Problem] = []
        for problem_data in problems_data:
            payload = ProblemStoragePayload.model_validate({"user_id": user_id, **problem_data})
            data = payload.model_dump(mode="json")
            problem_user_id = data.pop("user_id")
            problems.append(Problem(user_id=problem_user_id, **data))
        if not problems:
            return []
        self.db.add_all(problems)
        self.db.flush()
        return problems

    def get(self, problem_id: str) -> Problem | None:
        return self.db.get(Problem, problem_id)

    def list_recent_for_user_document(
        self,
        *,
        user_id: str,
        document_id: str,
        limit: int = 200,
    ) -> list[Problem]:
        return (
            self.db.query(Problem)
            .filter(Problem.user_id == user_id, Problem.document_id == document_id)
            .order_by(Problem.created_at.desc())
            .limit(limit)
            .all()
        )

    def count_generated_for_user_since(
        self,
        *,
        user_id: str,
        since: datetime,
        high_rigor_only: bool = False,
    ) -> int:
        query = self.db.query(Problem).filter(Problem.user_id == user_id, Problem.created_at >= since)
        if high_rigor_only:
            query = query.filter(
                (Problem.difficulty == "hard")
                | (Problem.bloom_level.in_(["analyze", "evaluate", "create"]))
            )
        return query.count()
