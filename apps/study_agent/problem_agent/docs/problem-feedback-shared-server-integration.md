# 같은 서버 통합 점검 노트

추후 `document_agent`, `tutor_agent`, `problem_agent`를 같은 FastAPI 서버에서 합칠 때 지켜야 할 기준이다.

## 현재 확인 결과

- `problem_agent`는 독립 실행용 `app.main:create_app()`을 가진다.
- 동시에 공유 서버에 붙일 수 있도록 `app.api.include_problem_feedback_routers(app)`를 제공한다.
- 문제/피드백 라우터는 아래 경로를 사용한다.
  - `POST /api/problems/generate`
  - `POST /api/assessment-sessions/readiness`
  - `POST /api/assessment-sessions/generate`
  - `GET /api/assessment-sessions/{session_id}`
  - `POST /api/assessment-sessions/{session_id}/submit`
  - `GET /api/assessment-sessions/{session_id}/report`
  - `POST /api/assessment-sessions/{session_id}/retry`
  - `GET /api/assessment-sessions/{session_id}/history`
  - `GET /api/problems/{problem_id}`
  - `GET /api/problems/{problem_id}/analytics`
  - `POST /api/problems/{problem_id}/hints`
  - `GET /api/problem-analytics`
  - `GET /api/problem-template-analytics`
  - `GET /api/problem-regeneration-candidates`
  - `POST /api/problem-regeneration-candidates/{candidate_id}/regenerate`
  - `GET /api/usage-ledger`
  - `GET /api/usage-ledger/summary`
  - `POST /api/quality-reports`
  - `POST /api/problems/{problem_id}/submit`
  - `GET /api/feedback/{feedback_id}`
  - `POST /api/feedback/{feedback_id}/actions`
  - `GET /api/feedback/{feedback_id}/actions`
  - `POST /api/learning-contents/generate`
  - `POST /api/learning-contents/recommendations`
  - `GET /api/learning-contents/{content_id}`
  - `POST /api/learning-contents/mistake-drills/generate`
  - `POST /api/learning-contents/mini-exams/generate`

## 통합 서버에서 권장하는 붙이는 방식

통합 서버의 메인 앱에서 아래처럼 붙인다.

```python
from fastapi import FastAPI

from app.api import (
    find_problem_feedback_route_conflicts,
    include_problem_feedback_routers,
)

app = FastAPI(title="Study Agent")

conflicts = find_problem_feedback_route_conflicts(app)
if conflicts:
    raise RuntimeError(f"problem_agent route conflicts: {conflicts}")

include_problem_feedback_routers(app)
```

중요한 점은 `problem_agent.app.main.app` 객체를 직접 가져오지 않는 것이다. 각 파트가 자기 `FastAPI()` 객체를 따로 만들면 lifespan, middleware, DB 초기화, CORS 설정이 중복된다.
`find_problem_feedback_route_conflicts(app)`는 `{problem_id}`와 `{id}`처럼 parameter 이름만 다른 같은 경로도 같은 route로 보고 충돌을 잡는다.

## 반드시 확인할 충돌 지점

### 1. Python 패키지명

현재 이 파트의 패키지명은 `app`이다. `document_agent`나 `tutor_agent`도 `app` 패키지를 쓰면 같은 서버에서 import 충돌이 난다.

통합 시 권장 선택지는 둘 중 하나다.

1. 하나의 루트 `app` 안에 기능별 하위 패키지로 합친다.
   - 예: `app.problem_feedback`, `app.document_agent`, `app.tutor_agent`
2. 각 파트의 패키지를 명확히 바꾼다.
   - 예: `problem_agent`, `document_agent`, `tutor_agent`

폴더만 나란히 두고 각 폴더 안에 `app` 패키지를 그대로 유지하는 방식은 피한다.

### 2. 저장소 경계

현재 `problem_agent`는 로컬 테스트와 데모를 위해 자체 `app.db.Base`, `SessionLocal`, `get_db()`를 가진다.

최종 통합에서는 김태훈 DB/Vector DB가 chunk와 생성 artifact의 원천 저장소다. 이 파트의 SQLAlchemy repository는 운영 원천 DB가 아니라, 통합 전 로컬 검증용 저장소로 본다.

- 운영에서는 각 파트가 따로 `create_all()`을 호출하지 않는다.
- `AUTO_CREATE_TABLES=false`를 유지한다.
- `AUTO_CREATE_TABLES=true`는 SQLite 데모 DB에서만 허용된다. PostgreSQL에서는 시작 시 `create_all()`을 막고 김태훈 저장소 adapter 또는 색인 API 연결을 사용해야 한다.
- 문제/피드백 장기 저장과 검색은 김태훈 쪽 저장소 adapter 또는 색인 API로 연결한다.
- 테이블명 충돌을 확인한다.

현재 로컬 테스트/데모 repository가 쓰는 주요 테이블명:

- `problems`
- `assessment_sessions`
- `submissions`
- `problem_hint_events`
- `feedbacks`
- `feedback_action_events`
- `user_concept_stats`
- `problem_item_analytics`
- `problem_template_analytics`
- `problem_regeneration_candidates`
- `mistake_remediation_events`
- `usage_ledger`
- `user_quality_reports`

