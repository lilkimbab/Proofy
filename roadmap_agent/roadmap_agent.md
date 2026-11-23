# Roadmap Agent

개인화 학습 로드맵을 생성·관리하는 FastAPI 서비스 (port 8002).  
**document_agent가 생성한 `material.json`을 주 데이터 소스로 사용한다.** Supabase가 없어도 동작한다.

| 에이전트 | 포트 | 역할 |
|---|---|---|
| rag_agent | 8000 | 문서 임베딩·검색 |
| document_agent | 8001 | 학습 자료 생성 |
| **roadmap_agent** | **8002** | **학습 계획·복습 스케줄·진도 관리** |

---

## 데이터 흐름

```
document_agent/generated_materials/{doc_id}/material.json
        │
        ├── title, exec_summary (key_topics, learning_objectives, conceptual_flow)
        ├── learning_flow[]     → 섹션 학습 순서
        └── sections[]
            ├── title           → SM-2 복습 단위
            ├── intent          → definition / example / comparison / exercise
            ├── focus           → 학습 포커스 설명
            └── flashcards[]    → concepts_to_study (오늘 학습 핵심 개념)
                ├── question    → 플래시카드 질문 (SM-2 복습 단위)
                ├── answer_hint → 단계적 힌트
                └── answer      → 정답
```

Supabase (`quiz_attempts`, `questions`)가 연결되어 있으면 약점 개념과 혼란 신호를 추가로 반영한다.

---

## 디렉토리 구조

```
roadmap_agent/
├── core/
│   ├── data_collector.py   material.json 파싱 + Supabase 선택적 조회
│   ├── analyzer.py         진도·약점·학습속도 분석 + SM-2 초기 레코드
│   ├── planner.py          일별 계획 생성 + LLM 마일스톤·전략
│   ├── scheduler.py        SM-2 알고리즘
│   └── llm_client.py       LLM 호출 (Ollama / OpenAI)
├── api/
│   ├── main.py
│   ├── routes.py
│   └── schemas.py
└── server.py               uvicorn 진입점
```

---

## 핵심 모듈

### `data_collector.py`

`material.json`에서 로드맵 생성에 필요한 모든 데이터를 추출한다.

- **document**: `title` + `exec_summary.learning_objectives[0]`을 goal로 사용 (Supabase 없을 때)
- **sections**: `intent`, `focus`, `flashcards` 포함 — 플래너가 바로 사용
- **exec_summary**: `key_topics`, `learning_objectives`, `conceptual_flow` → LLM 프롬프트에 전달
- **concept_cards**: 섹션별 flashcard를 `answer_hint`/`answer` 포함해 추출 (향후 힌트 시스템 활용)

### `analyzer.py`

수집된 데이터를 분석해 `AnalysisResult`를 반환한다.

- **SM-2 개념 단위**: 섹션 제목 (짧고 명확 — 복습 단위로 적합)
- **약점 개념**: Supabase `quiz_attempts` 오답 기반. 없으면 빈 상태로 시작
- **학습 속도**: rag_agent query 타임스탬프 → 주당 세션 수 추정

### `planner.py`

일별 학습 계획을 생성한다.

**`concepts_to_study` 추출 순서:**
1. 오늘 섹션의 플래시카드 질문 (최대 3개) — 가장 구체적인 학습 단위
2. 섹션 `focus` 필드 (40자 미만일 때만)

**일별 계획 항목:**
- `intents`: 오늘 섹션의 intent 목록 (`definition`, `exercise` 등)
- `flashcard_count`: 오늘 섹션의 플래시카드 수 → 학습 후 자기 테스트 기준
- `concepts_to_review`: SM-2 날짜별 계산 (모든 날 동일 목록 버그 수정)

**LLM 입력**: `exec_summary`의 `learning_objectives`, `conceptual_flow`, `key_topics` 포함 → 문서 맥락에 맞는 마일스톤·전략 생성

### `scheduler.py`

SM-2 간격 반복 알고리즘.

```
오답 (quality 0-2): interval = 1일, ease_factor -= 0.2
정답 (quality 3-5): interval *= ease_factor, ease_factor 증가
약점 개념:          quality=0으로 처리 → 매일 복습
```

---

## API

| Method | Path | 설명 |
|---|---|---|
| POST | `/roadmap/generate` | 로드맵 생성 (SM-2 이력 보존) |
| GET | `/roadmap/{user_id}/{doc_id}` | 로드맵 조회 |
| GET | `/roadmap/{user_id}/{doc_id}/today` | 오늘의 학습·복습 항목 |
| GET | `/roadmap/{user_id}/{doc_id}/schedule` | SM-2 전체 복습 일정 |
| PATCH | `/roadmap/{user_id}/{doc_id}/progress` | 섹션 완료 처리 |
| POST | `/roadmap/{user_id}/{doc_id}/review` | SM-2 복습 결과 반영 |
| DELETE | `/roadmap/{user_id}/{doc_id}` | 로드맵 삭제 |

### 로드맵 생성 예시

```bash
curl -X POST http://localhost:8002/roadmap/generate \
  -H "Content-Type: application/json" \
  -d '{"user_id": "u01", "doc_id": "greedy_algorithm_948b2a15"}'
```

`doc_id`는 document_agent가 업로드 응답으로 반환하는 폴더 이름이다.

### 복습 결과 반영

```bash
curl -X POST http://localhost:8002/roadmap/u01/greedy_algorithm_948b2a15/review \
  -H "Content-Type: application/json" \
  -d '{"concept": "탐욕 알고리즘의 기본 개념과 원리", "quality": 4}'
```

`quality` 0-2 = 오답, 3-5 = 정답. 다음 복습 날짜가 자동 계산된다.

---

## 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DOCUMENT_AGENT_MATERIALS_DIR` | `../document_agent/generated_materials` | material.json 경로 |
| `RAG_AGENT_USER_PROFILE_DIR` | `../rag_agent/user_profiles` | 학습 속도 추정용 query 이력 |
| `ROADMAP_DIR` | `./roadmaps` | 로드맵 저장 경로 |
| `DEFAULT_DAILY_STUDY_MINUTES` | `30` | 일일 학습 목표(분) |
| `MAX_DAILY_PLAN_DAYS` | `30` | 계획 최대 일수 |
| `AI_PROVIDER` | `ollama` | `ollama` 또는 `openai` |
| `OLLAMA_CHAT_MODEL` | `gemma3:4b` | Ollama 모델명 |
| `API_PORT` | `8002` | 서버 포트 |
| `SUPABASE_URL` | — | 없으면 로컬 파일만 사용 |
| `SUPABASE_SERVICE_KEY` | — | 없으면 로컬 파일만 사용 |

---

## 실행

```bash
cd study_agent/roadmap_agent
cp .env.example .env   # 필요한 환경 변수 설정
python server.py
# Swagger UI: http://localhost:8002/docs
# http://localhost:8002/roadmap/u01/greedy_algorithm_948b2a15/view
```
Supabase 없이도 동작한다. document_agent에서 자료를 먼저 생성한 후 `doc_id`로 로드맵을 생성하면 된다.
