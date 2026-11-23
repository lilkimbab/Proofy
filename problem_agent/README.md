# 문제 생성 · 피드백 백엔드

내가 개발할 때 보는 빠른 기준 문서입니다. 이 파트는 Study Agent에서 **문제를 만들고, 답안을 채점하고, 피드백을 돌려주는 백엔드**입니다.

PDF를 읽거나 Vector DB를 직접 다루지는 않습니다. 다른 파트가 만든 자료 chunk를 Search/RAG로 받아서 문제와 피드백을 만듭니다.

## 핵심 기능

- 자료 기반 객관식/주관식 문제 생성
- 객관식 코드 채점
- 주관식 rubric 기반 LLM 채점
- 오답 분석, 약점 개념, 복습 추천
- 오답 맞춤 연습과 미니 점검 문제
- 기존 생성 문제 재사용 방지
- 재검토가 필요한 문제의 재생성 후보 관리
- 개념 카드, 빈칸, OX, 순서 배열, 짝 맞추기, 풀이 예시
- 김태훈 RAG Agent와 붙기 위한 `RAG_AGENT_URL` 어댑터

## 내가 맡은 범위

직접 하는 것:

- 문제, 정답, 해설, rubric 생성
- 문제 품질 검증
- 답안 제출과 채점
- 피드백 생성
- 사용자에게 보이는 피드백 문체 조정
- Search/RAG, 저장소, User Model과 주고받을 계약 정의

직접 하지 않는 것:

- PDF/OCR/Parser
- Vector DB와 embedding 저장
- Search/RAG 내부 구현
- 로그인/회원 DB
- 전체 학습 로드맵 생성

## 팀원이 빠르게 통합할 때 보는 기준

한 줄로 보면 이 서버는 **김태훈 DB/Search/RAG가 찾아준 자료 chunk를 받아 문제를 만들고, 사용자가 낸 답안을 채점해 피드백과 후속 학습 신호를 돌려주는 파트**입니다. PDF 업로드, OCR, Vector DB 운영, 로그인 DB는 다른 파트가 맡고, 우리는 chunk 이후의 문제 생성·채점·피드백·오답 개선에 집중합니다. 현재 SQLAlchemy 저장소는 로컬 테스트와 데모용이며, 최종 통합의 원천 저장소는 김태훈 파트의 DB/Vector DB입니다.

연동할 때 필요한 입력은 아래 형태의 `RetrievedChunk`입니다.

```json
{
  "chunk_id": "chunk_001",
  "document_id": "doc_001",
  "content": "자료 본문 내용",
  "page": 12,
  "section_title": "섹션 제목",
  "concepts": ["핵심 개념"],
  "tags": ["formula", "concept_relation"],
  "metadata": {
    "subject_domain": "science",
    "content_forms": ["formula", "concept_relation"]
  }
}
```

팀별 연결 기준:

- 김태훈 파트: DB/Vector DB/Search/RAG의 원천 저장소를 담당합니다. 관련 chunk를 제공하고, 생성된 문제·피드백 artifact를 다시 받을 색인 endpoint를 제공합니다.
- 왕호진 파트: 인증된 `user_id`를 서버에 전달합니다. 현재 로컬 검증은 `X-User-Id` 헤더를 씁니다.
- 조유찬 파트: 자료 구조화 결과의 `concepts`, `tags`, `metadata`를 넘겨주면 문제 형식 추천과 고난도 전략에 반영됩니다.
- 이우진 파트: 화면과 버튼 동작을 구현합니다. 이 서버는 UI를 만들지 않고, 가능한 문제/콘텐츠 기능과 추천 근거만 API로 제공합니다.
- Tutor/로드맵 파트: 피드백의 `mistake_type`, `weak_concepts`, `recommended_review`, mastery update payload를 받아 후속 학습에 연결합니다.

통합 체크리스트:

- Search/RAG 응답에 `document_id`, 본문, `chunk_id` 또는 안정적으로 만들 수 있는 ID가 있어야 합니다.
- 문제 생성 응답은 제출 전 정답·해설·rubric을 숨깁니다.
- 객관식 채점은 LLM 없이 코드로 처리합니다.
- 주관식 채점과 고난도 문제 생성은 schema 검증과 품질 gate를 통과해야 저장됩니다.
- 생성된 문제 artifact에는 정답/해설을 넣지 않고, 피드백 artifact는 사용자별 private 데이터로 보냅니다.
- 기본 테스트는 OpenAI key 없이 통과해야 합니다.

