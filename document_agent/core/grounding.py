import logging

from core.llm_client import LLMClient
from core.creator import _SUPPLEMENT_MARKER

logger = logging.getLogger(__name__)

_SYSTEM = """너는 학습 자료의 사실적 오류를 검출하는 전문가야.

[AI 설명]에서 [원본 자료]와 **명백히 모순되거나 원본에 완전히 없는** 내용만 추출해라.
기준은 "틀렸는가"이지 "자료에 똑같이 표현되었는가"가 아니다.

절대 포함하지 말 것:
- 원본 내용을 한국어로 바꿔 쓰거나 풀어 설명한 것
- 원본의 영어 텍스트를 번역·해설한 것
- 원본 내용에서 논리적으로 따라오는 결론·특성
- 개념·알고리즘·자료구조를 교육적으로 서술·예시·단계별 설명한 것
- 해당 분야(그래프 이론, 알고리즘)의 표준 관례 (변수명 u/v/w, 상태 색 표현, 의사코드 기호 등)
- 원본과 모순되지 않는 구체적 예시나 수치 설명
- 조금이라도 판단이 애매한 것

포함 기준 (모두 해당해야 함):
- 원본 어디에도 없고 + 원본 내용과 모순되는 사실적 주장
- 또는: 원본에 없는 구체적 고유명사·논문명·외부 알고리즘명을 단정적으로 서술한 경우

아래 JSON 형식으로만 응답:
{"unsupported": ["명백히 잘못된 주장만"]}
없으면: {"unsupported": []}"""


async def check_grounding(
    llm: LLMClient, section_text: str, source_chunks: list[dict]
) -> list[str]:
    # Only check the main section, not the AI supplement
    main_text = section_text.split(_SUPPLEMENT_MARKER)[0]

    source_text = "\n---\n".join(c.get("text", "") for c in source_chunks[:8])
    if len(source_text) > 8000:
        source_text = source_text[:8000]
    if len(main_text) > 4000:
        main_text = main_text[:4000]

    user_prompt = f"[AI 설명]\n{main_text}\n\n[원본 자료]\n{source_text}"
    try:
        result = await llm.complete_json(_SYSTEM, user_prompt, temperature=0.1)
        issues = result.get("unsupported", [])
        return [i for i in issues if isinstance(i, str) and len(i) > 5]
    except Exception as e:
        logger.warning(f"Grounding check 실패: {e}")
        return []
