from __future__ import annotations

import re

from app.schemas.learning_contents import LearningContentBase, LearningContentType
from app.schemas.learning_voice import (
    FeedbackCopyInput,
    FeedbackCopyOutput,
    FeedbackSituation,
    LearningContentCopy,
    NextActionType,
)
from app.services.learning_copy_quality_checker import LearningCopyQualityChecker


NEXT_ACTION_LABELS: dict[NextActionType, str] = {
    NextActionType.retry: "힌트만 보고 다시 풀기",
    NextActionType.show_hint: "힌트만 보기",
    NextActionType.review_concept_card: "개념 카드로 30초 복습",
    NextActionType.solve_similar: "비슷한 문제 풀기",
    NextActionType.see_worked_example: "풀이 흐름 보기",
    NextActionType.mini_quiz: "짧은 점검 문제 풀기",
    NextActionType.mark_conditions: "조건 표시하고 다시 풀기",
    NextActionType.split_steps: "단계 나눠서 다시 풀기",
    NextActionType.compare_terms: "비슷한 용어 비교하기",
    NextActionType.review_formula: "공식 의미 먼저 보기",
    NextActionType.check_units: "단위만 체크하기",
    NextActionType.rewrite_answer: "내 답 다시 써보기",
    NextActionType.stop: "잠시 멈추기",
}

MISTAKE_COACHING: dict[str, dict[str, object]] = {
    "concept_misunderstanding": {
        "title_hint": "개념의 방향",
        "body": "이건 헷갈릴 만해요. 개념 이름은 맞게 보셨는데, 자료에서 말하는 관계의 방향이 살짝 바뀌었어요. 기준 문장 하나만 다시 잡으면 훨씬 깔끔해져요.",
        "next_action": NextActionType.review_concept_card,
        "secondary_action": NextActionType.solve_similar,
    },
    "missing_key_concept": {
        "title_hint": "빠진 핵심 조건",
        "body": "방향은 좋아요. 다만 교수님이 엄밀하게 보면 꼭 확인할 조건 하나가 빠져 있어요. 그 조건만 채우면 답이 훨씬 단단해져요.",
        "next_action": NextActionType.rewrite_answer,
        "secondary_action": NextActionType.review_concept_card,
    },
    "term_confusion": {
        "title_hint": "비슷한 용어",
        "body": "용어 두 개가 비슷해서 섞이기 쉬운 부분이에요. 뜻을 한 줄씩 나눠서 비교하면 차이가 바로 보여요.",
        "next_action": NextActionType.compare_terms,
        "secondary_action": NextActionType.solve_similar,
    },
    "calculation_error": {
        "title_hint": "계산 흐름",
        "body": "풀이 방향은 괜찮아요. 지금은 로직보다 중간 계산 흐름이 살짝 흔들린 상태예요. 식을 한 줄씩 나누면 실수를 훨씬 줄일 수 있어요.",
        "next_action": NextActionType.split_steps,
        "secondary_action": NextActionType.review_formula,
    },
    "logic_error": {
        "title_hint": "논리의 연결",
        "body": "각 문장은 괜찮아 보이지만, 앞뒤 연결에서 한 번 꺾인 부분이 있어요. 원인과 결과를 화살표로 이어보면 더 선명해져요.",
        "next_action": NextActionType.split_steps,
        "secondary_action": NextActionType.see_worked_example,
    },
    "misread_question": {
        "title_hint": "문제 조건",
        "body": "개념을 몰라서 틀린 느낌은 아니에요. 문제에서 묻는 조건을 살짝 다르게 읽으신 쪽에 가까워요. 먼저 묻는 것과 주어진 조건에 표시해보면 좋아요.",
        "next_action": NextActionType.mark_conditions,
        "secondary_action": NextActionType.retry,
    },
    "incomplete_answer": {
        "title_hint": "답안의 빈칸",
        "body": "큰 흐름은 잡으셨어요. 다만 설명이 중간에서 멈춘 느낌이라, 이유를 한 문장만 더 붙이면 서술형 답안으로 훨씬 안정적이에요.",
        "next_action": NextActionType.rewrite_answer,
        "secondary_action": NextActionType.see_worked_example,
    },
    "unit_error": {
        "title_hint": "단위",
        "body": "계산보다 단위에서 흔들린 부분이에요. 숫자를 다시 풀기 전에 단위만 먼저 맞춰보면 금방 정리돼요.",
        "next_action": NextActionType.check_units,
        "secondary_action": NextActionType.split_steps,
    },
}

