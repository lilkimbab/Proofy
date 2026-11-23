import logging

from core.llm_client import LLMClient
from core.creator import _SUPPLEMENT_MARKER

logger = logging.getLogger(__name__)

_SYSTEM = """너는 학습 자료 교정 전문가야.

AI가 생성한 [학습 설명]에서 원본 자료에 없는 주장이 발견되었다.
아래 [미확인 주장 목록]에 해당하는 내용을 [원본 자료]를 근거로 수정하거나 삭제해라.

규칙 (반드시 지킬 것):
1. [미확인 주장 목록]에 해당하는 문장·구절만 수정/삭제해라. 나머지는 한 글자도 바꾸지 마라.
2. 삭제 시: 해당 문장을 완전히 제거하고 앞뒤 문단이 자연스럽게 이어지도록 해라.
3. 수정 시: [원본 자료]에 있는 내용으로만 대체해라.
4. 마크다운 구조(제목, 목록, 수식, 코드 블록, 이미지 태그)는 그대로 유지해라.
5. 수정 후 텍스트만 출력해라. 설명·사과·메모를 덧붙이지 마라."""


async def correct_section(
    llm: LLMClient,
    section_text: str,
    grounding_issues: list[str],
    source_chunks: list[dict],
) -> str:
    # Separate main content from supplement — only correct the main part
    parts = section_text.split(_SUPPLEMENT_MARKER, 1)
    main_text = parts[0]
    supplement = (_SUPPLEMENT_MARKER + parts[1]) if len(parts) > 1 else ""

    source_text = "\n---\n".join(c.get("text", "") for c in source_chunks[:8])
    if len(source_text) > 8000:
        source_text = source_text[:8000]
    if len(main_text) > 4000:
        main_text = main_text[:4000]

    issues_text = "\n".join(f"- {i}" for i in grounding_issues)
    user_prompt = (
        f"[미확인 주장 목록]\n{issues_text}\n\n"
        f"[원본 자료]\n{source_text}\n\n"
        f"[학습 설명]\n{main_text}"
    )
    try:
        corrected_main = await llm.complete_text(_SYSTEM, user_prompt, temperature=0.1)
        return corrected_main + supplement
    except Exception as e:
        logger.warning(f"Corrector 실패: {e}")
        return section_text
