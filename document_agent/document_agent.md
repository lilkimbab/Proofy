# Document Agent 설계 및 구현 문서

## 1. 개요

업로드된 문서를 입력받아 **[Executive Summary → 개념 흐름 중심 설명 → 확인 문제]** 구조의 학습 자료를 자동 생성한다.

모든 parent를 빠짐없이 강의 형식으로 설명하는 **complete 모드** 단일 동작. 섹션 생성은 `SECTION_CONCURRENCY` (기본 3) 세마포어로 제한한 병렬 처리.

| 기능 | 웹사이트 LLM | document_agent |
|------|------------|----------------|
| 원본 근거 | 프롬프트 지시만 | Grounding Check + 자동 교정(Corrector) |
| 전체 요약 | 없음 | **Executive Summary**: 핵심 주제·학습 목표·전체 흐름 자동 생성 |
| 섹션 구성 | 페이지 순서 | **개념 단위** 그루핑 + 섹션 간 인과관계 중심 |
| 페이지 앵커 | 없음 | `(p.N)` 인라인 태그 → 클릭 가능한 PDF 페이지 칩 |
| 보충 설명 | 없음 | **💡 더 알아보기**: 자료 범위 외 배경 지식·비유·예시 자동 생성 |
| 능동 학습 | 선형 읽기 | Flashcard: 질문 → 힌트 → 정답 3단계 active recall |
| 키워드 검증 | 없음 | Validator: 한국어 음절 블록 토크나이징, 미달 시 재생성 |
| 수식/다이어그램 | 없음 | KaTeX (`$...$`) + Mermaid.js 자동 렌더링 |
| 원본 비교 | 없음 | PDF와 AI 설명을 나란히 표시하는 비교 뷰어 |

---

## 2. 파이프라인

### 업로드 기반 (`POST /upload`)

```
POST /upload {file, title}
  → /add 호출 → parents + job_id 수신
  → 202 {task_id, doc_id, job_id}

백그라운드:
  SUMMARIZING  (15%)  각 parent → LLM 3문장 요약 (병렬, 한국어)
  SUMMARIZING  (35%)  Executive Summary 생성:
                        key_topics (3~5개), learning_objectives (2~3개),
                        conceptual_flow (개념 단위 전체 흐름)
  PLANNING     (45%)  plan_sections_complete() LLM 클러스터링:
                        유사·중복 parents → 하나의 섹션으로 통합
                        독립적 개념 → 별도 섹션으로 분리
                        섹션당 최대 5개 parent (내용 많으면 여러 섹션으로 분리)
                        섹션 수 상한 없음 (내용에 따라 동적 결정)
                      _ensure_full_coverage():
                        LLM이 누락한 parent를 감지 → 5개씩 나눠 새 섹션 추가
  GENERATING   (50%→90%)  섹션 병렬 처리 (세마포어 SECTION_CONCURRENCY=3):
                          _process_one_section() 독립 실행:
                            Creator (주 내용 + (p.N) 앵커 + 💡 더 알아보기)
                            → Validator → [재생성]
                            → Grounding(주 내용만) + Flashcard (병렬)
                            → [이슈 있을 때] Corrector → 재Grounding → Flashcard 재생성
                          전체 완료 후 image_map 확정 → [IMAGE:...] + (p.N) → page chip 치환
  ASSEMBLING   (90%)  섹션 결합 + 출처 목록
  DONE
```

---

## 3. 디렉토리 구조

```
document_agent/
├── core/
│   ├── llm_client.py       LLM 호출 추상화 (Ollama / OpenAI, Vision API 포함)
│   ├── rag_client.py       rag_agent REST 클라이언트 + 응답 정규화
│   ├── summarizer.py       parent 배치 요약 + Executive Summary 생성 + Planner 입력 포맷
│   ├── planner.py          목차 구성 LLM (문서 기반 max 10, 개념 단위 그루핑)
│   ├── creator.py          섹션 본문 + 💡 더 알아보기 생성 LLM (10개 규칙)
│   ├── validator.py        키워드 커버리지 검사
│   ├── grounding.py        LLM 기반 환각 탐지 (주 내용만, exercise 섹션 스킵)
│   ├── corrector.py        LLM 기반 환각 교정 (주 내용만, 보충 설명 보존)
│   ├── flashcard_gen.py    active recall Q&A 3단계 생성 (question + hint + answer)
│   ├── assembler.py        섹션 결합 + [IMAGE:] + (p.N) → page chip 치환 + 출처 목록
│   └── manager.py          파이프라인 오케스트레이션 + 태스크 관리
├── api/
│   ├── main.py             FastAPI 앱 초기화
│   ├── routes.py           HTTP 엔드포인트 + 비교 뷰어 HTML
│   └── schemas.py          Pydantic 요청/응답 모델
└── server.py               uvicorn 진입점 (포트 8001)
```

