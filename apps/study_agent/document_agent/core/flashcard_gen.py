import logging

from core.llm_client import LLMClient

logger = logging.getLogger(__name__)

_SYSTEM = """너는 학습 전문가야. 아래 [섹션 내용]을 읽고 학습자가 능동적 회상(active recall)을 연습할 수 있는 플래시카드를 만들어.

규칙:
- 각 카드: 질문 + 힌트 + 정답 세 가지를 모두 작성
- 힌트(answer_hint)는 다음 중 하나 형태로 작성:
  · 핵심 키워드 제공: "핵심어: 큐, FIFO, 레벨 순서"
  · 정의 첫 단어: "정의는 '간선 (u,v)는 ...' 으로 시작해"
  · 반례 또는 대조: "역방향 간선이 없는 DAG와 비교해봐"
  · 단계 힌트: "①방문 여부 체크 → ②큐에 삽입 → ③거리+1 갱신"
- 정답(answer)은 섹션 내용을 근거로 완전한 문장으로 작성
- "참고하세요", "부분을 보세요" 같은 위치 안내 표현 금지
- 섹션 내용에 근거한 내용만 사용
- 수식은 반드시 $...$ (인라인) 또는 $$...$$ (블록) LaTeX 형식으로 작성. 마크다운 이탤릭(_..._)을 수식 표기에 사용하지 마.
- 3~5개 생성
- 아래 JSON 형식으로만 응답

[출력 예시]
{"flashcards": [
  {
    "question": "BFS에서 같은 레벨의 정점들이 처리 순서를 보장받는 이유는?",
    "answer_hint": "단계 힌트: ①FIFO 특성 ②선입선출 자료구조",
    "answer": "BFS는 큐(Queue)를 사용하기 때문이에요. 먼저 발견된 정점이 먼저 큐에서 나와 처리되므로, 같은 거리의 정점들은 발견된 순서대로 방문이 보장돼요."
  },
  {
    "question": "DFS 탐색 중 역방향 간선(back edge)이 발견됐을 때 그래프가 가지는 성질은?",
    "answer_hint": "반례를 떠올려봐: 역방향 간선이 없는 DAG vs 있는 경우",
    "answer": "그래프에 사이클이 존재해요. 역방향 간선은 현재 방문 중인 조상 정점으로 향하는 간선으로, 이는 순환 경로가 있음을 의미해요."
  },
  {
    "question": "Prim 알고리즘과 Kruskal 알고리즘이 동일한 MST 비용을 보장할 때, 밀집 그래프에서 Prim이 유리한 이유는?",
    "answer_hint": "핵심어: 간선 수 E, 정점 수 V, 인접 행렬 O(V²)",
    "answer": "간선 수가 많은 밀집 그래프(E ≈ V²)에서는 Prim을 인접 행렬로 구현하면 O(V²)로 동작해요. Kruskal은 간선 정렬에 O(E log E)가 필요하므로, 간선이 매우 많을수록 Prim이 더 효율적이에요."
  }
]}"""


async def generate_flashcards(
    llm: LLMClient, section_text: str, intent: str
) -> list[dict]:
    # exercise 섹션은 이미 문제 형식이므로 스킵
    if "exercise" in intent:
        return []

    if len(section_text) > 3000:
        section_text = section_text[:3000]

    user_prompt = f"[섹션 내용]\n{section_text}"
    try:
        result = await llm.complete_json(_SYSTEM, user_prompt, temperature=0.3)
        cards = result.get("flashcards", [])
        return [
            c for c in cards[:5]
            if isinstance(c.get("question"), str) and isinstance(c.get("answer_hint"), str)
               and isinstance(c.get("answer"), str)
        ]
    except Exception as e:
        logger.warning(f"Flashcard 생성 실패: {e}")
        return []
