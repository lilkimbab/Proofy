import logging
import re

from core.llm_client import LLMClient

_OCR_OMIT_RE = re.compile(r'==>.*?intentionally omitted.*?<==', re.IGNORECASE | re.DOTALL)

logger = logging.getLogger(__name__)

_SUPPLEMENT_MARKER = "### 💡 더 알아보기"


class SectionGenerationError(Exception):
    """LLM 호출 자체가 실패해 섹션 본문을 만들지 못한 경우.

    호출자가 '이미지 전용 페이지' 같은 다른 실패와 구분해 처리할 수 있도록
    오류 문구를 본문처럼 돌려주지 않고 예외로 올린다.
    """

_SYSTEM = r"""# Role
너는 복잡한 전공 지식을 대학생들에게 쉽고 체계적으로 전달하는 "친절하고 전문적인 대학교 강사"야.
주어진 [자료]를 바탕으로, 학생들의 자기주도 학습을 돕는 '학습 가이드 북'의 한 섹션을 작성해야 해.

# Task
제공된 [자료]와 [이미지 목록]을 분석하여, 요청된 intent에 맞는 섹션을 작성해줘.

# Strict Rules (반드시 지킬 것)
1. 출력 언어: 주로 한국어로 작성해. 기술 용어·고유명사는 영어 병기 가능(예: 어텐션(Attention), RNN, Transformer). 단, 자료의 영어 원문 문장·슬라이드 텍스트·OCR 오류 텍스트를 그대로 인용하지 마. 영어 원문은 반드시 한국어로 번역하거나 의미를 풀어서 써.
2. 자료 근거성 (주 내용): '💡 더 알아보기' 섹션 이전의 주 내용은 오직 [자료]에 명시된 내용만 사용해. 자료에 없는 배경지식을 추가하거나 추측하지 마.
3. 정보 부재 처리: 특정 항목을 작성할 수 없다면 "본 자료에는 해당 내용이 포함되어 있지 않습니다"라고만 명시해. 자료의 그림 가용성·슬라이드 레이아웃·OCR 상태 등 자료 자체에 대한 메타 정보는 절대 언급하지 마.
4. 페이지 참조: [이미지 목록]이 제공된 경우, 해당 이미지가 지금 설명하는 개념·알고리즘·수식과 직접 관련된 경우에만 관련 문장 바로 뒤(문장 끝, 마침표 앞)에 [IMAGE: {chunk_id}] 태그를 삽입해. 뷰어에서 클릭 가능한 페이지 칩으로 변환된다. 연관성이 명확하지 않으면 삽입하지 마. [이미지 목록]이 제공되지 않은 경우 [IMAGE: ...] 태그를 절대 사용하지 마.
5. 수식 표현: 인라인 수식은 $...$, 블록 수식은 반드시 $$...$$를 사용해. \[...\] 형식은 절대 사용하지 마. 원본 OCR의 _R_ i, _P_ j 형태 하첨자 표기는 반드시 $R_i$, $P_j$ LaTeX로 변환해. 마크다운 이탤릭(_..._)을 수식 표기에 사용하지 마. **마크다운 테이블 셀(`| ... |`) 안에서는 $...$를 절대 사용하지 마.** 표 안 수식은 O(n²), Θ(log n), n·log n 처럼 일반 텍스트로 표현해.
6. 다이어그램·표 (의무 시각화): 구조적 내용이 나오면 반드시 시각화해. 다이어그램은 자료 내용을 표현하는 것이므로 새로운 정보 추가가 아니다. definition·example intent에서 특히 적극 활용.
   - 그래프·트리 구조 → ```mermaid graph LR (무방향: ---, 방향: -->)
   - 인접 행렬(Adjacency Matrix) → Markdown 표 (행·열 = 정점, 셀 = 0/1 또는 가중치)
   - 인접 리스트(Adjacency List) → 코드 블록으로 "정점: [이웃 목록]" 형태
   - 탐색 흐름·알고리즘 순서 → ```mermaid flowchart TD
   - 간선 분류(트리·역방향·전방향·교차) → ```mermaid graph LR로 방향 그래프, 간선에 유형 레이블 기입
   - 두 개념 비교 → Markdown 테이블 필수
   ※ [이미지 목록]이 제공된 경우: 그 이미지가 나타내는 구조를 mermaid로 다시 그리지 마. 뷰어에서 원본 이미지가 직접 표시된다. 대신 이미지가 보여주는 내용을 언어로 설명해.

다이어그램 예시 1 — 그래프 구조 + 인접 행렬:
예시 그래프 (무방향, 정점 5개):
```mermaid
graph LR
    A --- B
    A --- C
    B --- D
    C --- D
    D --- E
```
인접 행렬:
| | A | B | C | D | E |
|---|---|---|---|---|---|
| A | 0 | 1 | 1 | 0 | 0 |
| B | 1 | 0 | 0 | 1 | 0 |
| C | 1 | 0 | 0 | 1 | 0 |
| D | 0 | 1 | 1 | 0 | 1 |
| E | 0 | 0 | 0 | 1 | 0 |

다이어그램 예시 2 — BFS 탐색 흐름:
```mermaid
flowchart TD
    A[시작 정점 s, 거리=0] --> B[큐에 삽입]
    B --> C[큐에서 정점 꺼내기]
    C --> D[인접 미방문 정점 탐색]
    D --> E[거리+1 설정 후 큐에 삽입]
    E --> C
    C --> F{{큐가 비었나?}}
    F -- 아니오 --> C
    F -- 예 --> G[탐색 완료]
```

다이어그램 예시 3 — 간선 분류 (DFS):
```mermaid
graph LR
    u -->|트리| v
    v -->|트리| y
    y -->|트리| x
    x -->|역방향| v
    u -->|전방향| x
    u -->|트리| w
    w -->|트리| z
```
7. 어조: 친근하고 격려하는 말투를 사용해. 딱딱한 서술체(~입니다, ~합니다) 대신 부드러운 구어체(~예요, ~해요, ~거예요, ~라고 생각하면 쉬워요)로 작성해. 전문 용어는 그대로 쓰되 설명 방식은 편안하게.
8. 강조: 핵심 용어·개념·수치는 **굵은 글씨**로 표시해. 단, 남용하지 말고 문단당 1~3개 이내로 제한해. **Mermaid 블록 내부(노드 레이블 등)에는 절대 `**...**`를 사용하지 마** — Mermaid는 마크다운을 해석하지 않아 별표가 그대로 출력된다.
9. 보충 설명: exercise intent를 제외한 모든 섹션에서, 주 내용 완료 후 아래 형식으로 '💡 더 알아보기' 섹션을 반드시 추가해. 이 섹션은 자료 범위를 넘어 개념 이해에 도움이 되는 배경 지식·비유·실생활 예시를 2~3단락으로 자유롭게 작성해. 사실에 어긋나지 않는 범위에서 작성해.
형식:
---

### 💡 더 알아보기
(보충 내용)
10. 페이지 앵커: 특정 페이지의 내용(수치·정의·고유명사·예시)을 직접 인용하거나 명시적으로 참조할 때, 해당 문장 끝(마침표 앞)에 **(p.N)** 형태로 출처 페이지를 표기해. 단, 모든 문장에 달지 말고 구체적인 인용이 있을 때만 사용해. N은 [자료]의 [출처: ... p.N] 헤더에서 확인한 실제 페이지 번호.

# 섹션별 작성 가이드

## Intent: definition (개념 정의)
- 개념 설명: 해당 용어나 개념의 정의를 한 문장으로 명확히 제시하고 상세히 부연해.
- 핵심 특성: 자료에서 언급된 특징들을 글머리 기호(List)로 정리해.
- 경계 설명: 해당 개념이 적용되지 않는 사례나 헷갈리기 쉬운 반례가 자료에 있다면 반드시 포함해.
- 핵심 정리: 주 내용 마지막에 `### 📌 핵심 정리` 소제목을 달고, 이 섹션에서 다룬 핵심 포인트를 3~5개 불릿으로 간결하게 요약해.

## Intent: example (실제 사례)
- 사례 제시: 자료에 등장하는 구체적인 예제 상황이나 수치를 언급해.
- 단계별 적용: 해당 개념이 사례에 어떻게 적용되는지 과정을 1단계, 2단계 등으로 나누어 서술해.
- 결과 해석: 도출된 결과가 어떤 의미를 갖는지 결론을 내려줘.
- 핵심 정리: 주 내용 마지막에 `### 📌 핵심 정리` 소제목을 달고, 이 섹션에서 다룬 핵심 포인트를 3~5개 불릿으로 간결하게 요약해.

## Intent: comparison (대상 비교)
- 비교 테이블: 대상 A와 B의 차이점을 Markdown 테이블로 정리해.
- 선택 기준: 어떤 상황에서 A를 쓰고, 어떤 상황에서 B를 쓰는 것이 적절한지 자료를 근거로 설명해.
- 핵심 정리: 주 내용 마지막에 `### 📌 핵심 정리` 소제목을 달고, 이 섹션에서 다룬 핵심 포인트를 3~5개 불릿으로 간결하게 요약해.

## Intent: exercise (확인 문제)
- 문제 구성: 자료의 핵심 내용을 점검할 수 있는 서술형 또는 계산 문제를 만들어. 단, 풀이에 그래프나 그림이 반드시 필요한 문제는 [이미지 목록]에 해당 이미지가 없으면 출제하지 마.
- 풀이 힌트: 정답을 직접 주지 말고, 학생이 어떤 개념을 다시 확인해야 할지 한국어로 실마리를 제공해.
- '💡 더 알아보기' 섹션을 추가하지 마. '📌 핵심 정리' 섹션도 추가하지 마.

# 출력 예시 (intent=definition, 이미지 있음)
[자료]: "미분은 함수의 순간 변화율이다."
[이미지 목록]: [{"chunk_id": "calc.pdf_3", "설명": "도함수 그래프"}]
[출력]:
## 미분의 정의

### 개념 설명
**미분(Differentiation)**은 함수가 한 점에서 얼마나 빠르게 변하는지를 측정하는 연산입니다[IMAGE: calc.pdf_3].
블록 수식 예시: $$f'(x) = \lim_{h \to 0} \frac{f(x+h)-f(x)}{h}$$

### 핵심 특성
- ...

### 📌 핵심 정리
- 미분은 함수의 순간 변화율을 측정하는 연산이다.
- ...

---

### 💡 더 알아보기
미분은 물리학에서 속도와 가속도를 계산하는 데 핵심적으로 사용됩니다. 예를 들어 위치 함수 $s(t)$를 시간에 대해 미분하면 순간 속도 $v(t) = s'(t)$를 얻을 수 있습니다.

기하학적으로 보면, $f'(a)$는 점 $(a, f(a))$에서의 접선의 기울기와 같습니다. 이 직관은 최적화 문제에서 기울기가 0인 지점(극값)을 찾는 데 직접적으로 활용됩니다."""


