# document_agent 설계도

## 개요

파일이 업로드되면 rag_agent의 raw 청크를 받아
[개념 설명 → 비유/예시 → 확인 문제] 구조의 학습 자료를 자동 생성하는 파이프라인.

사용자가 특정 질문을 하기 전에 문서 전체를 커버하는 학습 자료를 먼저 만드는 것이 목표.
임베딩(벡터 DB 저장)은 rag_agent가 백그라운드에서 병렬로 처리한다.

---

## 1. v1과의 차이

| 항목 | v1 (쿼리 기반) | v2 (업로드 기반) |
|------|----------------|-----------------|
| 트리거 | 사용자 질문 | 파일 업로드 |
| 청크 소스 | rag_agent /search (벡터) | rag_agent /parse (raw) |
| Planner 입력 | 질문 + 광역 검색 결과 | 문서 구조 + parent 요약 |
| 청크 선택 | 벡터 유사도 | parent_id 필터링 |
| 이미지 | base64 인라인 | 미지원 (임베딩 완료 후 /search로 조회) |
| 대용량 처리 | top_k 제한 | parent 요약으로 컨텍스트 압축 |

---

## 2. 전체 흐름

```
Client
  │  POST /upload  { file, title }
  ▼
document_agent (Port 8001)
  │
  ├─[Stage 1] PARSING
  │   rag_agent POST /parse (multipart: file, title)
  │   → chunks: list[ParseChunk]       ← 개별 청크 (~512자)
  │   → parents: list[ParseParent]     ← heading 경계 단위 묶음 (300~3000자)
  │   → job_id                         ← 백그라운드 임베딩 진행 ID
  │
  ├─[Stage 2] SUMMARIZING
  │   각 parent.text → LLM 2문장 요약 (최대 5개 병렬)
  │   → [(parent_id, heading_path, summary, source_type)]
  │
  │   대용량 처리 기준 (Planner 입력 상한 20,000자):
  │   ├─ parents ≤ 150개: parent별 요약 그대로 사용
  │   └─ parents > 150개: 최상위 heading(#)으로 그룹화 후 그룹 단위 요약
  │
  ├─[Stage 3] PLANNING
  │   입력: parent 요약 + heading 구조
  │   Planner LLM → [{title, intent, target_parent_ids}, ...]  최대 6개 섹션
  │
  ├─[Stage 4] GENERATING  (섹션별 순차)
  │   target_parent_ids로 chunks 필터링 → 관련 청크 추출 (최대 10개)
  │   Creator LLM → 섹션 본문 Markdown
  │   Validator → 키워드 커버리지 체크 (기존 로직 유지)
  │
  └─[Stage 5] ASSEMBLING
      섹션 결합 + 학습 목표 헤더 + 출처 목록
      → study_materials/{doc_id}/material.json 저장

Client
  │  GET /tasks/{task_id}   → 진행 상태 폴링
  └─ GET /study/{doc_id}    → 최종 학습 문서 조회
```

---

## 3. rag_agent /parse 응답 구조

```python
# ParseChunk — 개별 청크
{
    "text": str,                     # 청크 텍스트 (~512자)
    "chunk_index": int,              # 문서 전체 순서
    "page": int,                     # 페이지 번호
    "file_name": str,
    "content_hash": str,
    "heading_path": list[str]|None,  # ["제목1", "제목2", ...]
    "source_type": str|None,         # "slide"|"textbook"|"code"|"general"
    "parent_id": str|None
}

# ParseParent — 섹션 단위 논리적 묶음 (Summarizer가 이 단위로 요약)
{
    "parent_id": str,
    "text": str,                     # 300~3000자
    "file_name": str,
    "page_start": int,
    "page_end": int,
    "heading_path": list[str]|None,
    "source_type": str|None
}
```

