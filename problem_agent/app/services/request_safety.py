from __future__ import annotations


UNSAFE_USER_REQUIREMENT_PATTERNS = (
    "ignore previous",
    "ignore all previous",
    "system prompt",
    "developer message",
    "jailbreak",
    "prompt injection",
    "이전 지시",
    "지시를 무시",
    "시스템 프롬프트",
    "개발자 메시지",
    "관리자 명령",
    "탈옥",
    "프롬프트 인젝션",
)


def contains_unsafe_instruction_text(text: str | None) -> bool:
    normalized = (text or "").lower()
    if not normalized:
        return False
    return any(pattern in normalized for pattern in UNSAFE_USER_REQUIREMENT_PATTERNS)


def validate_safe_user_requirements(user_requirements: str | None, *, error_message: str) -> None:
    if contains_unsafe_instruction_text(user_requirements):
        raise ValueError(error_message)
