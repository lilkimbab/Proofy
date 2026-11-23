from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from app.schemas.integration_contracts import RetrievedChunk
from app.agents.korean_style import korean_tone_issues
from app.schemas.learning_contents import LearningContentBase, LearningContentType
from app.schemas.quality import QualityFlag, QualityStatus
from app.services.request_safety import contains_unsafe_instruction_text


@dataclass(frozen=True)
class LearningContentQualityCheck:
    is_valid: bool
    errors: list[str]
    flags: list[QualityFlag]
    source_coverage_score: float | None
    verbatim_overlap_chars: int


class LearningContentQualityChecker:
    """Deterministic quality checks for Phase 14 learning contents.

    This checker is intentionally stricter than the schema. Schemas prove shape;
    this class decides whether generated content is good enough to save.
    """

    def validate(
        self,
        content: LearningContentBase,
        *,
        retrieved_chunks: list[RetrievedChunk],
    ) -> LearningContentQualityCheck:
        errors: list[str] = []
        flags: list[QualityFlag] = []

        chunk_by_id = {chunk.chunk_id: chunk for chunk in retrieved_chunks}
        if len(chunk_by_id) != len(retrieved_chunks):
            errors.append("retrieved_chunks must not include duplicate chunk_id values")

        missing_chunk_ids = [chunk_id for chunk_id in content.source_chunk_ids if chunk_id not in chunk_by_id]
        if missing_chunk_ids:
            errors.append(f"source_chunk_ids not found in retrieved chunks: {', '.join(missing_chunk_ids)}")
            flags.append(QualityFlag.unsupported_source)

        mismatched_document_ids = [
            chunk_id
            for chunk_id in content.source_chunk_ids
            if chunk_id in chunk_by_id and chunk_by_id[chunk_id].document_id != content.document_id
        ]
        if mismatched_document_ids:
            errors.append(f"source_chunk_ids belong to a different document: {', '.join(mismatched_document_ids)}")
            flags.append(QualityFlag.unsupported_source)

        if content.quality_status == QualityStatus.passed and not content.quality_report.source_grounded:
            errors.append("passed learning content must be source grounded")
            flags.append(QualityFlag.unsupported_source)

        cited_chunks = [chunk_by_id[chunk_id] for chunk_id in content.source_chunk_ids if chunk_id in chunk_by_id]
        grounding = self._source_grounding_check(content=content, cited_chunks=cited_chunks)
        flags.extend(grounding.flags)

        if QualityFlag.weak_source_overlap in grounding.flags:
            errors.append("learning content has weak source overlap")
        if QualityFlag.unsupported_source in grounding.flags:
            errors.append("learning content includes unsupported numbers")
        if QualityFlag.source_verbatim_overlap in grounding.flags:
            errors.append("learning content copies too much source text verbatim")

        content_type_errors, content_type_flags = self._content_type_quality(content)
        errors.extend(content_type_errors)
        flags.extend(content_type_flags)

        content_text = self._content_text(content.payload)
        if contains_unsafe_instruction_text(content_text):
            errors.append("learning content leaks prompt-injection text")
            flags.append(QualityFlag.prompt_injection_leak)

        tone_issues = korean_tone_issues(content_text)
        if tone_issues and content.content_type != LearningContentType.mistake_drill:
            errors.extend(f"learning content tone issue: {issue}" for issue in tone_issues)
            flags.append(QualityFlag.ai_like_wording)

        unique_flags = list(dict.fromkeys(flags))
        return LearningContentQualityCheck(
            is_valid=not errors,
            errors=list(dict.fromkeys(errors)),
            flags=unique_flags,
            source_coverage_score=grounding.source_coverage_score,
            verbatim_overlap_chars=grounding.verbatim_overlap_chars,
        )

    def _content_type_quality(self, content: LearningContentBase) -> tuple[list[str], list[QualityFlag]]:
        if content.content_type == LearningContentType.flashcard:
            return self._flashcard_quality(content.payload)
        if content.content_type == LearningContentType.cloze:
            return self._cloze_quality(content.payload)
        if content.content_type == LearningContentType.true_false:
            return self._true_false_quality(content.payload)
        if content.content_type == LearningContentType.ordering:
            return self._ordering_quality(content.payload)
        if content.content_type == LearningContentType.matching:
            return self._matching_quality(content.payload)
        if content.content_type == LearningContentType.worked_example:
            return self._worked_example_quality(content.payload)
        if content.content_type == LearningContentType.mistake_drill:
            return self._mistake_drill_quality(content.payload)
        if content.content_type == LearningContentType.mini_exam:
            return self._mini_exam_quality(content.payload)
        if content.content_type == LearningContentType.concept_summary_card:
            return self._concept_summary_card_quality(content.payload)
        return [], []

    def _flashcard_quality(self, payload: dict[str, Any]) -> tuple[list[str], list[QualityFlag]]:
        errors: list[str] = []
        flags: list[QualityFlag] = []
        front = str(payload.get("front") or "").strip()
        back = str(payload.get("back") or "").strip()
        explanation = str(payload.get("explanation") or "").strip()
        if len(front) < 8:
            errors.append("flashcard front is too short")
            flags.append(QualityFlag.unfocused_stem)
        if len(back) > 420:
            errors.append("flashcard back is too long for a concept card")
            flags.append(QualityFlag.unfocused_stem)
        if len(self._content_tokens(f"{front} {back} {explanation}")) < 3:
            errors.append("flashcard is too shallow")
            flags.append(QualityFlag.weak_source_overlap)
        return errors, flags

    def _cloze_quality(self, payload: dict[str, Any]) -> tuple[list[str], list[QualityFlag]]:
        errors: list[str] = []
        flags: list[QualityFlag] = []
        prompt = str(payload.get("prompt") or "").strip()
        answer = str(payload.get("answer") or "").strip()
        blank_count = prompt.count("____")
        if blank_count != 1:
            errors.append("cloze content must contain exactly one blank")
            flags.append(QualityFlag.unfocused_stem)
        if len(answer) <= 1:
            errors.append("cloze answer is too short")
            flags.append(QualityFlag.unfocused_stem)
        if answer and answer in prompt.replace("____", ""):
            errors.append("cloze prompt leaks the answer")
            flags.append(QualityFlag.answer_leak)
        return errors, flags

    def _true_false_quality(self, payload: dict[str, Any]) -> tuple[list[str], list[QualityFlag]]:
        errors: list[str] = []
        flags: list[QualityFlag] = []
        statement = str(payload.get("statement") or "").strip()
        if len(statement) < 14:
            errors.append("true_false statement is too short")
            flags.append(QualityFlag.unfocused_stem)
        generic_patterns = (
            "중요하다",
            "관련이 있다",
            "필요하다",
            "좋다",
            "나쁘다",
            "맞다",
            "틀리다",
        )
        if any(pattern in statement for pattern in generic_patterns) and len(self._content_tokens(statement)) < 4:
            errors.append("true_false statement is too generic")
            flags.append(QualityFlag.unfocused_stem)
        return errors, flags

    def _ordering_quality(self, payload: dict[str, Any]) -> tuple[list[str], list[QualityFlag]]:
        errors: list[str] = []
        flags: list[QualityFlag] = []
        prompt = str(payload.get("prompt") or "").strip()
        items = payload.get("items") or []
        if len(prompt) < 12:
            errors.append("ordering prompt is too short")
            flags.append(QualityFlag.unfocused_stem)
        item_texts = [str(item.get("text") or "").strip() for item in items if isinstance(item, dict)]
        if len(set(item_texts)) != len(item_texts):
            errors.append("ordering item texts must be unique")
            flags.append(QualityFlag.unfocused_stem)
        if any(len(text) < 6 for text in item_texts):
            errors.append("ordering items are too shallow")
            flags.append(QualityFlag.unfocused_stem)
        return errors, flags

    def _matching_quality(self, payload: dict[str, Any]) -> tuple[list[str], list[QualityFlag]]:
        errors: list[str] = []
        flags: list[QualityFlag] = []
        prompt = str(payload.get("prompt") or "").strip()
        pairs = payload.get("pairs") or []
        if len(prompt) < 12:
            errors.append("matching prompt is too short")
            flags.append(QualityFlag.unfocused_stem)
        for pair in pairs:
            if not isinstance(pair, dict):
                continue
            left = str(pair.get("left") or "").strip()
            right = str(pair.get("right") or "").strip()
            if left and right and left == right:
                errors.append("matching pair cannot use the same text on both sides")
                flags.append(QualityFlag.unfocused_stem)
            if len(right) < 4:
                errors.append("matching pair is too shallow")
                flags.append(QualityFlag.unfocused_stem)
        return errors, flags

    def _worked_example_quality(self, payload: dict[str, Any]) -> tuple[list[str], list[QualityFlag]]:
        errors: list[str] = []
        flags: list[QualityFlag] = []
        steps = payload.get("steps") or []
        if len(steps) < 2:
            errors.append("worked_example requires at least two solution steps")
            flags.append(QualityFlag.unfocused_stem)
        orders = [int(step.get("order")) for step in steps if isinstance(step, dict) and step.get("order") is not None]
        if orders and sorted(orders) != list(range(1, len(orders) + 1)):
            errors.append("worked_example step order must be consecutive from 1")
            flags.append(QualityFlag.unfocused_stem)
        step_texts = [str(step.get("text") or "").strip() for step in steps if isinstance(step, dict)]
        if len(set(step_texts)) != len(step_texts):
            errors.append("worked_example steps must not repeat the same text")
            flags.append(QualityFlag.unfocused_stem)
        if any(len(text) < 8 for text in step_texts):
            errors.append("worked_example steps are too shallow")
            flags.append(QualityFlag.unfocused_stem)
        return errors, flags

    def _mistake_drill_quality(self, payload: dict[str, Any]) -> tuple[list[str], list[QualityFlag]]:
        errors: list[str] = []
        flags: list[QualityFlag] = []
        if not str(payload.get("generated_problem_id") or "").strip():
            errors.append("mistake_drill requires generated_problem_id")
            flags.append(QualityFlag.unfocused_stem)
        if not str(payload.get("seed_problem_id") or "").strip():
            errors.append("mistake_drill requires seed_problem_id")
            flags.append(QualityFlag.unfocused_stem)
        if not str(payload.get("seed_feedback_id") or "").strip():
            errors.append("mistake_drill requires seed_feedback_id")
            flags.append(QualityFlag.unfocused_stem)
        target_concepts = payload.get("target_concepts") or []
        if not target_concepts:
            errors.append("mistake_drill requires target_concepts")
            flags.append(QualityFlag.unfocused_stem)
        return errors, flags

    def _mini_exam_quality(self, payload: dict[str, Any]) -> tuple[list[str], list[QualityFlag]]:
        errors: list[str] = []
        flags: list[QualityFlag] = []
        title = str(payload.get("title") or "").strip()
        items = payload.get("items") or []
        if len(title) < 4:
            errors.append("mini_exam title is too short")
            flags.append(QualityFlag.unfocused_stem)
        if not items:
            errors.append("mini_exam requires at least one item")
            flags.append(QualityFlag.unfocused_stem)

        references: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                errors.append("mini_exam items must be objects")
                flags.append(QualityFlag.unfocused_stem)
                continue
            problem_id = str(item.get("problem_id") or "").strip()
            content_id = str(item.get("content_id") or "").strip()
            reference = problem_id or content_id
            if not reference:
                errors.append("mini_exam item requires problem_id or content_id")
                flags.append(QualityFlag.unfocused_stem)
            else:
                references.append(reference)
        if len(set(references)) != len(references):
            errors.append("mini_exam item references must be unique")
            flags.append(QualityFlag.unfocused_stem)
        return errors, flags

    def _concept_summary_card_quality(self, payload: dict[str, Any]) -> tuple[list[str], list[QualityFlag]]:
        errors: list[str] = []
        flags: list[QualityFlag] = []
        title = str(payload.get("title") or "").strip()
        summary = str(payload.get("summary") or "").strip()
        key_points = [str(point or "").strip() for point in (payload.get("key_points") or [])]
        if len(summary) < 16:
            errors.append("concept_summary_card summary is too short")
            flags.append(QualityFlag.unfocused_stem)
        if title and summary and title == summary:
            errors.append("concept_summary_card title and summary must be different")
            flags.append(QualityFlag.unfocused_stem)
        if len(key_points) < 2:
            errors.append("concept_summary_card requires at least two key points")
            flags.append(QualityFlag.unfocused_stem)
        if len(set(key_points)) != len(key_points):
            errors.append("concept_summary_card key points must be unique")
            flags.append(QualityFlag.unfocused_stem)
        if any(len(point) < 4 for point in key_points):
            errors.append("concept_summary_card key points are too shallow")
            flags.append(QualityFlag.unfocused_stem)
        return errors, flags

    def _source_grounding_check(
        self,
        *,
        content: LearningContentBase,
        cited_chunks: list[RetrievedChunk],
    ) -> LearningContentQualityCheck:
        if not cited_chunks:
            return LearningContentQualityCheck(
                is_valid=False,
                errors=[],
                flags=[QualityFlag.unsupported_source],
                source_coverage_score=0,
                verbatim_overlap_chars=0,
            )

        source_text = " ".join(
            " ".join([chunk.content, chunk.section_title or "", " ".join(chunk.concepts)])
            for chunk in cited_chunks
        )
        generated_text = self._content_text(content.payload)
        source_tokens = self._content_tokens(source_text)
        generated_tokens = self._content_tokens(generated_text)

        flags: list[QualityFlag] = []
        coverage_score: float | None = None
        if generated_tokens:
            overlap = source_tokens & generated_tokens
            coverage_score = round(len(overlap) / max(1, min(len(generated_tokens), len(source_tokens))), 3)
            if len(overlap) < min(2, len(generated_tokens)) or coverage_score < 0.12:
                flags.append(QualityFlag.weak_source_overlap)

        source_numbers = set(re.findall(r"\d+(?:\.\d+)?", source_text))
        generated_numbers = set(re.findall(r"\d+(?:\.\d+)?", generated_text))
        unsupported_numbers = {
            number
            for number in generated_numbers - source_numbers
            if number not in {"0", "1", "2", "3", "4", "5"}
        }
        if unsupported_numbers:
            flags.append(QualityFlag.unsupported_source)

        verbatim_overlap_chars = self._max_verbatim_source_overlap(generated_text=generated_text, cited_chunks=cited_chunks)
        if verbatim_overlap_chars >= 70:
            flags.append(QualityFlag.source_verbatim_overlap)

        return LearningContentQualityCheck(
            is_valid=not flags,
            errors=[],
            flags=list(dict.fromkeys(flags)),
            source_coverage_score=coverage_score,
            verbatim_overlap_chars=verbatim_overlap_chars,
        )

    def _content_text(self, payload: Any) -> str:
        if isinstance(payload, dict):
            metadata_keys = {
                "id",
                "content_id",
                "problem_id",
                "seed_problem_id",
                "seed_feedback_id",
                "generated_problem_id",
                "time_limit_seconds",
                "points",
                "blueprint",
                "content_type",
            }
            return " ".join(
                self._content_text(value)
                for key, value in payload.items()
                if key not in metadata_keys
            )
        if isinstance(payload, list):
            return " ".join(self._content_text(value) for value in payload)
        return str(payload or "")

    def _content_tokens(self, text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[가-힣A-Za-z0-9]+", text.lower())
            if len(token) >= 2 and token not in {"자료", "설명", "문제", "정답", "해설", "개념", "확인"}
        }

    def _max_verbatim_source_overlap(self, *, generated_text: str, cited_chunks: list[RetrievedChunk]) -> int:
        normalized_generated = self._normalize_whitespace(generated_text)
        max_overlap = 0
        for chunk in cited_chunks:
            source = self._normalize_whitespace(chunk.content)
            for window_size in range(min(len(source), 220), 39, -1):
                found = False
                for start in range(0, max(1, len(source) - window_size + 1), 10):
                    window = source[start : start + window_size]
                    if len(window.strip()) < 40:
                        continue
                    if window in normalized_generated:
                        max_overlap = max(max_overlap, len(window))
                        found = True
                        break
                if found:
                    break
        return max_overlap

    def _normalize_whitespace(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()
