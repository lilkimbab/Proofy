from __future__ import annotations

import re

from app.schemas.common import GuardResult


MAX_QUESTION_CHARS = 1200
MAX_SELECTED_TEXT_CHARS = 1800

PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"developer\s+message", re.IGNORECASE),
    re.compile(r"act\s+as\s+.*jailbreak", re.IGNORECASE),
    re.compile(r"프롬프트\s*무시"),
    re.compile(r"시스템\s*메시지"),
    re.compile(r"이전\s*지시.*무시"),
    re.compile(r"규칙.*무시"),
]

UNSAFE_PATTERNS = [
    re.compile(r"폭탄|테러|자살|자해|해킹|피싱|악성코드|바이러스"),
    re.compile(r"개인정보|주민등록번호|비밀번호|토큰|api\s*key", re.IGNORECASE),
]


def guard_question(*, question: str, document: dict | None = None, selected_text: str = "") -> GuardResult:
    normalized_question = normalize_space(question)
    normalized_selection = normalize_space(selected_text)

    if not normalized_question:
        return block("empty_question", "질문을 입력해주세요.")
    if len(normalized_question) > MAX_QUESTION_CHARS:
        return block("question_too_long", "질문이 너무 깁니다. 핵심 질문만 짧게 다시 작성해주세요.")
    if len(normalized_selection) > MAX_SELECTED_TEXT_CHARS:
        return block("selection_too_long", "선택한 문장이 너무 깁니다. 질문할 핵심 부분만 다시 선택해주세요.")
    if document is not None and not document_has_content(document):
        return block("missing_document", "답변할 학습 자료를 찾지 못했습니다. 먼저 자료를 업로드해주세요.")
    if matches_any(normalized_question, PROMPT_INJECTION_PATTERNS):
        return block("prompt_injection", "자료 기반 학습 질문만 처리할 수 있습니다. 질문을 학습 내용 중심으로 다시 작성해주세요.")
    if matches_any(normalized_question, UNSAFE_PATTERNS):
        return block("unsafe_request", "안전하지 않거나 학습 범위를 벗어난 요청은 처리할 수 없습니다.")
    return GuardResult(allowed=True, reason="allowed")


def enforce_tutor_output(answer: str | None, fallback_message: str | None = None) -> str:
    cleaned = normalize_answer(answer)
    return cleaned or fallback_message or "자료에서 답변에 필요한 내용을 충분히 찾지 못했습니다. 질문을 조금 더 구체적으로 작성해보세요."


def normalize_answer(answer: str | None) -> str:
    return re.sub(r"\n{4,}", "\n\n\n", str(answer or "")).strip()


def normalize_space(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def matches_any(value: str, patterns: list[re.Pattern]) -> bool:
    return any(pattern.search(value) for pattern in patterns)


def document_has_content(document: dict) -> bool:
    sections = document.get("sections") or []
    return bool(sections or document.get("chunks") or document.get("content") or document.get("text") or document.get("summary"))


def block(reason: str, message: str) -> GuardResult:
    return GuardResult(allowed=False, reason=reason, message=message)