CONTENT_INTROS: dict[LearningContentType, str] = {
    LearningContentType.flashcard: "📌 앞면에서는 용어를 확인하고, 뒷면에서는 실제 흐름을 같이 잡아볼까요?",
    LearningContentType.cloze: "✍️ 문장을 읽고, 중요한 개념어 하나를 채워볼까요?",
    LearningContentType.true_false: "⭕ 자료의 설명과 맞는지 같이 판단해볼까요?",
    LearningContentType.ordering: "🔢 자료에서 설명한 흐름대로 순서를 맞춰볼까요?",
    LearningContentType.matching: "🔗 용어와 설명을 서로 맞춰보면서 차이를 확인해볼까요?",
    LearningContentType.worked_example: "🧭 바로 답부터 보지 말고, 조건을 어떻게 나누는지 같이 볼게요.",
    LearningContentType.mistake_drill: "💪 방금 헷갈리신 지점을 다른 문제로 한 번 더 연습해볼게요.",
    LearningContentType.mini_exam: "📝 지금까지 나온 중요한 내용만 모아서 짧게 점검해볼까요?",
    LearningContentType.concept_summary_card: "✨ 먼저 용어와 흐름을 짧게 잡고 넘어가면 훨씬 깔끔해져요.",
}


class LearningVoiceRenderer:
    def __init__(self, *, copy_checker: LearningCopyQualityChecker | None = None):
        self.copy_checker = copy_checker or LearningCopyQualityChecker()

    def render_feedback(self, copy_input: FeedbackCopyInput) -> FeedbackCopyOutput:
        situation = copy_input.situation
        if situation == FeedbackSituation.correct:
            output = self._correct_feedback(copy_input)
        elif situation == FeedbackSituation.partially_correct:
            output = self._partially_correct_feedback(copy_input)
        elif situation == FeedbackSituation.repeated_wrong:
            output = self._repeated_wrong_feedback(copy_input)
        elif situation == FeedbackSituation.wrong:
            output = self._wrong_feedback(copy_input)
        elif situation == FeedbackSituation.hint_requested:
            output = self._hint_feedback(copy_input)
        elif situation == FeedbackSituation.error:
            output = self._error_feedback(copy_input)
        elif situation == FeedbackSituation.loading:
            output = FeedbackCopyOutput(
                title="좋은 문제로 만들 부분을 고르고 있어요 🔎",
                body="정의만 묻는 쉬운 문장은 빼고, 실제로 연습에 도움이 되는 부분만 추려볼게요.",
            )
        elif situation == FeedbackSituation.summary:
            output = FeedbackCopyOutput(
                title="이번 학습 흐름을 같이 정리해볼게요 ✨",
                body=self._safe_body(copy_input.evidence_summary, default="핵심은 맞힌 부분과 다시 볼 부분을 나눠서 보는 거예요. 이렇게 정리하면 다음 문제에서 훨씬 덜 흔들려요."),
                **self._next_action_fields(copy_input.next_action, default=NextActionType.review_concept_card),
            )
        else:
            output = FeedbackCopyOutput(
                title="한 단계만 같이 확인해볼까요? 👀",
                body=self._safe_body(copy_input.evidence_summary, default="이번 답에서 놓치기 쉬운 기준을 먼저 잡아보면 좋아요."),
                **self._next_action_fields(copy_input.next_action, default=NextActionType.show_hint),
            )
        output = self._apply_confidence_tone(output, confidence=copy_input.confidence)
        return self._checked_output(output, situation=situation, emoji_policy=copy_input.tone_profile.emoji_policy)

    def render_learning_content_copy(self, content: LearningContentBase) -> LearningContentCopy:
        concept = _first_text(content.concepts) or "이 내용"
        intro = CONTENT_INTROS.get(content.content_type, "이 부분을 짧게 연습해볼게요.")
        success = FeedbackCopyOutput(
            title="좋아요, 잘하셨어요 👍",
            body=f"특히 {concept}의 기준을 놓치지 않고 보신 점이 좋아요. 우리 비슷한 문제로 한 번 더 확인해볼까요?",
            **self._next_action_fields(None, default=NextActionType.solve_similar),
        )
        failure = self.render_feedback(
            FeedbackCopyInput(
                situation=FeedbackSituation.wrong,
                concept=concept,
                evidence_summary=self._failure_evidence_for_content(content),
                next_action=self._next_action_for_content(content.content_type),
            )
        )

        success = self._checked_output(success, situation=FeedbackSituation.correct, emoji_policy="contextual")
        return LearningContentCopy(intro=intro, success=success, failure=failure)

    def _correct_feedback(self, copy_input: FeedbackCopyInput) -> FeedbackCopyOutput:
        concept = _concept_label(copy_input.concept)
        body = self._safe_body(
            copy_input.evidence_summary,
            default=f"특히 {concept}의 조건을 놓치지 않고 보신 점이 좋아요. 이건 그냥 외운 게 아니라 기준을 잡고 고른 답에 가까워요.",
        )
        return FeedbackCopyOutput(
            title="좋아요, 잘하셨어요 👍",
            body=body,
            **self._next_action_fields(copy_input.next_action, default=NextActionType.solve_similar),
        )

    def _partially_correct_feedback(self, copy_input: FeedbackCopyInput) -> FeedbackCopyOutput:
        concept = _concept_label(copy_input.concept)
        body = self._safe_body(
            copy_input.evidence_summary or copy_input.learner_misconception,
            default=f"큰 흐름은 맞게 잡으셨어요. 다만 {concept}의 세부 조건이 조금 비어 있어서, 그 부분만 채우면 훨씬 깔끔해져요.",
        )
        return FeedbackCopyOutput(
            title="방향은 좋아요 👏",
            body=body,
            **self._next_action_fields(copy_input.next_action, default=NextActionType.show_hint),
        )

    def _wrong_feedback(self, copy_input: FeedbackCopyInput) -> FeedbackCopyOutput:
        concept = _concept_label(copy_input.concept)
        coaching = self._mistake_coaching(copy_input.mistake_type)
        title_hint = str(coaching.get("title_hint") or concept)
        title = f"{title_hint}{_subject_particle(title_hint)} 조금 헷갈리셨군요 🤔"
        body = self._safe_body(
            copy_input.evidence_summary or copy_input.learner_misconception,
            default=str(
                coaching.get("body")
                or f"괜찮아요. 이건 처음 보면 충분히 헷갈릴 수 있어요. {concept}을 예시와 함께 다시 보면 다음 문제에서 훨씬 안정적으로 고를 수 있어요."
            ),
        )
        next_action = _next_action_value(coaching.get("next_action"), default=NextActionType.solve_similar)
        secondary_action = _next_action_value(coaching.get("secondary_action"), default=NextActionType.review_concept_card)
        return FeedbackCopyOutput(
            title=title,
            body=body,
            **self._next_action_fields(copy_input.next_action, default=next_action),
            **self._secondary_action_fields(secondary_action),
        )

    def _repeated_wrong_feedback(self, copy_input: FeedbackCopyInput) -> FeedbackCopyOutput:
        concept = _concept_label(copy_input.concept)
        body = self._safe_body(
            copy_input.evidence_summary,
            default=f"{concept}은 문제를 계속 더 풀기보다 예시 하나로 흐름을 먼저 잡는 게 좋아요. 지금은 양보다 기준을 다시 세우는 쪽이 더 효과적이에요.",
        )
        return FeedbackCopyOutput(
            title="괜찮아요 😊 이 부분은 작게 나누면 쉬워져요.",
            body=body,
            **self._next_action_fields(copy_input.next_action, default=NextActionType.see_worked_example),
        )

    def _hint_feedback(self, copy_input: FeedbackCopyInput) -> FeedbackCopyOutput:
        reference = copy_input.source_reference_label or "자료"
        body = self._safe_body(
            copy_input.evidence_summary,
            default=f"{reference}에서 이유를 설명하는 문장을 먼저 찾아보시면 좋아요. 정답을 바로 보지 말고, 어떤 기준으로 나누는지만 먼저 잡아볼까요?",
        )
        return FeedbackCopyOutput(
            title="힌트 하나만 드릴게요 💡",
            body=body,
            **self._next_action_fields(copy_input.next_action, default=NextActionType.retry),
        )

    def _error_feedback(self, copy_input: FeedbackCopyInput) -> FeedbackCopyOutput:
        body = self._safe_body(
            copy_input.evidence_summary,
            default="이번 자료만으로는 바로 좋은 문제를 만들기 어려웠어요. 내용이 조금 더 있으면 단순 개념 확인이 아니라 응용 문제까지 더 정확하게 만들 수 있어요.",
        )
        return FeedbackCopyOutput(
            title="잠시 막힌 부분이 있어요 🧭",
            body=body,
            **self._next_action_fields(copy_input.next_action, default=NextActionType.retry),
            secondary_action_label="자료 더 추가하기",
        )

    def _checked_output(
        self,
        output: FeedbackCopyOutput,
        *,
        situation: FeedbackSituation,
        emoji_policy: str = "contextual",
    ) -> FeedbackCopyOutput:
        cleaned_output = output.model_copy(
            update={
                "title": _polish_text(output.title),
                "body": _polish_text(output.body),
                "next_action_label": _polish_optional_text(output.next_action_label),
                "secondary_action_label": _polish_optional_text(output.secondary_action_label),
            }
        )
        cleaned_output = _apply_emoji_policy(cleaned_output, emoji_policy=emoji_policy)
        result = self.copy_checker.check_output(cleaned_output, situation=situation)
        if result.is_valid:
            return cleaned_output.model_copy(
                update={
                    "warnings": list(dict.fromkeys([*cleaned_output.warnings, *result.warnings]))[:10],
                    "tone_status": "passed",
                }
            )

        fallback = self._fallback_output(situation)
        return fallback.model_copy(
            update={
                "warnings": list(dict.fromkeys([*cleaned_output.warnings, *result.errors, *result.warnings]))[:10],
                "tone_status": "needs_review",
            }
        )

    def _fallback_output(self, situation: FeedbackSituation) -> FeedbackCopyOutput:
        if situation == FeedbackSituation.correct:
            return FeedbackCopyOutput(
                title="좋아요, 잘하셨어요 👍",
                body="조건을 놓치지 않고 잘 고르셨어요. 우리 비슷한 문제로 한 번 더 확인해볼까요?",
                **self._next_action_fields(None, default=NextActionType.solve_similar),
            )
        if situation == FeedbackSituation.partially_correct:
            return FeedbackCopyOutput(
                title="거의 잡으셨어요 👏",
                body="빠진 조건만 하나 더 확인하면 훨씬 깔끔해져요.",
                **self._next_action_fields(None, default=NextActionType.retry),
            )
        if situation == FeedbackSituation.repeated_wrong:
            return FeedbackCopyOutput(
                title="괜찮아요 😊 작게 나누면 쉬워져요.",
                body="먼저 예시 하나로 흐름을 같이 잡아볼까요?",
                **self._next_action_fields(None, default=NextActionType.see_worked_example),
            )
        if situation == FeedbackSituation.error:
            return FeedbackCopyOutput(
                title="잠시 막힌 부분이 있어요 🧭",
                body="자료를 조금 더 추가하면 더 정확한 문제를 만들 수 있어요.",
                next_action_label="자료 더 추가하기",
            )
        return FeedbackCopyOutput(
            title="이 부분이 헷갈리셨군요 🤔",
            body="기준을 먼저 잡고 다시 풀어보면 훨씬 안정적이에요.",
            **self._next_action_fields(None, default=NextActionType.retry),
        )

    def _next_action_fields(
        self,
        action: NextActionType | None,
        *,
        default: NextActionType,
    ) -> dict[str, NextActionType | str]:
        selected_action = action or default
        return {
            "next_action_type": selected_action,
            "next_action_label": NEXT_ACTION_LABELS[selected_action],
        }

    def _secondary_action_fields(self, action: NextActionType) -> dict[str, NextActionType | str]:
        return {
            "secondary_action_type": action,
            "secondary_action_label": NEXT_ACTION_LABELS[action],
        }

    def _apply_confidence_tone(self, output: FeedbackCopyOutput, *, confidence: str) -> FeedbackCopyOutput:
        if confidence != "low":
            return output
        caution = "필기 인식이나 답안 근거가 조금 애매할 수 있어요. 지금 보이는 답안을 기준으로 같이 확인해볼게요."
        if output.body.startswith(caution):
            return output
        return output.model_copy(
            update={
                "body": f"{caution} {output.body}",
                "warnings": list(dict.fromkeys([*output.warnings, "low_confidence_feedback_copy"]))[:10],
            }
        )

    def _mistake_coaching(self, mistake_type: str | None) -> dict[str, object]:
        if not mistake_type:
            return {}
        return MISTAKE_COACHING.get(str(mistake_type), {})

    def _safe_body(self, text: str | None, *, default: str) -> str:
        if not text:
            return default
        return _polish_text(text)

    def _failure_evidence_for_content(self, content: LearningContentBase) -> str:
        if content.content_type == LearningContentType.true_false:
            return "문장의 방향이 살짝 바뀌었는지 먼저 확인해보시면 좋아요. 우리 근거 문장과 나란히 비교해볼까요?"
        if content.content_type == LearningContentType.cloze:
            return "빈칸에는 예시보다 개념 이름이나 조건이 들어가는 경우가 많아요. 문장 역할부터 같이 볼까요?"
        if content.content_type == LearningContentType.ordering:
            return "흐름 문제는 무엇이 먼저 나오고 무엇이 뒤따르는지 표시하면 쉬워져요. 번호를 붙이면서 다시 맞춰볼까요?"
        if content.content_type == LearningContentType.matching:
            return "비슷해 보이는 용어라도 기준이 다를 수 있어요. 기준을 하나씩 나눠서 맞춰볼까요?"
        if content.content_type == LearningContentType.mistake_drill:
            return "방금 헷갈리신 지점을 조건만 바꿔 다시 묻는 문제예요. 이번에는 기준부터 잡고 풀어볼까요?"
        return "문제에서 묻는 기준을 먼저 잡고 다시 보면 좋아요. 우리 한 번 더 천천히 볼까요?"

    def _next_action_for_content(self, content_type: LearningContentType) -> NextActionType:
        if content_type in {LearningContentType.flashcard, LearningContentType.concept_summary_card}:
            return NextActionType.review_concept_card
        if content_type == LearningContentType.worked_example:
            return NextActionType.solve_similar
        return NextActionType.retry


