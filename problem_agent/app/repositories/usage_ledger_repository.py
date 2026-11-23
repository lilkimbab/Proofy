from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import UsageLedger


class UsageLedgerRepository:
    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()

    def create_from_llm_client(
        self,
        *,
        user_id: str,
        feature: str,
        client: object,
        premium_reason: str | None = None,
    ) -> UsageLedger | None:
        if client is None:
            return None
        snapshot = self.usage_snapshot_from_llm_client(client)
        if snapshot is None:
            return None

        ledger = UsageLedger(
            user_id=user_id,
            feature=feature,
            model=snapshot["model"],
            request_id=getattr(client, "last_request_id", None),
            input_tokens=snapshot["input_tokens"],
            output_tokens=snapshot["output_tokens"],
            total_tokens=snapshot["total_tokens"],
            estimated_cost_krw=snapshot["estimated_cost_krw"],
            premium_model_used=snapshot["premium_model_used"],
            premium_reason=premium_reason if snapshot["premium_model_used"] else None,
        )
        self.db.add(ledger)
        self.db.flush()
        return ledger

    def usage_snapshot_from_llm_client(self, client: object | None) -> dict[str, Any] | None:
        if client is None:
            return None
        usage = getattr(client, "last_usage", None)
        model = getattr(client, "last_model", None)
        if not usage or not model:
            return None

        input_tokens = self._token_value(usage, "input_tokens", "prompt_tokens")
        output_tokens = self._token_value(usage, "output_tokens", "completion_tokens")
        total_tokens = self._token_value(usage, "total_tokens")
        if total_tokens is None and (input_tokens is not None or output_tokens is not None):
            total_tokens = int(input_tokens or 0) + int(output_tokens or 0)

        premium_model_used = self._is_premium_model(model)
        return {
            "model": str(model),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_krw": self._estimated_cost_krw(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                premium_model_used=premium_model_used,
            ),
            "premium_model_used": premium_model_used,
        }

    def list_for_user(
        self,
        *,
        user_id: str,
        feature: str | None = None,
        limit: int = 100,
        since: datetime | None = None,
    ) -> tuple[list[UsageLedger], int]:
        query = self.db.query(UsageLedger).filter(UsageLedger.user_id == user_id)
        if feature:
            query = query.filter(UsageLedger.feature == feature)
        if since is not None:
            query = query.filter(UsageLedger.created_at >= since)
        total = query.count()
        items = query.order_by(UsageLedger.created_at.desc()).limit(limit).all()
        return items, total

    def summary_for_user(
        self,
        *,
        user_id: str,
        feature: str | None = None,
        since: datetime | None = None,
    ) -> dict:
        query = self.db.query(UsageLedger).filter(UsageLedger.user_id == user_id)
        if feature:
            query = query.filter(UsageLedger.feature == feature)
        if since is not None:
            query = query.filter(UsageLedger.created_at >= since)
        aggregates = query.with_entities(
            func.count(UsageLedger.id),
            func.coalesce(func.sum(UsageLedger.input_tokens), 0),
            func.coalesce(func.sum(UsageLedger.output_tokens), 0),
            func.coalesce(func.sum(UsageLedger.total_tokens), 0),
            func.coalesce(func.sum(UsageLedger.estimated_cost_krw), 0),
            func.coalesce(func.sum(case((UsageLedger.premium_model_used.is_(True), 1), else_=0)), 0),
        ).one()
        total_calls = int(aggregates[0] or 0)
        total_input_tokens = int(aggregates[1] or 0)
        total_output_tokens = int(aggregates[2] or 0)
        total_tokens = int(aggregates[3] or 0)
        total_estimated_cost_krw = round(float(aggregates[4] or 0), 6)
        premium_call_count = int(aggregates[5] or 0)
        budget_limit = float(self.settings.llm_monthly_user_budget_krw or 0)
        budget_used_ratio = round(total_estimated_cost_krw / budget_limit, 3) if budget_limit > 0 else None
        return {
            "user_id": user_id,
            "feature": feature,
            "total_calls": total_calls,
            "premium_call_count": premium_call_count,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_tokens,
            "total_estimated_cost_krw": total_estimated_cost_krw,
            "budget_limit_krw": budget_limit if budget_limit > 0 else None,
            "budget_used_ratio": budget_used_ratio,
            "budget_status": self._budget_status(
                total_estimated_cost_krw=total_estimated_cost_krw,
                budget_limit_krw=budget_limit,
            ),
        }

    def _token_value(self, usage: dict[str, Any], *keys: str) -> int | None:
        for key in keys:
            value = usage.get(key)
            if value is not None:
                return int(value)
        return None

    def _is_premium_model(self, model: str) -> bool:
        premium_models = {
            self.settings.problem_quality_model,
            self.settings.grading_quality_model,
            self.settings.learning_content_quality_model,
        }
        return model in premium_models

    def _estimated_cost_krw(
        self,
        *,
        input_tokens: int | None,
        output_tokens: int | None,
        premium_model_used: bool,
    ) -> float | None:
        if input_tokens is None and output_tokens is None:
            return None
        if premium_model_used:
            input_price = self.settings.llm_premium_input_price_krw_per_1m_tokens
            output_price = self.settings.llm_premium_output_price_krw_per_1m_tokens
        else:
            input_price = self.settings.llm_standard_input_price_krw_per_1m_tokens
            output_price = self.settings.llm_standard_output_price_krw_per_1m_tokens
        cost = ((input_tokens or 0) / 1_000_000 * input_price) + ((output_tokens or 0) / 1_000_000 * output_price)
        return round(cost, 6)

    def _budget_status(self, *, total_estimated_cost_krw: float, budget_limit_krw: float) -> str:
        if budget_limit_krw <= 0:
            return "not_configured"
        if total_estimated_cost_krw >= budget_limit_krw:
            return "exceeded"
        if total_estimated_cost_krw >= budget_limit_krw * self.settings.llm_budget_warning_ratio:
            return "warning"
        return "ok"