---

## 4. 핵심 모듈

### `core/rag_client.py`

rag_agent REST 클라이언트. **응답 정규화**로 rag_agent 버전 간 호환을 담당한다.

| 함수 | 엔드포인트 |
|------|-----------|
| `add(file_path, title) → dict` | `POST /add` |
| `search(query, title, top_k, user_id) → list[dict]` | `POST /search` |
| `get_titles() → list[str]` | `GET /titles` |
| `send_feedback(...)` | `POST /feedback` |

**정규화 처리:**

| 변환 | 이유 |
|------|------|
| `add()`: parent `source` → `file_name` | 업데이트된 rag_agent의 ParseParent 필드명이 `source` |
| `search()`: `parent_text` → `text` fallback | 업데이트된 rag_agent는 SearchResult.text를 직렬화에서 제외하고 parent_text로 대체 |

---

### `core/summarizer.py`

| 함수 | 역할 |
|------|------|
| `summarize_parents(llm, parents)` | 각 parent를 한국어 3문장으로 병렬 요약 (온도 0.1) |
| `generate_executive_summary(llm, summaries)` | 전체 문서에서 key_topics·learning_objectives·conceptual_flow 생성 (입력 최대 6,000자) |
| `build_planner_input(summaries)` | Planner에게 전달할 요약 텍스트 포맷 구성 (max 20,000자) |

**Executive Summary 출력 구조:**
```json
{
  "key_topics": ["핵심 주제 3~5개 (명사구)"],
  "learning_objectives": ["~할 수 있다 형태 2~3개"],
  "conceptual_flow": "개념 단위 논리 흐름 2~4문장"
}
```

`conceptual_flow`는 Planner에게 전달되어 섹션 구성 품질을 향상시킨다.

---

### `core/planner.py`

| 함수 | 용도 | 출력 |
|------|------|------|
| `plan_sections_from_doc(llm, planner_input, parents, conceptual_flow="")` | study 모드 | `{title, intent, target_parent_ids, focus}` 최대 **10**개 |
| `plan_sections_complete(llm, planner_input, parents, conceptual_flow="")` | complete 모드 | `{title, intent, target_parent_ids, focus}` 개수 제한 없음 |

**study 모드 섹션 구성 원칙:**
- 페이지 번호 순서가 아닌 **개념 단위**로 묶음
- `focus` 필드에 이전 섹션과의 인과관계·논리적 연결 포함
- `conceptual_flow` 컨텍스트를 참고해 전체 흐름과 일관된 목차 생성

**complete 모드 섹션 구성 원칙:**
- **모든 parent_id를 반드시 하나의 섹션에 포함** (누락 불가)
- 유사·중복 parents는 하나의 섹션으로 통합해 중복 제거
- **섹션당 최대 5개 parent** 제한 → 내용 많으면 여러 섹션으로 분리
- 섹션 수 상한 없음 (내용에 따라 동적 결정)
- LLM 누락분은 `_ensure_full_coverage()`가 5개씩 나눠 새 섹션으로 보정

`intent`: `definition` | `example` | `comparison` | `exercise` (하나만 선택)

---

### `core/creator.py`

섹션 본문과 보충 설명을 하나의 LLM 호출로 생성한다.

```python
await create_section(llm, section, chunks, image_chunks,
                     extra_keywords=None, prev_context=None,
                     complete_mode=False) → str
```

`complete_mode=True`이면 "자료의 모든 예시·수치·단계를 빠짐없이 설명하라"는 지시가 프롬프트 앞에 추가된다.

**출력 구조:**
```
## 섹션 제목

### 개념 설명 / 사례 제시 / 비교 테이블 / 문제 구성
(자료 기반 주 내용 — Rule 2 적용)

### 📌 핵심 정리
(이 섹션의 핵심 포인트 3~5개 불릿 — definition·example·comparison에만, exercise 제외)

---

### 💡 더 알아보기
(자유 보충 설명 — Rule 2 미적용, exercise 섹션은 생략)
```

**10개 규칙 요약:**

