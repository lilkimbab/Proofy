from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Literal

from app.schemas.quality import EvalUsageLedgerRecord, RejectedCandidateArtifactRecord


REJECTED_CANDIDATES_JSONL_NAME = "rejected_candidates.jsonl"
EVAL_USAGE_LEDGER_JSONL_NAME = "eval_usage_ledger.jsonl"


class RejectedCandidateArtifactWriter:
    def __init__(
        self,
        output_dir: Path | str | None,
        *,
        export_mode: Literal["redacted", "full"] = "redacted",
    ):
        self.output_dir = Path(output_dir) if output_dir is not None else None
        self.export_mode = export_mode if export_mode in {"redacted", "full"} else "redacted"

    def write_rejected_candidate(
        self,
        *,
        case_id: str,
        repeat_index: int,
        attempt_index: int,
        candidate_index: int,
        candidate: dict,
        kernel_type: str | None,
        problem_style: str | None,
        selected_atom_ids: list[str],
        selected_atom_chunk_ids: list[str],
        evidence_obligation_issues: list[str] | None = None,
        quality_errors: list[str] | None = None,
        rejection_categories: dict[str, int] | None = None,
        usage: dict[str, object] | None = None,
    ) -> None:
        if self.output_dir is None:
            return
        usage = usage or {}
        record = RejectedCandidateArtifactRecord(
            case_id=case_id,
            repeat_index=repeat_index,
            attempt_index=attempt_index,
            candidate_index=candidate_index,
            document_id=self._str_or_none(candidate.get("document_id")),
            type=self._str_or_none(candidate.get("type")),
            kernel_type=kernel_type,
            problem_style=problem_style,
            question_preview=self._preview(candidate.get("question")),
            choices_preview=self._choices_preview(candidate.get("choices")),
            answer_preview=self._sensitive_preview(candidate.get("answer")),
            explanation_preview=self._sensitive_preview(candidate.get("explanation")),
            rubric_preview=self._sensitive_preview(candidate.get("rubric")),
            source_chunk_ids=self._string_list(candidate.get("source_chunk_ids")),
            selected_atom_ids=list(selected_atom_ids),
            selected_atom_chunk_ids=list(selected_atom_chunk_ids),
            evidence_obligation_issues=list(evidence_obligation_issues or []),
            quality_errors=list(quality_errors or []),
            rejection_categories=dict(rejection_categories or {}),
            llm_model=self._str_or_none(usage.get("model")),
            input_tokens=self._int_or_none(usage.get("input_tokens")),
            output_tokens=self._int_or_none(usage.get("output_tokens")),
            total_tokens=self._int_or_none(usage.get("total_tokens")),
            created_at=self._now_iso(),
        )
        self._append_jsonl(REJECTED_CANDIDATES_JSONL_NAME, record.model_dump(mode="json"))

    def write_rejected_payload_candidates(
        self,
        *,
        case_id: str,
        repeat_index: int,
        attempt_index: int,
        payload: object,
        kernel_type: str | None,
        problem_style: str | None,
        selected_atom_ids: list[str],
        selected_atom_chunk_ids: list[str],
        quality_errors: list[str] | None = None,
        rejection_categories: dict[str, int] | None = None,
        usage: dict[str, object] | None = None,
    ) -> None:
        for candidate_index, candidate in enumerate(self._payload_candidates(payload)):
            self.write_rejected_candidate(
                case_id=case_id,
                repeat_index=repeat_index,
                attempt_index=attempt_index,
                candidate_index=candidate_index,
                candidate=candidate,
                kernel_type=kernel_type,
                problem_style=problem_style,
                selected_atom_ids=selected_atom_ids,
                selected_atom_chunk_ids=selected_atom_chunk_ids,
                quality_errors=quality_errors,
                rejection_categories=rejection_categories,
                usage=usage,
            )

    def write_usage(
        self,
        *,
        case_id: str,
        repeat_index: int,
        attempt_index: int,
        usage: dict[str, object],
        generation_mode: str | None,
        failure_status: str | None,
    ) -> None:
        if self.output_dir is None or not usage:
            return
        if not any(usage.get(key) is not None for key in ("model", "input_tokens", "output_tokens", "total_tokens")):
            return
        record = EvalUsageLedgerRecord(
            case_id=case_id,
            repeat_index=repeat_index,
            attempt_index=attempt_index,
            model=self._str_or_none(usage.get("model")),
            input_tokens=self._int_or_none(usage.get("input_tokens")),
            output_tokens=self._int_or_none(usage.get("output_tokens")),
            total_tokens=self._int_or_none(usage.get("total_tokens")),
            estimated_cost_krw=self._float_or_none(usage.get("estimated_cost_krw")),
            generation_mode=generation_mode,
            failure_status=failure_status,
            created_at=self._now_iso(),
        )
        self._append_jsonl(EVAL_USAGE_LEDGER_JSONL_NAME, record.model_dump(mode="json"))

    def _append_jsonl(self, filename: str, payload: dict) -> None:
        assert self.output_dir is not None
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with (self.output_dir / filename).open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def _payload_candidates(self, payload: object) -> list[dict]:
        if isinstance(payload, dict):
            problems = payload.get("problems")
            if isinstance(problems, list):
                return [item for item in problems if isinstance(item, dict)]
            return [payload]
        return []

    def _sensitive_preview(self, value: object) -> str | None:
        if value is None:
            return None
        if self.export_mode != "full":
            return "[redacted]"
        return self._preview(value)

    def _choices_preview(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        previews: list[str] = []
        for choice in value[:6]:
            if isinstance(choice, dict):
                text = choice.get("text")
                choice_id = choice.get("id")
                label = f"{choice_id}: {text}" if choice_id is not None else text
                preview = self._preview(label)
            else:
                preview = self._preview(choice)
            if preview:
                previews.append(preview)
        return previews

    def _preview(self, value: object, *, limit: int = 500) -> str | None:
        if value is None:
            return None
        text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        text = " ".join(text.split())
        if len(text) <= limit:
            return text
        return text[: limit - 1].rstrip() + "…"

    def _string_list(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]

    def _str_or_none(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value)
        return text if text else None

    def _int_or_none(self, value: object) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _float_or_none(self, value: object) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()