## 빠른 실행

처음 한 번만 설치합니다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
```

외부 API 비용 없이 데모로 실행합니다.

```bash
cp .env.free.example .env
.venv/bin/uvicorn app.main:app --reload
```

API 문서는 여기서 봅니다.

```text
http://127.0.0.1:8000/docs
```

## 팀 연동 설정

자료 검색은 두 방식 중 하나로 붙입니다.

```env
# 표준 Search Agent
SEARCH_AGENT_URL=http://localhost:8001
SEARCH_AGENT_API_KEY=
SEARCH_AGENT_API_KEY_HEADER=X-API-Key
SEARCH_AGENT_TIMEOUT_SECONDS=20

# 김태훈 RAG Agent를 그대로 붙일 때
RAG_AGENT_URL=http://localhost:8001
RAG_AGENT_SEARCH_PATH=/search
# batch 조회 endpoint가 있으면 설정합니다. 없으면 비워둡니다.
RAG_AGENT_CHUNKS_PATH=
# 김태훈 RAG Agent의 /fetch를 chunk 재조회 경로로 씁니다.
RAG_AGENT_FETCH_PATH=/fetch
# 문제 생성은 텍스트 chunk만 사용합니다.
RAG_AGENT_TEXT_ONLY=true
# ngrok 임시 서버를 붙일 때만 true로 둡니다.
RAG_AGENT_SKIP_NGROK_WARNING=false
# 호환용 예외 설정입니다. 통합 기본 흐름에서는 이미지를 쓰지 않습니다.
RAG_AGENT_PRESERVE_IMAGE_PAYLOADS=false

