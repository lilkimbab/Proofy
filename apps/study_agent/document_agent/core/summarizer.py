import asyncio
import logging
import os

logger = logging.getLogger(__name__)

_CONCURRENCY = int(os.getenv("SUMMARIZER_CONCURRENCY", "5"))
_MAX_INPUT_CHARS = int(os.getenv("PLANNER_MAX_INPUT_CHARS", "20000"))

_SYSTEM = "아래 텍스트를 한국어로 3문장 이내로 요약해. 핵심 개념과 다루는 내용만 서술해."

_EXEC_SYSTEM = """너는 학습 자료 설계 전문가야. 아래 [문서 요약]을 분석해 JSON으로 응답해.

아래 JSON 형식으로만 응답:
{
  "key_topics": ["핵심 주제 (명사구) 3~5개"],
  "learning_objectives": ["이 자료를 통해 학습자가 달성할 수 있는 목표 2~3개 (~할 수 있다 형태)"],
  "conceptual_flow": "문서의 논리적 흐름을 2~4문장으로 설명. 페이지 번호 대신 개념 단위로 각 파트 간 인과관계 중심으로 서술."
}"""


async def _summarize_one(llm, parent: dict) -> dict:
    try:
        text = await llm.complete_text(_SYSTEM, parent["text"], temperature=0.1)
        return {
            "parent_id": parent["parent_id"],
            "heading_path": parent.get("heading_path"),
            "summary": text.strip(),
            "source_type": parent.get("source_type"),
        }
    except Exception as e:
        logger.warning(f"요약 실패 parent_id={parent['parent_id']}: {e}")
        return {
            "parent_id": parent["parent_id"],
            "heading_path": parent.get("heading_path"),
            "summary": parent["text"][:200],
            "source_type": parent.get("source_type"),
        }


async def summarize_parents(llm, parents: list[dict]) -> list[dict]:
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _bounded(p: dict) -> dict:
        async with sem:
            return await _summarize_one(llm, p)

    return list(await asyncio.gather(*[_bounded(p) for p in parents]))


async def generate_executive_summary(llm, summaries: list[dict]) -> dict:
    text = build_planner_input(summaries)[:6000]
    try:
        result = await llm.complete_json(_EXEC_SYSTEM, f"[문서 요약]\n{text}", temperature=0.2)
        return {
            "key_topics": result.get("key_topics", []),
            "learning_objectives": result.get("learning_objectives", []),
            "conceptual_flow": result.get("conceptual_flow", ""),
        }
    except Exception as e:
        logger.warning(f"Executive summary 생성 실패: {e}")
        return {"key_topics": [], "learning_objectives": [], "conceptual_flow": ""}


def build_planner_input(summaries: list[dict]) -> str:
    def _fmt(s: dict) -> str:
        heading = " > ".join(s["heading_path"]) if s.get("heading_path") else "일반"
        stype = s.get("source_type") or "general"
        return f"- [{heading}] {s['summary']} ({stype}) [parent_id={s['parent_id']}]"

    result = "\n".join(_fmt(s) for s in summaries)
    if len(result) <= _MAX_INPUT_CHARS:
        return result

    # Too long: group by top-level heading
    groups: dict[str, list] = {}
    for s in summaries:
        top = (s.get("heading_path") or ["기타"])[0]
        groups.setdefault(top, []).append(s)

    lines = []
    for heading, items in groups.items():
        combined = " ".join(i["summary"] for i in items)[:400]
        ids = ",".join(i["parent_id"] for i in items)
        lines.append(f"- [{heading}] {combined} [parent_ids={ids}]")

    return "\n".join(lines)[:_MAX_INPUT_CHARS]