| # | 규칙 |
|---|------|
| 1 | 주로 한국어. 기술 용어 영어 병기 가능. 영어 원문·슬라이드 텍스트·OCR 오류 직접 인용 금지 |
| 2 | 주 내용은 [자료]에 명시된 내용만 사용 (💡 더 알아보기 제외) |
| 3 | 내용 없으면 "본 자료에는 해당 내용이 포함되어 있지 않습니다"만 명시. 자료 메타 정보(그림 가용성 등) 언급 금지 |
| 4 | 이미지 직접 관련 시 문장 끝 인라인에 `[IMAGE: chunk_id]` 삽입 → page chip 변환 |
| 5 | 인라인 `$...$`, 블록 `$$...$$`. `\[...\]` 절대 금지. OCR `_R_ i` 형태 하첨자는 반드시 `$R_i$` LaTeX로 변환 |
| 6 | 구조적 내용은 mermaid 블록으로 시각화 (그래프·BFS·DFS 간선 분류 등 타입별 예시 제공). 이미지 제공 시 mermaid 중복 작성 금지 |
| 7 | 친근하고 격려하는 구어체 어조 (~예요, ~해요, ~거예요). 딱딱한 서술체(~입니다) 사용 금지 |
| 8 | 핵심 용어·개념·수치 **굵은 글씨** (문단당 1~3개) |
| 9 | exercise 제외 모든 섹션 끝에 `---\n\n### 💡 더 알아보기` 자유 보충 설명 추가 |
| 10 | 특정 페이지 내용 직접 인용 시 문장 끝(마침표 앞)에 **(p.N)** 페이지 앵커 표기 |

**OCR 아티팩트 처리:** `_OCR_OMIT_RE`로 `==> picture [...] intentionally omitted <==` 패턴을 포맷 단계에서 제거.

온도: `0.4` / `_SUPPLEMENT_MARKER = "### 💡 더 알아보기"`

---

### `core/grounding.py` / `core/corrector.py`

`_SUPPLEMENT_MARKER` 기준으로 주 내용과 보충 설명을 분리하여 처리한다.

```
section_text
  ├── main_text   → Grounding 검증 대상 / Corrector 교정 대상
  └── supplement  → 검증·교정 제외, Corrector 후 원본 그대로 재결합
```

**Grounding 포함 기준 (모두 해당해야 함)**:
- 원본 어디에도 없고 + 원본 내용과 모순되는 사실적 주장
- 또는: 원본에 없는 구체적 고유명사·논문명·외부 알고리즘명을 단정적으로 서술

**Grounding 제외**:
- 원본 내용을 한국어로 바꿔 쓰거나 풀어 설명한 것
- 원본의 영어 텍스트를 번역·해설한 것
- 원본 내용에서 논리적으로 따라오는 결론·특성
- 개념·알고리즘을 교육적으로 서술·예시·단계별 설명한 것
- 해당 분야 CS 표준 관례(u/v/w 변수명, 상태 색 표현 등)
- 원본과 모순되지 않는 구체적 예시·수치 설명
- 조금이라도 판단이 애매한 것

**exercise 섹션은 grounding 스킵** (`"exercise" in intent` 체크)

| 설정 | 값 |
|------|----|
| 온도 | 0.1 |
| 소스 청크 | 최대 8개, 8,000자 |
| 섹션 주 내용 | 최대 4,000자 |
| grounding 경고 뷰어 표시 | 이슈 2건 이상일 때만 표시 |

**자동 교정 루프** (`manager._correct_if_needed`):
```
grounding 이슈 발견
  → Corrector LLM (주 내용만 교정, supplement 보존)
  → 재Grounding 검증
  → Flashcard 재생성 (교정된 텍스트 기준)
  → 잔여 이슈 경고 표시
```

---

### `core/flashcard_gen.py`

섹션 내용을 바탕으로 3단계 active recall 카드를 생성한다.

```python
await generate_flashcards(llm, section_text, intent) → list[dict]
# exercise 섹션("exercise" in intent)은 [] 반환
```

**출력 구조:**
```json
{"flashcards": [{"question": "...", "answer_hint": "...", "answer": "..."}]}
```

| 필드 | 내용 |
|------|------|
| `question` | 핵심 개념을 묻는 질문 |
| `answer_hint` | 키워드·정의 첫 단어·단계 힌트 등 불완전한 실마리 |
| `answer` | 섹션 내용 기반 완전한 정답 문장 |

수식은 `$...$` / `$$...$$` LaTeX 형식 사용. 섹션 텍스트는 최대 3,000자로 자른 뒤 입력.

---

### `core/assembler.py`