parents를 요약 단위로 쓰는 이유: rag_agent가 heading 경계 기준으로 이미 논리적으로
묶어놨기 때문에 별도 배칭 없이 각 parent = 1 요약 단위로 처리 가능.

---

## 4. 디렉토리 구조

```
document_agent/
├── core/
│   ├── llm_client.py      변경 없음
│   ├── rag_client.py      parse() 메서드 추가 / search(), send_feedback() 유지
│   ├── summarizer.py      NEW — parent 배치 요약
│   ├── planner.py         수정 — user_query 없는 문서 레벨 계획 지원
│   ├── creator.py         수정 — parent_id 기반 청크 선택
│   ├── validator.py       변경 없음
│   ├── assembler.py       변경 없음
│   └── manager.py         수정 — 새 파이프라인 스테이지 추가
│
├── api/
│   ├── main.py            변경 없음
│   ├── routes.py          POST /upload 추가
│   └── schemas.py         UploadResponse 추가
│
└── server.py              변경 없음
```

---

## 5. 모듈별 설명

### 5-1. core/rag_client.py

기존 메서드 유지 + parse 추가.

```python
async def parse(file_path: str, title: str) -> dict:
    # multipart/form-data로 rag_agent POST /parse 호출
    # returns: {"chunks": [...], "parents": [...], "job_id": "..."}

async def search(query, title, top_k, user_id=None) -> list[dict]  # 유지
async def send_feedback(user_id, title, chunk_id, kind) -> None    # 유지
async def get_titles() -> list[str]                                # 유지
```

---

### 5-2. core/summarizer.py (신규)

역할: 각 parent 텍스트를 LLM으로 2문장 요약.

```python
async def summarize_parents(llm, parents: list[dict]) -> list[dict]:
    # asyncio.gather로 최대 SUMMARIZER_CONCURRENCY개 병렬 처리
    # returns: [{"parent_id", "heading_path", "summary", "source_type"}, ...]

def build_planner_input(summaries: list[dict], max_chars: int = 20000) -> str:
    # 요약 목록 → Planner 프롬프트용 텍스트 포맷
    # 상한 초과 시: 최상위 heading 그룹별 재묶음
```

온도: `0.1` (사실 기반 요약)

프롬프트:
```
[System] 아래 텍스트를 2문장으로 요약해. 핵심 개념과 다루는 내용만 서술해.

[User] {parent.text}
```

---

### 5-3. core/planner.py

변경: `user_query` 파라미터 optional로 변경. 없으면 문서 레벨 계획 프롬프트 사용.

입력 (쿼리 없을 때):
```
문서 구조와 내용 요약을 보고 학습 자료 목차를 구성해.
[문서 구조]
- [미분의 정의] 미분은 함수의 순간 변화율이다... (textbook)
- [미분의 예제] f(x)=x² 풀이 예시... (code)
...
```

출력 JSON:
```json
{
  "sections": [
    {
      "title": "미분의 정의",
      "intent": "definition",
      "target_parent_ids": ["abc123", "def456"]
    },
    {
      "title": "미분 계산 예시",
      "intent": "example",
      "target_parent_ids": ["ghi789"]
    }
  ]
}
```

폴백: 실패 시 parents를 순서대로 2개씩 묶어 기본 섹션 생성.
온도: `0.3`

---

### 5-4. core/creator.py

변경: rag 검색 결과 대신 parent_id 필터링으로 청크 선택.

```python
def select_chunks(all_chunks: list, target_parent_ids: list[str]) -> list[dict]:
    matched = [c for c in all_chunks if c.get("parent_id") in target_parent_ids]
    return matched[:10]  # 최대 10개
```

이미지: /parse가 이미지를 반환하지 않으므로 image_list는 항상 `[]`.
나머지 프롬프트 로직(intent별 스타일, 그라운딩 강제)은 기존과 동일.

---

### 5-5. core/manager.py