DEMO_SEARCH_ENABLED=false
```

`SEARCH_AGENT_API_KEY`를 넣으면 표준 Search Agent와 `RAG_AGENT_URL` 어댑터 호출에 `SEARCH_AGENT_API_KEY_HEADER` 이름으로 인증 헤더를 보냅니다. 기본 헤더명은 `X-API-Key`입니다. RAG 서버가 리랭킹이나 이미지 반환 때문에 느리면 `SEARCH_AGENT_TIMEOUT_SECONDS`를 45~60 정도로 올립니다.
실제 키는 커밋하지 말고 로컬 `.env`나 배포 환경변수에만 둡니다. 이 저장소의 `.gitignore`는 `.env`를 제외합니다.

`RAG_AGENT_URL`을 넣으면 김태훈 RAG Agent 응답을 우리 쪽 `RetrievedChunk` 형태로 맞춰 받습니다. RAG Agent와 이 서버가 둘 다 `8000`을 쓰면 한쪽을 `8001` 같은 포트로 바꿉니다. ngrok 주소를 임시로 쓸 때 브라우저 경고가 API 호출을 막으면 `RAG_AGENT_SKIP_NGROK_WARNING=true`를 켭니다.

RAG 응답은 `results`, `documents`, `chunks`, `items`, `data`, `matches`, `contexts`, `nodes` 같은 목록 형태를 받을 수 있고, 본문 필드는 `parent_text`, `text`, `content`, `page_content`, nested `document.page_content`를 지원합니다. `parent_text`가 있으면 문제 생성 본문으로 우선 사용하고, 짧은 child text는 metadata에 보존합니다. 최종 통합에서는 조유찬 Document Agent가 이미 텍스트화한 chunk만 사용하므로 문제/피드백 파트는 텍스트 전용입니다. `RAG_AGENT_TEXT_ONLY=true`일 때 `X-RAG-Text-Only: true` 헤더를 보내며, 김태훈 RAG 서버도 image/base64 payload를 내려주지 않는 것을 기본 계약으로 봅니다. 혹시 서버가 이미지를 내려줘도 우리 쪽은 실제 `image` payload를 버립니다. `/search` 결과의 중복 chunk는 첫 결과만 사용하지만, 다른 문서 결과가 섞이거나 검색 결과가 비어 있으면 문제 생성을 중단합니다. 저장된 근거 재조회는 `/chunks/batch`가 있으면 `RAG_AGENT_CHUNKS_PATH`를 쓰고, 없으면 `RAG_AGENT_FETCH_PATH=/fetch`로 `id` 필터 조회를 사용합니다.

생성된 문제/피드백/평가 리포트/학습 콘텐츠/학습 신호를 김태훈 Vector DB에도 남기려면 아래를 켭니다.

```env
GENERATED_ARTIFACT_INDEX_URL=http://localhost:8001/generated-artifacts/index
GENERATED_ARTIFACT_PUBLISH_ENABLED=true
GENERATED_ARTIFACT_PUBLISH_FAIL_FAST=false
GENERATED_ARTIFACT_API_KEY=
GENERATED_ARTIFACT_API_KEY_HEADER=X-API-Key
GENERATED_ARTIFACT_TIMEOUT_SECONDS=3
```

동작 방식:

- 문제 생성 후: 문제 본문, 보기, `user_id`, `document_id`, `source_chunk_ids`, 난이도, 개념 등을 보냅니다.
- 문제 artifact에는 정답/해설을 넣지 않습니다. 제출 전 검색으로 정답이 새는 것을 막기 위해서입니다.
- 답안 제출 후: 피드백 요약, 점수, 오답 유형, 약점 개념, 복습 추천을 사용자별 private artifact로 보냅니다.
- 평가 세트 최종 제출 후: 총점, 완료율, 시간 초과 여부, 강점/약점 개념, 복습 추천, 재도전 변화만 `assessment_report` private artifact로 보냅니다. 문항별 세부 결과나 feedback id 목록은 보내지 않습니다.
- 학습 콘텐츠 생성 후: 개념 카드, 빈칸, OX, 매칭, 순서 배열, 풀이 예시, 미니 시험을 `learning_content` private artifact로 보냅니다. 자동 채점형 콘텐츠는 정답과 해설을 색인 본문에 넣지 않습니다.
- 같은 제출에서 나온 mastery update, learning_state, recommended_review는 `learning_signal` private artifact로 한 번 더 보냅니다.
- 대량 사용자 상황을 고려해 색인 payload는 학습에 필요한 요약만 보냅니다. 색인 본문은 artifact당 최대 4,000자로 제한하고, 평가 리포트와 학습 신호의 개념/복습 목록은 상위 20개까지만 싣습니다. 장문 세부 기록은 Vector DB 색인에 넣지 않습니다.
- 색인 API 타임아웃은 `GENERATED_ARTIFACT_TIMEOUT_SECONDS`로 LLM 타임아웃과 따로 관리합니다. 기본값은 3초라 Vector DB 지연이 문제 생성/제출 요청을 오래 붙잡지 않습니다.
- 기본값은 꺼져 있습니다. 김태훈 쪽 실제 색인 endpoint가 준비되면 URL만 맞추면 됩니다.
- 이 서버의 로컬 DB는 테스트/데모용 cache에 가깝습니다. 운영에서 문제와 피드백을 장기 저장·검색하는 원천은 김태훈 DB/Vector DB 쪽으로 둡니다.

LLM 비용을 추적하려면 모델 단가를 넣어둡니다. 값을 모르면 `0`으로 두고 나중에 바꾸면 됩니다.

```env
LLM_STANDARD_INPUT_PRICE_KRW_PER_1M_TOKENS=0
LLM_STANDARD_OUTPUT_PRICE_KRW_PER_1M_TOKENS=0
LLM_PREMIUM_INPUT_PRICE_KRW_PER_1M_TOKENS=0
LLM_PREMIUM_OUTPUT_PRICE_KRW_PER_1M_TOKENS=0
LLM_MONTHLY_USER_BUDGET_KRW=0
LLM_BUDGET_WARNING_RATIO=0.8
LLM_ENFORCE_MONTHLY_BUDGET=false
PROBLEM_GENERATION_MONTHLY_LIMIT=0
PROBLEM_GENERATION_HIGH_RIGOR_MONTHLY_LIMIT=0
```

월정액 배포에서는 `PROBLEM_GENERATION_MONTHLY_LIMIT`로 사용자별 월 문제 생성 수를 제한하고, 시험 대비/고난도 문제는 `PROBLEM_GENERATION_HIGH_RIGOR_MONTHLY_LIMIT`로 별도 제한합니다. `LLM_ENFORCE_MONTHLY_BUDGET=true`를 켜면 사용자의 월 LLM 예산 초과 시 새 문제 생성, LLM 기반 피드백, LLM 기반 학습 콘텐츠 생성을 막습니다. 객관식 기본 채점처럼 코드로 끝나는 경로는 비용 한도에 걸지 않습니다. 사용량 요약은 목록 조회 limit와 별개로 DB aggregate로 전체 기간을 합산합니다.

## 주요 API

```text
POST /api/problems/generate
POST /api/assessment-sessions/readiness
POST /api/assessment-sessions/generate
GET  /api/assessment-sessions/{session_id}
POST /api/assessment-sessions/{session_id}/submit
GET  /api/assessment-sessions/{session_id}/report
POST /api/assessment-sessions/{session_id}/retry
GET  /api/assessment-sessions/{session_id}/history
GET  /api/problems/{problem_id}
GET  /api/problems/{problem_id}/analytics
POST /api/problems/{problem_id}/hints
GET  /api/problem-analytics
GET  /api/problem-template-analytics
GET  /api/problem-regeneration-candidates
POST /api/problem-regeneration-candidates/{candidate_id}/regenerate
GET  /api/usage-ledger
GET  /api/usage-ledger/summary
POST /api/quality-reports
POST /api/problems/{problem_id}/submit
GET  /api/feedback/{feedback_id}
POST /api/feedback/{feedback_id}/actions
GET  /api/feedback/{feedback_id}/actions

