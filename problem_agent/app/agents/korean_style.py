from __future__ import annotations

import re


HUMAN_KOREAN_STYLE_GUIDE = """
문체 기준:
- 실제 선생님이 학생 답안을 보고 짧게 짚어주는 말투로 쓴다.
- 학생을 낮춰 보거나 과하게 칭찬하지 않는다. 담백하고 구체적으로 말한다.
- "자료에서", "해당 부분", "핵심 개념", "확인하는 개념", "가장 적절한 것은" 같은 티 나는 템플릿 표현을 쓰지 않는다.
- "기반으로", "수행한다", "제공한다", "관련된다"처럼 번역투가 강한 표현은 쉬운 말로 바꾼다.
- 문제는 시험지처럼 자연스럽게 쓴다. 필요하면 "왜", "어떻게", "무엇이 달라지는지"로 묻는다.
- 피드백은 "틀렸어"보다 "여기서 놓친 지점은 ..."처럼 원인을 짚는다.
- 해설은 필요한 만큼 자세히 써도 된다. 대신 한 문장에 여러 생각을 우겨 넣지 말고, 이유와 예시를 자연스럽게 나눈다.
- 자세히 설명할 때도 어려운 단어와 번역투를 피하고, 학생이 바로 다음 행동을 알 수 있게 쓴다.
- 내부 용어(context, chunk, source, LLM, 생성 후보, 품질 검증, 루브릭, 청사진, 메타데이터)는 사용자에게 보이는 문장에 쓰지 않는다.
""".strip()


PROBLEM_KOREAN_STYLE_GUIDE = """
문제 문항 문체 기준:
- 실제 시험지나 연습 문제처럼 담백하고 명확하게 쓴다.
- 문제 문장에는 이모티콘, 감탄, 과한 친근 표현을 쓰지 않는다.
- "우리", "해볼까요", "잘하셨어요", "헷갈리셨군요" 같은 코칭 말투는 문제 문항에 쓰지 않는다.
- 객관식 문항은 무엇을 고르면 되는지 한 번에 알 수 있게 쓴다.
- 주관식 문항은 답안에서 요구하는 사고 작업을 분명히 밝힌다.
- 공식, 방정식, 변수 관계는 가능하면 inline LaTeX 형식으로 쓴다. 예: `$F = ma$`, `$a = F / m$`.
- 긴 수식은 display LaTeX 형식으로 쓴다. 예: `$$F = ma$$`.
- 해설은 친절하게 쓸 수 있지만, 정답 공개 전 문제 본문은 시험 문항처럼 유지한다.
- 내부 용어(context, chunk, source, LLM, 생성 후보, 품질 검증, 루브릭, 청사진, 메타데이터)는 사용자에게 보이는 문장에 쓰지 않는다.
""".strip()


AI_LIKE_PHRASES = (
    "자료에서 어떤 관계",
    "자료의 해당 부분",
    "해당 부분에서는",
    "핵심 개념",
    "확인하는 개념",
    "관계와 연결된다",
    "연결해서 이해해야 한다",
    "기반으로",
    "중심으로",
    "관련된다",
    "수행한다",
    "제공한다",
    "도출한다",
    "활용한다",
    "가장 적절한 것은",
    "바탕으로 설명",
    "자연스러운 한국어",
    "학습 콘텐츠",
    "생성 후보",
    "품질 검증",
    "루브릭",
    "청사진",
    "메타데이터",
)


INTERNAL_TERMS = (
    "context",
    "chunk",
    "source_chunk",
    "source chunk",
    "llm",
    "schema",
    "payload",
)


def korean_tone_issues(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    if not normalized:
        return []

    issues: list[str] = []
    for phrase in AI_LIKE_PHRASES:
        if phrase.lower() in normalized:
            issues.append(f"AI-like template phrase: {phrase}")

    for term in INTERNAL_TERMS:
        if term in normalized:
            issues.append(f"internal term leaked: {term}")

    if normalized.count("자료") >= 4:
        issues.append("too many repeated references to 자료")

    if _same_sentence_ending_repeated(normalized):
        issues.append("same sentence ending repeated too often")

    return list(dict.fromkeys(issues))


def _same_sentence_ending_repeated(text: str) -> bool:
    sentences = [sentence.strip() for sentence in re.split(r"[.!?\n]+", text) if sentence.strip()]
    if len(sentences) < 3:
        return False
    endings = [sentence[-5:] for sentence in sentences if len(sentence) >= 5]
    return any(endings.count(ending) >= 3 for ending in set(endings))