태스크 상태 추가:
```
PENDING → PARSING → SUMMARIZING → PLANNING → GENERATING → ASSEMBLING → DONE
                                                                       ↘ FAILED
```

신규 메서드:
```python
def submit_upload(file_path: str, title: str) -> tuple[str, str]:
    # (task_id, doc_id) 반환, 백그라운드 파이프라인 시작
```

기존 `submit_task` (쿼리 기반) 유지.

---

## 6. API 엔드포인트

### 신규: POST /upload

```
Request: multipart/form-data
  - file: UploadFile (pdf, docx, txt)
  - title: str

Response 202:
{
  "task_id": "abc123",
  "doc_id": "def456",
  "job_id": "xyz789"    ← rag_agent 임베딩 백그라운드 작업 ID
}
```

### 기존 유지

| Method | Path | 설명 |
|--------|------|------|
| POST | `/study` | 쿼리 기반 자료 생성 (기존, 독립 공존) |
| GET | `/tasks/{task_id}` | 진행 상태 확인 |
| GET | `/study/{doc_id}` | 생성된 학습 문서 조회 |
| POST | `/feedback` | 피드백 → rag_agent 전달 |

---

## 7. 대용량 문서 처리 기준

| 문서 크기 | parents 수 | 요약 총량 | Planner 처리 방식 |
|---------|-----------|---------|----------------|
| ~50페이지 | ~25개 | ~2,500자 | parent별 요약 직접 사용 |
| ~200페이지 | ~100개 | ~10,000자 | parent별 요약 직접 사용 |
| ~500페이지 | ~250개 | ~25,000자 | 최상위 heading 그룹별 재묶음 |

상한: Planner 입력 최대 20,000자 (환경변수 `PLANNER_MAX_INPUT_CHARS`로 조정).

---

## 8. 이미지 처리

`/parse`는 이미지 데이터를 반환하지 않는다.
이미지가 포함된 PDF는 백그라운드 임베딩 완료 후 `/search`로 조회 가능.
업로드 자동 생성 문서는 텍스트 전용. `[IMAGE]` 태그 미사용.

---

## 9. 환경 변수

```bash
# rag_agent 연결
RAG_AGENT_URL=http://localhost:8000
RAG_TIMEOUT=30

# LLM
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_CHAT_MODEL=gemma3:4b
OPENAI_API_KEY=
OPENAI_CHAT_MODEL=gpt-4.1-mini
LLM_MAX_RETRIES=3
LLM_RETRY_BACKOFF_BASE=2

# 자료 저장
MATERIALS_DIR=./study_materials

# 파이프라인 튜닝
SUMMARIZER_CONCURRENCY=5      # 병렬 요약 LLM 호출 수
PLANNER_MAX_INPUT_CHARS=20000 # Planner 입력 상한

# 서버
API_HOST=0.0.0.0
API_PORT=8001
```

---

## 10. 검증 방법

```bash
# 1. rag_agent 실행 (포트 8000)
cd rag_agent && .venv/bin/python server.py

# 2. document_agent 실행 (포트 8001)
cd document_agent && ../rag_agent/.venv/bin/python server.py

# 3. 파일 업로드
curl -X POST http://localhost:8001/upload \
  -F "file=@differentiation1.pdf" \
  -F "title=미분"
# → {"task_id": "abc123", "doc_id": "def456", "job_id": "xyz789"}

# 4. 진행 상태 폴링
curl http://localhost:8001/tasks/abc123
# → {"status": "SUMMARIZING", "progress": 0.25, "message": "parent 요약 중"}

# 5. 완료 후 문서 조회
curl http://localhost:8001/study/def456
```

확인 항목:
- 응답 Markdown에 `### 개념 설명`, `### 비유 / 예시`, `### 확인 문제` 포함
- sources 필드에 file_name + page_start 포함
- 100페이지+ 문서에서 SUMMARIZING 단계 정상 진행
- 임베딩 백그라운드 job_id 응답에 포함