POST /api/learning-contents/generate
POST /api/learning-contents/recommendations
GET  /api/learning-contents/{content_id}
POST /api/learning-contents/mistake-drills/generate
POST /api/learning-contents/mini-exams/generate
```

현재는 임시로 `X-User-Id` 헤더가 필요합니다.

```text
X-User-Id: user_001
```

## 짧은 API 확인

데모 모드 서버를 켠 뒤 문제를 생성합니다.

```bash
curl -s -X POST http://127.0.0.1:8000/api/problems/generate \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: user_001' \
  -d '{
    "document_id": "demo_doc",
    "concepts": ["뉴턴 제2법칙"],
    "type": "multiple_choice",
    "problem_style": "concept_check",
    "count": 1
  }'
```

프론트에서는 자유 프롬프트 대신 `problem_style`을 버튼/칩으로 고르게 합니다. 허용값은 `auto`, `concept_check`, `exam_application`, `calculation_practice`, `misconception_drill`, `evidence_analysis`, `error_detection`입니다.

학습 콘텐츠는 먼저 `/api/learning-contents/recommendations`로 자료에 맞는 형식을 받습니다. 이 API는 우리 파트가 제공할 수 있는 객관식, 주관식, 고난도 주관식, OX, 빈칸, 매칭 같은 문제/학습 콘텐츠 기능을 `problem_options`와 `content_options`로 명시합니다. 화면 구성과 버튼 동작은 UI 파트에서 결정하며, 이 판단은 저장용 분류가 아니라 현재 검색 chunk의 `tags`, `metadata`, `concepts`, `content`만 보고 즉시 계산합니다.

답안을 제출합니다.

```bash
curl -s -X POST http://127.0.0.1:8000/api/problems/{problem_id}/submit \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: user_001' \
  -d '{"answer": {"choice_id": "A", "text": "A"}, "confidence_level": 3}'
```

`confidence_level`은 선택값이고 1~4 범위입니다. 보내면 피드백에 `learning_state`가 함께 저장되어 정답이지만 불안정한 이해인지, 확신 있는 오개념인지까지 구분합니다.

문제나 피드백이 이상하면 신고할 수 있습니다.

시험 대비 문제 세트를 바로 만들기 전에, 지금 자료와 풀이 기록이 어느 정도 준비됐는지 먼저 확인할 수 있습니다.

```bash
curl -s -X POST http://127.0.0.1:8000/api/assessment-sessions/readiness \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: user_001' \
  -d '{
    "document_id": "demo_doc",
    "concepts": ["뉴턴 제2법칙"],
    "type": "multiple_choice",
    "count": 5,
    "goal": "exam_prep",
    "target_rigor": "high"
  }'