def _concept_label(concept: str | None) -> str:
    value = _first_text([concept] if concept else [])
    return value or "문제의 기준"


def _first_text(values: list[str] | None) -> str | None:
    for value in values or []:
        if value and value.strip():
            return value.strip()
    return None


def _subject_particle(text: str) -> str:
    if not text:
        return "이"
    last = text[-1]
    code = ord(last)
    if 0xAC00 <= code <= 0xD7A3:
        return "이" if (code - 0xAC00) % 28 else "가"
    return "이"


def _next_action_value(value: object, *, default: NextActionType) -> NextActionType:
    if isinstance(value, NextActionType):
        return value
    if isinstance(value, str):
        try:
            return NextActionType(value)
        except ValueError:
            return default
    return default


def _polish_optional_text(text: str | None) -> str | None:
    if text is None:
        return None
    return _polish_text(text)


def _apply_emoji_policy(output: FeedbackCopyOutput, *, emoji_policy: str) -> FeedbackCopyOutput:
    if emoji_policy == "none":
        return output.model_copy(
            update={
                "title": _strip_emoji(output.title),
                "body": _strip_emoji(output.body),
                "next_action_label": _strip_emoji(output.next_action_label) if output.next_action_label else None,
                "secondary_action_label": _strip_emoji(output.secondary_action_label)
                if output.secondary_action_label
                else None,
            }
        )
    if emoji_policy == "rare":
        return output.model_copy(
            update={
                "body": _strip_emoji(output.body),
                "next_action_label": _strip_emoji(output.next_action_label) if output.next_action_label else None,
                "secondary_action_label": _strip_emoji(output.secondary_action_label)
                if output.secondary_action_label
                else None,
            }
        )
    return output


def _strip_emoji(text: str) -> str:
    return re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]+", "", text).replace("  ", " ").strip()


def _polish_text(text: str) -> str:
    polished = re.sub(r"\s+", " ", str(text or "")).strip()
    replacements = {
        "정답입니다": "잘하셨어요",
        "오답입니다": "이 부분이 헷갈리셨군요",
        "해당 개념": "이 개념",
        "이해도가 부족합니다": "이 부분은 한 번 더 보면 훨씬 깔끔해져요",
        "학습을 진행하세요": "우리 한 단계만 더 해볼까요?",
        "분석 결과": "방금 답을 보면",
        "사용자 응답": "이번 답",
        "제공합니다": "같이 볼게요",
        "오류가 발생했습니다": "잠시 막힌 부분이 있어요",
    }
    for old, new in replacements.items():
        polished = polished.replace(old, new)
    return polished