### 3. 인증 의존성

현재는 임시로 `X-User-Id` 헤더를 사용한다.

통합 서버에서는 왕호진 파트의 계정/인증 결과를 `user_id`로 넘겨야 한다. FastAPI dependency override 또는 공통 인증 dependency로 `get_user_id`를 대체한다.

### 4. Document/Search/Tutor 경계

문제/피드백 파트는 PDF, OCR, 문서 구조화, Vector DB 내부를 직접 다루지 않는다.
받아야 하는 최소 입력:

```json
{
  "chunk_id": "chunk_001",
  "document_id": "doc_001",
  "content": "자료 본문",
  "page": 12,
  "section_title": "섹션 제목",
  "concepts": ["핵심 개념"]
}
```

Search/RAG endpoint가 인증을 요구하면 `SEARCH_AGENT_API_KEY`, `SEARCH_AGENT_API_KEY_HEADER`를 설정해 같은 헤더를 보낸다. ngrok 임시 endpoint를 쓸 때 API 호출이 브라우저 경고에 막히면 `RAG_AGENT_SKIP_NGROK_WARNING=true`를 켜서 `ngrok-skip-browser-warning: true` 헤더를 보낸다.

김태훈 Retrieval 서버의 `/search` 응답에서 `score`는 chunk metadata에 보존한다. 최종 통합에서는 조유찬 Document Agent가 텍스트화한 chunk만 검색 대상으로 쓰므로 문제/피드백 파트는 이미지 payload를 사용하지 않는다. `RAG_AGENT_TEXT_ONLY=true`가 기본이며, 이때 `X-RAG-Text-Only: true` 헤더를 보낸다. 김태훈 RAG 서버도 image/base64 payload를 제외해서 응답 크기와 검색 지연을 줄이는 것을 기본 계약으로 본다.

Tutor Agent가 질의응답을 담당하더라도, 문제/피드백 파트는 채점과 오답 진단 결과를 제공한다. Tutor Agent는 필요하면 `Feedback`, `UserConceptStat`, `ProblemItemAnalytics` 결과를 읽어 설명에 활용할 수 있다.

### 4-1. 생성된 문제/피드백 Vector DB 색인

생성된 문제, 피드백, 평가 리포트, 학습 콘텐츠, 학습 신호는 우리 로컬 DB에 저장한 뒤, 선택적으로 김태훈 Vector DB 색인 API에도 보낼 수 있다.

설정:

```env
GENERATED_ARTIFACT_INDEX_URL=http://localhost:8001/generated-artifacts/index
GENERATED_ARTIFACT_ADD_URL=http://localhost:8001/add
GENERATED_ARTIFACT_ADD_TITLE_PREFIX=generated_artifact
GENERATED_ARTIFACT_PUBLISH_ENABLED=true
GENERATED_ARTIFACT_PUBLISH_FAIL_FAST=false
GENERATED_ARTIFACT_API_KEY=
GENERATED_ARTIFACT_API_KEY_HEADER=X-API-Key
GENERATED_ARTIFACT_TIMEOUT_SECONDS=3
```

역할 경계:

- 문제/피드백 파트는 `GeneratedArtifactPublisher`로 HTTP payload만 보낸다.
- 정식 색인 API가 아직 없을 때는 smoke 목적으로 `GENERATED_ARTIFACT_ADD_URL`에 RAG Agent `/add`를 넣어 multipart txt 파일 형태로 보낼 수 있다. 이때 form `title`은 비워 두지 않고 `generated_artifact__{document_id}__{artifact_type}` 형태로 만든다.
- Vector DB 저장, embedding, 중복 처리, 검색 필터링은 김태훈 파트가 담당한다.
- 문제 artifact는 제출 전 정답 유출을 막기 위해 정답/해설을 색인 본문에 넣지 않는다.
- 문제 artifact metadata에는 `schema_version`, `producer`, `problem_id`, `question`, `problem_type`, `difficulty`, `concepts`, `source_refs`를 넣는다.
- 피드백 artifact metadata에는 `schema_version`, `producer`, `feedback_id`, `problem_id`, `submission_id`, 점수, 오답 유형, 약점 개념, 복습 추천을 넣는다.
- assessment report artifact metadata에는 `schema_version`, `producer`, `session_id`, 점수 요약, 완료율, 시간 초과 여부, 강점/약점 개념, 복습 추천, 재도전 변화, 개념별 요약만 넣는다. 문항별 세부 결과와 feedback id 목록은 보내지 않는다.
- learning content artifact metadata에는 `schema_version`, `producer`, `content_id`, `content_type`, `interaction_mode`, 품질 점수, 근거 chunk를 넣는다.
- learning signal artifact metadata에는 `schema_version`, `producer`, `problem_id`, `submission_id`, `feedback_id`, `learning_state`, `mastery_updates`, 복습 추천을 넣는다.
- 학습 콘텐츠가 자동 채점형이면 정답, 해설, 정답 순서를 색인 본문과 metadata에 넣지 않는다.
- 피드백, assessment report, learning content, learning signal artifact는 `user_id` 기준 private 데이터로 색인해야 한다.
- Tutor/Search에서 이 데이터를 다시 읽을 때는 `visibility`와 `artifact_type` 필터를 반드시 적용해야 한다.

