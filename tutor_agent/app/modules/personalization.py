from __future__ import annotations

from collections import Counter
from typing import Any


LEVELS = {"beginner", "intermediate", "advanced"}
LEVEL_LABELS = {
    "beginner": "초보자",
    "intermediate": "중급자",
    "advanced": "고급자",
}


def build_user_model(
    *,
    requested_level: str | None = None,
    attempts: list[dict[str, Any]] | None = None,
    questions: list[dict[str, Any]] | None = None,
    preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    explicit_level = normalize_level(requested_level)
    recent_attempts = list(attempts or [])[:20]
    recent_questions = list(questions or [])[:20]
    total_attempts = len(recent_attempts)
    correct_count = sum(1 for attempt in recent_attempts if bool(attempt.get("is_correct") or attempt.get("isCorrect")))
    accuracy = correct_count / total_attempts if total_attempts else None
    level = explicit_level or infer_level(accuracy=accuracy, question_count=len(recent_questions))
    return {
        "level": level,
        "requested_level": explicit_level,
        "accuracy": accuracy,
        "weak_concepts": collect_weak_concepts(recent_attempts),
        "preference": infer_preference(level=explicit_level, accuracy=accuracy),
        "preferences": preferences or {},
    }


def build_personalization_instructions(user_model: dict[str, Any] | None = None) -> str:
    model = user_model or {}
    level = normalize_level(model.get("level")) or "intermediate"
    weak_concepts = ", ".join((model.get("weak_concepts") or [])[:3])
    instructions = [
        f"학생 수준: {LEVEL_LABELS[level]}.",
        "답변은 한국어로 작성한다.",
        "자료에 근거한 내용과 추론을 구분한다.",
        "불필요하게 길게 쓰지 말고 질문에 직접 답한다.",
    ]
    if level == "beginner":
        instructions.extend([
            "쉬운 단어를 우선 사용한다.",
            "정의보다 직관을 먼저 설명하고 짧은 예시를 포함한다.",
        ])
    elif level == "advanced":
        instructions.extend([
            "핵심 정의, 조건, 예외를 명확히 구분한다.",
            "가능하면 수식이나 논리 구조를 함께 제시한다.",
        ])
    else:
        instructions.extend([
            "개념 간 관계를 중심으로 설명한다.",
            "대표 예시와 주의할 오개념을 하나씩 포함한다.",
        ])
    if weak_concepts:
        instructions.append(f"최근 취약 개념이 있다면 자연스럽게 보강한다: {weak_concepts}.")
    return "\n".join(instructions)


def apply_local_personalization(answer: str, user_model: dict[str, Any] | None = None) -> str:
    level = normalize_level((user_model or {}).get("level")) or "intermediate"
    clean_answer = str(answer or "").strip()
    if not clean_answer:
        return clean_answer
    if level == "beginner":
        return "\n".join([
            "쉽게 말하면,",
            clean_answer,
            "",
            "먼저 핵심 문장을 하나 고르고 예시와 연결해보면 좋아요.",
        ])
    if level == "advanced":
        return "\n".join([
            clean_answer,
            "",
            "엄밀하게는 자료에 제시된 조건 안에서만 이 설명을 적용해야 합니다.",
        ])
    return clean_answer


def normalize_level(level: str | None) -> str | None:
    normalized = str(level or "").lower().strip()
    return normalized if normalized in LEVELS else None


def infer_level(*, accuracy: float | None, question_count: int) -> str:
    if accuracy is None:
        return "intermediate" if question_count >= 5 else "beginner"
    if accuracy < 0.45:
        return "beginner"
    if accuracy > 0.8:
        return "advanced"
    return "intermediate"


def infer_preference(*, level: str | None, accuracy: float | None) -> str:
    normalized_level = normalize_level(level)
    if normalized_level == "advanced" or (accuracy is not None and accuracy > 0.8):
        return "formal"
    if normalized_level == "beginner" or (accuracy is not None and accuracy < 0.45):
        return "intuitive"
    return "balanced"


def collect_weak_concepts(attempts: list[dict[str, Any]]) -> list[str]:
    counter: Counter[str] = Counter()
    for attempt in attempts:
        for concept in attempt.get("weak_concepts") or attempt.get("weakConcepts") or []:
            key = str(concept or "").strip()
            if key:
                counter[key] += 1
    return [concept for concept, _count in counter.most_common(5)]