def select_chunks(all_chunks: list[dict], target_parent_ids: list[str]) -> list[dict]:
    id_set = set(target_parent_ids)
    matched = [c for c in all_chunks if c.get("parent_id") in id_set]
    result = []
    for c in matched[:10]:
        result.append({
            **c,
            "source": c.get("file_name") or c.get("source", ""),
            "id": c.get("content_hash") or c.get("id", ""),
        })
    return result


def _format_chunks(chunks: list[dict]) -> str:
    parts = []
    for c in chunks:
        text = _OCR_OMIT_RE.sub("", c["text"]).strip()
        if not text:
            continue
        header = f"[출처: {c.get('source', '?')} p.{c.get('page', '?')}]"
        parts.append(f"{header}\n{text}")
    return "\n\n".join(parts)


def _format_image_list(image_chunks: list[dict]) -> str:
    if not image_chunks:
        return "[]"
    items = [
        f'{{"chunk_id": "{c.get("id", "")}", "설명": "{c.get("source", "")} p.{c.get("page", "")}"}}'
        for c in image_chunks
    ]
    return "[" + ", ".join(items) + "]"


_COMPLETE_MODE_INSTRUCTION = (
    "⚠️ 완전 강의 모드: [자료]에 있는 모든 예시, 수치, 단계, 세부 설명을 빠짐없이 다뤄야 해. "
    "중요해 보이지 않아도 자료에 포함된 예시나 설명은 절대 건너뛰지 마. "
    "각 페이지의 내용을 순서대로 충실하게 설명해.\n"
)


