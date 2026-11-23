from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas.learning_voice import FeedbackCopyOutput, FeedbackSituation


BANNED_USER_VISIBLE_TERMS = (
    "LLM",
    "AI가",
    "인공지능이",
    "스키마",
    "schema",
    "chunk",
    "source_chunk",
    "source_chunk_ids",
    "quality_status",
    "quality_report",
    "validation",
    "검증기",
    "repository",
    "Agent",
    "payload",
    "DB",
    "API",
    "프롬프트",
    "분석 결과",
    "사용자 응답",
    "처리되었습니다",
    "오류가 발생했습니다",
)

ROBOTIC_PATTERNS = (
    "정답입니다",
    "오답입니다",
    "학습을 진행하세요",
    "이해도가 부족합니다",
    "다음 단계를 수행하십시오",
    "해당 개념",
    "제공합니다",
    "생성되었습니다",
    "판단됩니다",
    "추가 학습이 필요합니다",
)

TRANSLATION_LIKE_TERMS = (
    "당신",
    "사용자",
    "사용자의",
    "응답",
    "해당",
    "수행",
    "진행하십시오",
    "하시기 바랍니다",
)

BLAMING_PATTERNS = (
    "틀렸습니다",
    "틀렸어요",
    "계속 틀리고",
    "부족합니다",
    "이해하지 못했습니다",
    "못합니다",
    "실패",
)

GENERIC_PRAISE = (
    "훌륭해요",
    "대단해요",
    "완벽해요",
    "천재예요",
    "정말 잘했어요",
)

UNSUPPORTED_CERTAINTY_PATTERNS = (
    "무조건",
    "반드시 정답",
    "100%",
    "완전히 이해했어요",
)

GENERIC_ACTION_LABELS = (
    "진행",
    "확인",
    "다음",
    "학습 시작",
    "시작",
)

FRIENDLY_EDU_MARKERS = (
    "요",
    "세요",
    "볼까요",
    "해볼게요",
    "좋아요",
    "괜찮아요",
    "같이",
    "천천히",
)


@dataclass(frozen=True)
class LearningCopyQualityResult:
    status: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.status == "passed"


class LearningCopyQualityChecker:
    def check_text(self, text: str, *, situation: FeedbackSituation | str | None = None) -> LearningCopyQualityResult:
        errors: list[str] = []
        warnings: list[str] = []
        normalized = _normalize(text)

        if not normalized:
            errors.append("copy must not be empty")
            return LearningCopyQualityResult(status="failed", errors=errors)

        errors.extend(_contains_any(normalized, BANNED_USER_VISIBLE_TERMS, "copy exposes internal term"))
        errors.extend(_contains_any(normalized, ROBOTIC_PATTERNS, "copy uses robotic phrase"))
        errors.extend(_contains_any(normalized, TRANSLATION_LIKE_TERMS, "copy uses translated or awkward term"))
        errors.extend(_contains_any(normalized, UNSUPPORTED_CERTAINTY_PATTERNS, "copy sounds too certain"))

        situation_value = str(situation or "")
        if situation_value in {
            FeedbackSituation.wrong.value,
            FeedbackSituation.partially_correct.value,
            FeedbackSituation.repeated_wrong.value,
        }:
            errors.extend(_contains_any(normalized, BLAMING_PATTERNS, "copy blames the learner"))

        if situation_value == FeedbackSituation.correct.value and any(phrase in normalized for phrase in GENERIC_PRAISE):
            if not _has_specific_reason(normalized):
                errors.append("correct copy praises without a concrete reason")

        sentence_count = _sentence_count(text)
        if sentence_count > 5:
            warnings.append("copy has many sentences; check readability")
        if _longest_sentence_length(text) > 180:
            warnings.append("copy has a long sentence; split it if possible")
        if _emoji_count(text) > 3:
            warnings.append("copy has many emoji; check that the tone still feels reliable")

        return LearningCopyQualityResult(
            status="passed" if not errors else "failed",
            errors=list(dict.fromkeys(errors)),
            warnings=list(dict.fromkeys(warnings)),
        )

    def check_output(
        self,
        output: FeedbackCopyOutput,
        *,
        situation: FeedbackSituation | str | None = None,
    ) -> LearningCopyQualityResult:
        errors: list[str] = []
        warnings: list[str] = []
        situation_value = str(situation or "")

        for field_name, text in (
            ("title", output.title),
            ("body", output.body),
            ("next_action_label", output.next_action_label or ""),
            ("secondary_action_label", output.secondary_action_label or ""),
        ):
            if not text:
                continue
            result = self.check_text(text, situation=situation)
            errors.extend(f"{field_name}: {error}" for error in result.errors)
            warnings.extend(f"{field_name}: {warning}" for warning in result.warnings)

        if situation_value in {
            FeedbackSituation.wrong.value,
            FeedbackSituation.partially_correct.value,
            FeedbackSituation.repeated_wrong.value,
            FeedbackSituation.hint_requested.value,
            FeedbackSituation.stuck.value,
            FeedbackSituation.error.value,
        } and not output.next_action_label:
            errors.append("copy must include a next action label")

        if output.next_action_label and output.next_action_label.strip() in GENERIC_ACTION_LABELS:
            errors.append("next action label is too generic")

        if situation_value and not _has_friendly_education_tone(output):
            errors.append("copy should use friendly education-site tone")

        return LearningCopyQualityResult(
            status="passed" if not errors else "failed",
            errors=list(dict.fromkeys(errors)),
            warnings=list(dict.fromkeys(warnings)),
        )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _contains_any(text: str, phrases: tuple[str, ...], reason: str) -> list[str]:
    lower_text = text.lower()
    errors = []
    for phrase in phrases:
        needle = phrase.lower()
        if needle in lower_text:
            errors.append(f"{reason}: {phrase}")
    return errors


def _sentence_count(text: str) -> int:
    return len([sentence for sentence in re.split(r"[.!?\n。]+", text) if sentence.strip()])


def _longest_sentence_length(text: str) -> int:
    sentences = [sentence.strip() for sentence in re.split(r"[.!?\n。]+", text) if sentence.strip()]
    if not sentences:
        return 0
    return max(len(sentence) for sentence in sentences)


def _has_specific_reason(text: str) -> bool:
    return any(marker in text for marker in ("특히", "조건", "흐름", "이유", "비교", "순서", "예시", "근거"))


def _emoji_count(text: str) -> int:
    return len(re.findall(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", text))


def _has_friendly_education_tone(output: FeedbackCopyOutput) -> bool:
    combined = " ".join(
        text
        for text in (
            output.title,
            output.body,
            output.next_action_label or "",
            output.secondary_action_label or "",
        )
        if text
    )
    return any(marker in combined for marker in FRIENDLY_EDU_MARKERS)
