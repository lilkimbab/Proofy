import logging

from core.llm_client import LLMClient

logger = logging.getLogger(__name__)

_SYSTEM_DOC = """너는 교육과정 설계 전문가야. 아래 [전체 흐름]과 [문서 구조]를 보고 학습 자료 목차를 구성해.

규칙:
- 페이지 번호 순서가 아닌 **개념의 단위**로 섹션을 묶어라. 여러 페이지에 걸쳐 하나의 개념을 다루면 하나의 섹션으로 통합하고, 한 페이지에 여러 독립 개념이 있으면 섹션을 나눠라.
- 각 섹션의 focus에는 이전 섹션과의 인과관계·논리적 연결을 반드시 포함해. (예: "앞에서 정의한 X를 전제로 Y가 왜 필요한지 설명")
- [개념 설명 → 비유/예시 → 확인 문제] 흐름을 포함할 것
- 최대 10개 섹션
- target_parent_ids는 반드시 [문서 구조]에 나온 parent_id 값만 사용.
  (parent_ids=A,B,C 형태면 A, B, C 각각을 리스트에 넣어라)
- 아래 JSON 형식으로만 응답해:

{
  "sections": [
    {
      "title": "...",
      "intent": "definition, example, comparison, exercise 중 하나만 선택",
      "target_parent_ids": ["parent_id_1", "parent_id_2"],
      "focus": "이 섹션에서 원본 자료와 비교하며 확인해야 할 핵심 포인트 (1문장)"
    }
  ]
}"""

_SYSTEM_COMPLETE = """너는 강의 자료 설계 전문가야. 아래 [전체 흐름]과 [문서 구조]를 보고 모든 내용을 빠짐없이 다루는 강의 목차를 구성해.

규칙:
- **[문서 구조]에 나온 모든 parent_id를 반드시 하나의 섹션에 포함해야 한다. parent_id를 하나라도 누락하면 안 된다.**
- 내용이 유사하거나 중복되는 parents는 하나의 섹션으로 통합해 중복을 제거해라.
- 완전히 독립적인 개념은 별도 섹션으로 분리해라.
- **하나의 섹션에 포함되는 parent 수는 최대 5개로 제한해라. 내용이 많으면 여러 섹션으로 분리해.**
- 섹션 수는 내용에 따라 동적으로 결정해라 (최소 1개, 상한 없음).
- 각 섹션의 focus에는 이전 섹션과의 연결 또는 이 섹션에서 다루는 핵심 내용을 포함해라.
- target_parent_ids는 반드시 [문서 구조]에 나온 parent_id 값만 사용.
  (parent_ids=A,B,C 형태면 A, B, C 각각을 리스트에 넣어라)
- 아래 JSON 형식으로만 응답해:

{
  "sections": [
    {
      "title": "...",
      "intent": "definition, example, comparison, exercise 중 하나만 선택",
      "target_parent_ids": ["parent_id_1", "parent_id_2"],
      "focus": "이 섹션에서 다루는 핵심 포인트 (1문장)"
    }
  ]
}"""

_DEFAULT_SECTIONS = [
    {"title": "개념 설명", "intent": "definition", "focus": "원본 자료의 핵심 정의와 AI 설명을 비교하며 개념 확인"},
    {"title": "예시 및 비유", "intent": "example", "focus": "원본 예시와 AI가 재구성한 설명의 차이 확인"},
    {"title": "확인 문제", "intent": "exercise", "focus": "원본 자료에서 다룬 개념을 직접 적용해 보기"},
]


async def plan_sections_from_doc(
    llm: LLMClient, planner_input: str, parents: list[dict], conceptual_flow: str = ""
) -> list[dict]:
    flow_ctx = f"[전체 흐름]\n{conceptual_flow}\n\n" if conceptual_flow else ""
    user_prompt = f"{flow_ctx}문서 구조와 내용 요약을 보고 학습 자료 목차를 구성해.\n[문서 구조]\n{planner_input}"

    try:
        result = await llm.complete_json(_SYSTEM_DOC, user_prompt, temperature=0.3)
        sections = result.get("sections", [])
        valid = [
            s for s in sections
            if s.get("target_parent_ids") and s.get("title") and s.get("intent")
        ]
        if not valid:
            raise ValueError("유효한 섹션 없음")
        return valid[:10]
    except Exception as e:
        logger.warning(f"Planner(문서 레벨) LLM 실패, 기본 섹션 사용: {e}")
        return _fallback_sections(parents)


async def plan_sections_complete(
    llm: LLMClient, planner_input: str, parents: list[dict], conceptual_flow: str = ""
) -> list[dict]:
    """complete 모드: 모든 parent를 커버하도록 LLM이 클러스터링."""
    flow_ctx = f"[전체 흐름]\n{conceptual_flow}\n\n" if conceptual_flow else ""
    user_prompt = (
        f"{flow_ctx}아래 문서의 모든 parent_id를 빠짐없이 포함하는 강의 목차를 구성해. "
        f"유사한 내용은 통합하고, 독립적인 개념은 분리해.\n[문서 구조]\n{planner_input}"
    )

    try:
        result = await llm.complete_json(_SYSTEM_COMPLETE, user_prompt, temperature=0.3)
        sections = result.get("sections", [])
        valid = [
            s for s in sections
            if s.get("target_parent_ids") and s.get("title") and s.get("intent")
        ]
        if not valid:
            raise ValueError("유효한 섹션 없음")
        return valid
    except Exception as e:
        logger.warning(f"Planner(complete 모드) LLM 실패, 순차 그루핑 사용: {e}")
        return _fallback_sections_complete(parents)


def _fallback_sections(parents: list[dict]) -> list[dict]:
    intents = ["definition", "example", "exercise"]
    titles = ["개념 설명", "예시 및 비유", "확인 문제"]
    step = max(1, len(parents) // 3)
    sections = []
    for i, (intent, title) in enumerate(zip(intents, titles)):
        chunk = parents[i * step : (i + 1) * step] or parents[:1]
        sections.append({
            "title": title,
            "intent": intent,
            "target_parent_ids": [p["parent_id"] for p in chunk],
        })
    return sections


def _fallback_sections_complete(parents: list[dict]) -> list[dict]:
    """폴백: 3개씩 순차 그루핑으로 전체 커버."""
    group_size = 3
    sections = []
    for i in range(0, len(parents), group_size):
        group = parents[i : i + group_size]
        page = group[0].get("page_start", i)
        sections.append({
            "title": f"p.{page + 1} 내용",
            "intent": "definition",
            "target_parent_ids": [p["parent_id"] for p in group],
            "focus": "해당 페이지의 내용을 설명합니다",
        })
    return sections