```

응답의 `status`는 `not_ready`, `diagnostic_ready`, `personalized_ready`, `exam_ready` 중 하나입니다. 자료 근거가 조금이라도 있으면 사용자가 원한 고난도/시험 대비 세트는 막지 않고, 대신 “근거 안에서 가능한 최고 수준”이라는 경고를 함께 줍니다.

`/api/assessment-sessions/generate`는 `session_id`와 정답이 숨겨진 문제 목록을 돌려줍니다. 선택값 `time_limit_seconds`를 보내면 세트 제한 시간으로 저장됩니다. 세트를 다 풀면 `/api/assessment-sessions/{session_id}/submit`으로 한 번에 제출하고, `/api/assessment-sessions/{session_id}/report`에서 점수, 완료율, 총 풀이시간, 시간 초과 여부, 잘한 개념, 약점 개념, 개념별 결과, 다음 행동을 조회합니다. 중간 저장처럼 일부만 먼저 채점하려면 submit 요청에 `"finalize": false`를 넣습니다.
다시 풀기는 `/api/assessment-sessions/{session_id}/retry`로 새 세트를 만들고, 새 리포트에서 `previous_score_ratio`, `score_delta`, `concept_score_deltas`로 이전 결과와 비교합니다.
여러 번 다시 풀면 `/api/assessment-sessions/{session_id}/history`에서 attempt 목록, 최고 점수, 최신 점수 변화, 전체 trend를 조회합니다.

```bash
curl -s -X POST http://127.0.0.1:8000/api/quality-reports \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: user_001' \
  -d '{
    "target_type": "problem",
    "target_id": "{problem_id}",
    "reason": "answer_wrong",
    "message": "정답 근거가 이상해 보여요."
  }'
```

피드백 이후 사용자가 어떤 행동을 했는지도 저장할 수 있습니다.
피드백 응답의 `copy.next_action_type`은 아래 `action_type`에 그대로 넣고, `copy.next_action_label`은 화면 표시용으로만 사용합니다.

```bash
curl -s -X POST http://127.0.0.1:8000/api/feedback/{feedback_id}/actions \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: user_001' \
  -d '{
    "event_type": "next_action_clicked",
    "action_type": "review_concept_card",
    "event_metadata": {"surface": "feedback_card"}
  }'
```

## 테스트

기본 테스트는 OpenAI key 없이 돌아갑니다.

```bash
.venv/bin/python -m pytest -q
PYTHONPYCACHEPREFIX=/tmp/problem_agent_pycache .venv/bin/python -m compileall app tests
```

고난도 문제 생성 품질만 따로 확인할 때는 아래 eval을 돌립니다.

```bash
.venv/bin/python -m pytest tests/test_eval_runner.py -q
```

이 eval에는 물리, 수학, 경제, 생물, 통계, 컴퓨터과학, 문학, 정책 자료처럼 만든 9개 케이스가 들어 있습니다. 단순히 문제가 생성됐는지가 아니라 근거 chunk, 여러 개념 연결, LaTeX 수식, rubric, 오답 진단, 자료 밖 내용 차단까지 함께 봅니다.

실제 강의 자료에서 검색 품질, 문제 품질, latency, DB write, artifact publish, reject/retry 비율까지 보려면 live benchmark를 사용합니다. 실행 절차와 case 작성법은 `docs/live_benchmark_guide.md`에 정리되어 있습니다.

```bash
./scripts/run_tests.sh