확장성 기준:

- 운영 트래픽에서는 문제 생성/제출 API가 Vector DB write 지연을 직접 떠안지 않게 queue/outbox 또는 batch index API를 둔다.
- 문제/피드백 파트가 보내는 payload는 색인용 요약이다. artifact 본문은 4,000자로 제한하고, 평가 리포트와 학습 신호는 개념/복습 목록을 상위 20개로 제한한다. 문항별 세부 결과나 feedback id 목록은 보내지 않는다.
- 색인 API 타임아웃은 `GENERATED_ARTIFACT_TIMEOUT_SECONDS`로 분리하고 기본 3초로 둔다.
- 김태훈 파트는 `artifact_type`, `visibility`, `created_at` 기준 retention과 재색인 정책을 둘 수 있어야 한다.

통합 smoke test:

```bash
RAG_AGENT_URL=http://localhost:8001 \
SEARCH_AGENT_API_KEY=... \
RAG_SMOKE_DOCUMENT_ID=실제_문서_ID \
.venv/bin/python -m pytest tests/test_rag_agent_live_smoke.py -q -m rag

GENERATED_ARTIFACT_SMOKE_ENABLED=true \
GENERATED_ARTIFACT_INDEX_URL=http://localhost:8001/generated-artifacts/index \
GENERATED_ARTIFACT_API_KEY=... \
.venv/bin/python -m pytest tests/test_generated_artifact_live_smoke.py -q -m rag

PROBLEM_AGENT_E2E_SMOKE_ENABLED=true \
RAG_AGENT_URL=http://localhost:8001 \
SEARCH_AGENT_API_KEY=... \
GENERATED_ARTIFACT_INDEX_URL=http://localhost:8001/generated-artifacts/index \
GENERATED_ARTIFACT_API_KEY=... \
PROBLEM_AGENT_E2E_SMOKE_DOCUMENT_ID=실제_문서_ID \
PROBLEM_AGENT_E2E_SMOKE_CONCEPT=핵심_개념 \
.venv/bin/python -m pytest tests/test_problem_agent_live_e2e_smoke.py -q -m rag
```

기본 E2E smoke test는 비용을 막기 위해 문제 생성을 deterministic fallback으로 돌린다. 실제 OpenAI 문제 생성까지 포함해 확인할 때만 `PROBLEM_AGENT_E2E_SMOKE_USE_OPENAI=true`, `OPENAI_API_KEY=...`를 추가하고 `-m llm`으로 실행한다.

### 5. Route prefix

현재 문제/피드백 파트는 `/api` 아래에 route를 둔다. 다른 파트도 `/api/problems`, `/api/feedback`, `/api/learning-contents`를 쓰면 충돌한다.

통합 전 `find_problem_feedback_route_conflicts(app)`로 중복 경로를 확인해야 한다. 이 함수는 HTTP method와 canonical path를 함께 비교하므로, 같은 path의 `GET`/`POST`처럼 의도적으로 method가 다른 route는 충돌로 보지 않는다.

## 통합 전 체크리스트

- [ ] `document_agent`, `tutor_agent`가 `app` 패키지명을 쓰는지 확인한다.
- [ ] 통합 서버에서 라우터만 include하고 각 파트의 standalone `app` 객체는 import하지 않는다.
- [ ] 문제/피드백 장기 저장을 김태훈 DB/Vector DB adapter 또는 색인 API로 연결한다.
- [ ] `X-User-Id` 임시 인증을 공통 인증 dependency로 교체한다.
- [ ] Search/RAG endpoint가 보호되어 있으면 `SEARCH_AGENT_API_KEY_HEADER`와 실제 키가 맞는지 확인한다.
- [ ] Search/RAG 출력이 `RetrievedChunk` 계약을 만족하는지 확인한다.
- [ ] 김태훈 RAG 응답이 `text/content/page_content`, `source`, `page`, `metadata` 중 어떤 형태로 오는지 샘플을 확인한다.
- [ ] `tests/test_generated_artifact_live_smoke.py`로 생성 artifact 색인 endpoint가 smoke payload를 받는지 확인한다.
- [ ] `tests/test_problem_agent_live_e2e_smoke.py`로 RAG chunk 기반 문제 생성, 제출, 피드백, artifact write가 한 번에 도는지 확인한다.
- [ ] RAG 응답의 문서 식별자가 요청한 `document_id`와 일치하는지 확인한다.
- [ ] route prefix 중복이 없는지 확인한다.
- [ ] 실제 PDF 업로드 이후 문제 생성, 답안 제출, 피드백, Tutor 설명까지 end-to-end smoke test를 만든다.

## 현재 한계

원격 GitHub의 `document-agent`, `tutor-agent` 브랜치는 현재 환경에서 인증 문제로 직접 내려받아 확인하지 못했다. 이 문서는 현재 `problem_agent` 코드 기준의 통합 준비 사항이다.