```python
def replace_image_tags(text, image_map) → str
    # [IMAGE: chunk_id] → <span class="page-chip" onclick="jumpToPage(N)">[p.N]</span>

def replace_page_anchors(text) → str
    # (p.N) → <span class="page-chip" onclick="jumpToPage(N)">(p.N)</span>

def assemble(sections_md, image_map, sources) → str
    # 섹션 결합 + replace_image_tags + replace_page_anchors + 출처 목록
```

`replace_image_tags()`는 `manager.py`에서 섹션별 `content` 저장 시에도 별도 호출한다.

---

### `core/llm_client.py`

| 메서드 | 역할 |
|--------|------|
| `complete_text(system, user, temperature)` | 텍스트 생성 |
| `complete_json(system, user, temperature)` | JSON 생성 + 파싱 |
| `complete_with_images(system, user, images, temperature)` | Vision API (OpenAI 한정, Ollama는 텍스트 폴백) |

OpenAI Vision: base64 인코딩된 이미지를 `image_url` 타입 메시지로 전달. Creator가 이미지 청크 있을 때 자동으로 이 경로 사용.

---

### `core/manager.py`

| 메서드 | 역할 |
|--------|------|
| `submit_upload(file_path, title)` | 파이프라인 비동기 시작 |
| `_ensure_full_coverage(sections, parents)` | LLM 누락 parent를 5개씩 나눠 새 섹션으로 추가 |
| `_process_one_section(section, parent_map, img_dir)` | 단일 섹션 생성 (Creator→Validator→Grounding+Flashcard→Corrector) |
| `_enrich_section(text, chunks, intent)` | grounding + flashcard 병렬 실행 (exercise 스킵) |
| `_correct_if_needed(text, issues, chunks)` | grounding 이슈 있을 때만 교정 → flashcard 재생성 |
| `_run_upload_pipeline(task_id, doc_id, parents, title)` | 파이프라인 (SUMMARIZING→PLANNING→병렬 GENERATING→ASSEMBLING) |

**이미지 처리:** 섹션당 page 중복을 제거한 뒤 첫 번째 이미지 청크만 사용(`[:1]`). 청크에 `image` 필드가 있으면 `{MATERIALS_DIR}/{doc_id}/images/{chunk_id}.png`로 저장하고 `image_map[cid]["has_image"] = True` 설정.

**Validator 임계값:**
| coverage 범위 | 처리 |
|---|---|
| `< 0.2` | Creator 재호출 1회 (missing_keywords 전달) → 재시도 후도 `< 0.2`이면 경고 |
| `< 0.4` (첫 시도) | 재생성 없이 경고만 추가 |
| `≥ 0.4` | 통과 |

---

## 5. API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| POST | `/upload` | 업로드 기반 자료 생성 (202). Form: `file`, `title` |
| GET | `/tasks/{task_id}` | 진행 상태 |
| GET | `/study/{doc_id}` | 생성 자료 JSON |
| GET | `/view/{doc_id}` | 비교 학습 뷰어 HTML |
| GET | `/view/{doc_id}/source` | 원본 파일 서빙 |
| GET | `/view/{doc_id}/image/{chunk_id}` | 저장된 이미지 PNG 서빙 |
| POST | `/feedback` | 피드백 → rag_agent |

---

## 6. 비교 뷰어 렌더링 스택

### 구성 요소

| 용도 | 라이브러리 |
|------|-----------|
| 마크다운 | marked.js |
| 수식 | KaTeX (`$...$`, `$$...$$`) |
| 다이어그램 | Mermaid.js ESM |
| PDF 렌더링 | PDF.js |
| 페이지 이동 | `<span class="page-chip" onclick="jumpToPage(N)">` |

### 뷰어 레이아웃

```
┌────────────────────────────────────────────────────┐
│ header: 제목                                        │
│ flow bar: 섹션 순서 칩                              │
├──────────────────────┬─────────────────────────────┤
│  PDF.js 패널         │  섹션 패널                  │
│  (원본 PDF 렌더링)   │  ┌─ Executive Summary 카드  │
│                      │  │  핵심 주제 / 학습 목표   │
│  ◀ [페이지] ▶       │  │  전체 흐름               │
│                      │  └──────────────────────────│
│                      │  ┌─ 섹션 카드 (반복)        │
│                      │  │  제목 + intent 배지      │
│                      │  │  학습 포커스 (인과관계)  │
│                      │  │  페이지 칩               │
│                      │  │  📎 참고자료 (hover→미리보기, click→전체) │
│                      │  │  AI 설명 (마크다운)      │
│                      │  │  🃏 플래시카드           │
│                      │  └──────────────────────────│
└──────────────────────┴─────────────────────────────┘
```

