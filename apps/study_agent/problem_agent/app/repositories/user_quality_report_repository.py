from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import UserQualityReport
from app.schemas.problems import QualityReportRequest


class UserQualityReportRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, user_id: str, request: QualityReportRequest) -> UserQualityReport:
        report = UserQualityReport(
            user_id=user_id,
            target_type=request.target_type.value,
            target_id=request.target_id,
            reason=request.reason.value,
            message=request.message,
            status="open",
        )
        self.db.add(report)
        self.db.flush()
        return report

    def list_for_user(
        self,
        *,
        user_id: str,
        target_type: str | None = None,
        limit: int = 100,
    ) -> tuple[list[UserQualityReport], int]:
        query = self.db.query(UserQualityReport).filter(UserQualityReport.user_id == user_id)
        if target_type:
            query = query.filter(UserQualityReport.target_type == target_type)
        total = query.count()
        items = query.order_by(UserQualityReport.created_at.desc()).limit(limit).all()
        return items, total