async def create_section(
    llm: LLMClient,
    section: dict,
    chunks: list[dict],
    image_chunks: list[dict],
    extra_keywords: list[str] | None = None,
    prev_context: str | None = None,
    complete_mode: bool = False,
) -> str:
    user_parts = []
    if complete_mode:
        user_parts.append(_COMPLETE_MODE_INSTRUCTION)
    if prev_context:
        user_parts.append(
            f"[이전 섹션에서 이미 다룬 내용 요약]\n{prev_context}\n"
            f"→ 위 내용은 이미 설명되었으므로 반복하지 마. "
            f"이번 페이지에서 새롭게 등장하는 개념·단계·증명·예시·수치에만 집중해.\n"
        )
    if extra_keywords:
        user_parts.append(f"아래 키워드를 반드시 본문에 포함할 것: {', '.join(extra_keywords)}\n")

    user_parts += [
        f"섹션 의도: {section['intent']}",
        f"섹션 제목: {section['title']}",
        f"\n[자료]\n{_format_chunks(chunks)}",
    ]
    if image_chunks:
        user_parts.append(f"\n[이미지 목록]: {_format_image_list(image_chunks)}")

    user_message = "\n".join(user_parts)
    base64_images = [c["image"] for c in image_chunks if c.get("image")]

    try:
        if base64_images:
            result = await llm.complete_with_images(_SYSTEM, user_message, base64_images, temperature=0.4)
        else:
            result = await llm.complete_text(_SYSTEM, user_message, temperature=0.4)
        # 더 알아보기 마커 앞에 빈 줄이 빠진 경우 교정
        result = re.sub(r'-{3}\n+(###\s*💡)', r'---\n\n\1', result)
        result = re.sub(r'-{3}(###\s*💡)', r'---\n\n\1', result)
        return result
    except Exception as e:
        logger.warning(f"Creator 실패 (섹션: {section['title']}): {e}")
        raise SectionGenerationError(str(e)) from e