export PROBLEM_AGENT_LIVE_EVAL_ENABLED=true
export PROBLEM_AGENT_LIVE_EVAL_CASES=evals/live_materials/my_real_cases.jsonl
export PROBLEM_AGENT_LIVE_EVAL_OUTPUT_DIR=evals/reports
export PROBLEM_AGENT_LIVE_EVAL_COMPARE_BASELINE_SEARCH=true
export RAG_AGENT_URL=http://localhost:8001
export OPENAI_API_KEY=...
./scripts/run_live_eval.sh
```

실제 OpenAI 호출은 필요할 때만 실행합니다. 요금이 발생할 수 있습니다.

```bash
OPENAI_API_KEY=sk-... .venv/bin/python -m pytest tests/test_openai_smoke_llm.py -q -m llm
```

테스트 모델만 바꾸고 싶으면 `OPENAI_SMOKE_PROBLEM_MODEL`, `OPENAI_SMOKE_GRADING_MODEL`을 같이 설정합니다.

실제 김태훈 RAG/Search와 generated artifact 전송 endpoint가 준비되면 아래 smoke test를 따로 실행합니다. 두 번째 명령은 smoke artifact 1개를 실제 endpoint에 씁니다. 정식 JSON 색인 API가 있으면 `GENERATED_ARTIFACT_INDEX_URL`을 쓰고, 지금처럼 RAG Agent `/add`만 있으면 `GENERATED_ARTIFACT_ADD_URL`을 쓰면 됩니다.

```bash
RAG_AGENT_URL=http://localhost:8001 \
SEARCH_AGENT_API_KEY=... \
RAG_SMOKE_DOCUMENT_ID=실제_문서_ID \
.venv/bin/python -m pytest tests/test_rag_agent_live_smoke.py -q -m rag

GENERATED_ARTIFACT_SMOKE_ENABLED=true \
GENERATED_ARTIFACT_ADD_URL=http://localhost:8001/add \
GENERATED_ARTIFACT_API_KEY=... \
.venv/bin/python -m pytest tests/test_generated_artifact_live_smoke.py -q -m rag

PROBLEM_AGENT_E2E_SMOKE_ENABLED=true \
RAG_AGENT_URL=http://localhost:8001 \
SEARCH_AGENT_API_KEY=... \
GENERATED_ARTIFACT_ADD_URL=http://localhost:8001/add \
GENERATED_ARTIFACT_API_KEY=... \
PROBLEM_AGENT_E2E_SMOKE_DOCUMENT_ID=실제_문서_ID \
PROBLEM_AGENT_E2E_SMOKE_CONCEPT=핵심_개념 \
.venv/bin/python -m pytest tests/test_problem_agent_live_e2e_smoke.py -q -m rag
```

위 E2E smoke test는 기본적으로 비용 방지를 위해 문제 생성을 deterministic fallback으로 돌리고, RAG 조회와 artifact write만 실제 서버로 확인합니다. OpenAI까지 한 번에 확인하려면 `PROBLEM_AGENT_E2E_SMOKE_USE_OPENAI=true`와 `OPENAI_API_KEY=...`를 추가합니다.

```bash
PROBLEM_AGENT_E2E_SMOKE_ENABLED=true \
PROBLEM_AGENT_E2E_SMOKE_USE_OPENAI=true \
OPENAI_API_KEY=sk-... \
RAG_AGENT_URL=http://localhost:8001 \
SEARCH_AGENT_API_KEY=... \
GENERATED_ARTIFACT_ADD_URL=http://localhost:8001/add \
GENERATED_ARTIFACT_API_KEY=... \
PROBLEM_AGENT_E2E_SMOKE_DOCUMENT_ID=실제_문서_ID \
PROBLEM_AGENT_E2E_SMOKE_CONCEPT=핵심_개념 \
.venv/bin/python -m pytest tests/test_problem_agent_live_e2e_smoke.py -q -m llm
```

## 반드시 지킬 정책

- 문제는 사용자가 올린 자료 안에서만 만듭니다.
- 모든 문제와 콘텐츠는 근거 chunk를 가져야 합니다.
- 제출 전에는 정답/해설/rubric을 숨깁니다.
- 객관식 채점은 LLM이 아니라 코드로 합니다.
- 업로드 자료를 다른 사용자 문제 생성이나 모델 학습 데이터로 쓰면 안 됩니다.

## 자주 보는 문서

- `problem-feedback-roadmap.md`: 다음 구현 기준
- `docs/problem-feedback-integration-contracts.md`: 팀 연동 계약
- `docs/problem-feedback-quality-application-plan.md`: 품질, 고난도, 비용 기준
- `docs/problem-feedback-human-tone-strategy.md`: 사용자에게 보이는 말투 기준