### Executive Summary 카드

- 어두운 그라디언트 배경의 최상단 카드
- **핵심 주제**: 태그 형태 칩
- **학습 목표**: `✓` 체크리스트
- **전체 흐름**: 개념 단위 인과관계 서술

### 💡 더 알아보기 (collapsible)

- `<details class="supplement">` 요소로 구현 — 기본 접힘(closed) 상태
- 클릭하면 펼쳐지며 보충 설명이 표시됨

### 참고자료 칩

- 이미지가 있는 청크는 항상 표시 대신 `📎 참고자료` 영역의 칩으로 표시
- **호버**: 칩 아래에 최대 260px 썸네일 미리보기 플로팅
- **클릭**: 전체 크기 이미지 카드 내 펼침/접힘 토글

### 플래시카드 3단계

클릭할 때마다 상태 순환: `질문만 → 힌트 → 정답 → 초기화`

| 상태 | 표시 내용 |
|------|-----------|
| 초기 | Q. 질문 / "클릭하여 힌트 보기" |
| hint | 💡 힌트: answer_hint |
| answer | ✅ 정답: answer |

---

## 7. 데이터 모델 (`material.json`)

```json
{
  "doc_id": "...",
  "query": "title과 동일한 값 (업로드 시 title 파라미터)",
  "title": "...",
  "mode": "study | page | complete",
  "document": "전체 마크다운 문자열",
  "exec_summary": {
    "key_topics": ["주제1", "주제2"],
    "learning_objectives": ["목표1", "목표2"],
    "conceptual_flow": "개념 흐름 서술"
  },
  "learning_flow": [{"step": 1, "title": "...", "intent": "...", "focus": "..."}],
  "sections": [
    {
      "title": "...",
      "intent": "definition | example | comparison | exercise",
      "content": "마크다운 (page-chip HTML 포함)",
      "focus": "이전 섹션과의 인과관계 포함",
      "source_chunks": [{"chunk_id": "...", "text": "...", "file": "...", "page": 0}],
      "grounding_issues": [],
      "flashcards": [{"question": "...", "answer_hint": "...", "answer": "..."}]
    }
  ],
  "sources": [{"file": "...", "page": 0, "chunk_id": "..."}],
  "image_map": {"chunk_id": {"source": "...", "page": 0, "has_image": true}},
  "warnings": [],
  "generated_at": "ISO8601"
}
```

---

## 8. LLM 온도 설정

| 단계 | 온도 |
|------|------|
| Summarizer / Grounding / Corrector | 0.1 |
| Executive Summary | 0.2 |
| Planner / Flashcard | 0.3 |
| Creator | 0.4 |

---

## 9. 환경 변수

```bash
RAG_AGENT_URL=http://localhost:8000
RAG_TIMEOUT=120

AI_PROVIDER=openai           # "ollama" | "openai"
OPENAI_API_KEY=<your-key>
OPENAI_CHAT_MODEL=gpt-4.1-mini
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_CHAT_MODEL=gemma3:4b

MATERIALS_DIR=./generated_materials
SUMMARIZER_CONCURRENCY=5
SECTION_CONCURRENCY=3
PLANNER_MAX_INPUT_CHARS=20000
API_HOST=0.0.0.0
API_PORT=8001
```

---

## 10. 실행 방법

```bash
cd document_agent && python server.py
# Swagger: http://localhost:8001/docs
```

**업로드**
```bash
curl -X POST http://localhost:8001/upload \
  -F "file=@lecture.pdf" -F "title=운영체제"
```

**진행 상태 조회**
```bash
curl http://localhost:8001/tasks/{task_id}
```

**뷰어**
```
http://localhost:8001/view/{doc_id}
```

---

## 11. 알려진 한계

| 한계 | 확장 방안 |
|------|-----------|
| 태스크 인메모리 저장 (재시작 시 소실) | SQLite / Redis |
| Planner가 parent를 누락하면 `_ensure_full_coverage`가 "추가 내용 N" 제목으로 보정 (제목 품질 낮음) | 누락 parent도 LLM에 재요청해 제목·intent 결정 |
| Planner input이 20,000자 초과 시 잘려 일부 parent 누락 가능 | `PLANNER_MAX_INPUT_CHARS` 증가 또는 2-pass planner |
| 다중 문서 비교 미지원 | 다중 업로드 + cross-doc 섹션 생성 |
| Ollama Vision 미지원 (이미지 청크 있어도 텍스트 폴백) | Ollama 멀티모달 모델 연동 |
