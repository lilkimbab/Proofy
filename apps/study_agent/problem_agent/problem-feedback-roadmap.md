# 문제 생성 + 피드백 실행 로드맵

이 문서는 앞으로 구현과 점검 때 보는 기준 문서다. 이전의 세부 Phase 0~15는 핵심 Phase 1~5로 통합했고, 이후 사업성 차별화와 실제 RAG 통합 안정화는 Phase 6~7로 따로 관리한다.

범위는 **문제 생성 + 피드백 파트**만 다룬다. 자료 파싱, OCR, Vector DB, 계정 DB, 전체 로드맵 생성은 다른 팀 파트와 계약으로 연결한다.

## 핵심 원칙

- 사용자가 올린 자료 안에서만 문제와 피드백을 만든다.
- 생성 문제는 반드시 `source_chunk_ids`를 가진다.
- 정답/해설은 제출 전에는 숨기고, 제출 후에만 공개한다.
- 객관식 채점은 코드로 결정적으로 처리한다.
- 주관식 채점과 고난도 문제 생성은 LLM을 쓰되 JSON Schema로 검증한다.
- 문제 품질, 피드백 문체, 비용을 모두 테스트 가능한 기준으로 관리한다.
- 김태훈 RAG/Search 파트는 직접 수정하지 않고 `SearchService` 어댑터로 연결한다.

## 역할 경계

직접 구현하는 것:

- `ProblemAgent`: 자료 기반 문제, 정답, 해설, rubric 생성
- `FeedbackAgent`: 주관식 채점, 오답 분석, 개선 방향 생성
- `QualityChecker`: 출처, rubric, 보기, 수식/계산형 문제 품질 검증
- `LearningVoiceRenderer`: 사용자에게 보이는 피드백 문체 조정
- API: 문제 생성, 문제 조회, 답안 제출, 피드백 조회, 학습 콘텐츠 생성
- 팀 연동 계약: Search/RAG, 저장소, User Model 업데이트 payload

직접 구현하지 않는 것:

- PDF/OCR/Parser 구현
- Vector DB와 embedding 저장소 운영
- Search/RAG 내부 검색 알고리즘
- 사용자 계정/개인정보 DB
- 전체 학습 로드맵 생성

## Phase 1. 핵심 문제/피드백 엔진

상태: DONE

목표:

- 자료 chunk를 받아 객관식/주관식 문제를 생성한다.
- 답안을 제출하면 채점과 피드백을 반환한다.
- 제출 전/후 정답 공개 정책을 지킨다.

포함 기능:

- FastAPI 기본 구조
- `POST /api/problems/generate`
- `GET /api/problems/{problem_id}`
- `POST /api/problems/{problem_id}/submit`
- `GET /api/feedback/{feedback_id}`
- 객관식 코드 채점
- 주관식 rubric 기반 LLM 채점 경로
- 문제/제출/피드백/UserConceptStat 로컬 저장소
- 중복 제출 방지

검증:

```bash
.venv/bin/python -m pytest tests/test_problem_feedback_service.py tests/test_problem_feedback_api.py -q
```

## Phase 2. Search/RAG와 팀 연동

상태: IN_PROGRESS

목표:

- 김태훈 Search/RAG 파트와 붙기 위한 계약을 유지한다.
- RAG 내부 구현이 바뀌어도 문제/피드백 코드는 `SearchService`만 바라보게 한다.

포함 기능:

- 표준 Search Agent 계약: `/search`, `/chunks/batch`
- 김태훈 RAG Agent 호환 계약: `RAG_AGENT_URL`
- 생성된 문제/피드백을 Vector DB 색인 API로 보내는 `GeneratedArtifactPublisher`
- `GENERATED_ARTIFACT_INDEX_URL` 기반 outbound 연동
- 문제 색인 본문에서 정답/해설 제외
- 피드백 색인은 사용자별 private artifact로 전송
- `document_id -> title`, `text -> content`, `source -> section_title` 변환
- RAG 응답에 임시 `rag_...` chunk ID 생성
- Search/RAG 장애 시 API `503` 반환
- 팀 연동 문서: [docs/problem-feedback-integration-contracts.md](docs/problem-feedback-integration-contracts.md)

남은 작업:

- 실제 김태훈 `rag_agent` 서버와 end-to-end 테스트
- RAG 결과의 안정적인 `chunk_id` 제공 방식 협의
- `/chunks/batch`를 RAG 쪽에 추가할지, 우리 쪽 `evidence_snapshot` 저장으로 대체할지 결정
- 김태훈 쪽 실제 색인 endpoint 경로 확정

검증:

```bash
.venv/bin/python -m pytest tests/test_search_service_contract.py tests/test_search_agent_errors.py tests/test_generated_artifact_publisher.py -q
```

## Phase 3. 문제 품질과 고난도 출제

상태: DONE

목표:

- 단순 정의형 문제만 반복하지 않도록 자료 준비도, 출제 전략, 난이도 요청을 반영한다.
- 사용자가 “시험 대비”, “고난도”, “수능 30번 수준”, “대학 시험형”처럼 요청하면 더 깊은 문제를 만들 수 있게 한다.

포함 기능:

- Structured Outputs 기반 LLM 출력 검증
- `MaterialReadinessService`
- `AssessmentBlueprintService`
- `LearningTaskStrategyRouter`
- `AdaptiveHighRigorPlanner`
- `ProfessorGradeItemDesigner`
- `ItemDesignBrief`: 목표 개념, 평가 주장, 관찰 가능한 근거, 예상 사고 단계 저장
- `ItemModelSelector`: 문항 모델 자동 선택
- `DifficultyProfile`: 실제 사고 요구량 기반 난이도 점수화
- `TeacherReviewChecklist`: 출처, 정답 명확성, 보기/rubric 품질 게이트
- `ProfessorGradeItemScore`: 문항 품질 점수화
- `StudentResponseSimulationReport`: 정답/부분정답/오개념/조건누락 답안 dry-run
- source chunk 기반성 검증
- 자료에 없는 수치/조건 생성 방지
- 원문 장문 복제 방지
- 실제 과목 chunk처럼 만든 고난도 문제 생성 eval set
- 객관식 보기 4개, 정답 1개, 보기별 해설 검증
- 주관식 rubric 점수 합계와 부분 점수 검증
- 계산형/수식형 문제에서 LaTeX 사용 지침

검증:

```bash
.venv/bin/python -m pytest \
  tests/test_problem_quality_rules.py \
  tests/test_quality_strategy_router.py \
  tests/test_deep_grounding.py \
  tests/test_quality_hardening.py \
  tests/test_exam_calculation_generation.py \
  tests/test_adaptive_high_rigor_generation.py \
  tests/test_eval_runner.py \
  -q
```

## Phase 4. 피드백, 문체, 개인화

상태: DONE

목표:

- 피드백이 차갑거나 번역투처럼 보이지 않게 한다.
- 오답 후 “왜 틀렸는지”와 “다음에 뭘 하면 되는지”가 바로 보이게 한다.
- User Model 업데이트를 통해 반복 오답과 복습 추천을 만든다.

포함 기능:

- 객관식 선택지별 진단
- 주관식 rubric별 채점 결과 구조화 및 `evaluation_details` 저장
- 오답 유형 enum
- `UserConceptStat` mastery 업데이트
- 반복 오답 복습 추천
- `LearningVoiceRenderer`
- `LearningCopyQualityChecker`
- 친근하지만 존댓말을 쓰는 교육자 문체
- 내부 용어, 과장 칭찬, 비난 표현 차단

검증:

```bash
.venv/bin/python -m pytest \
  tests/test_feedback_quality.py \
  tests/test_user_concept_stat_repository.py \
  tests/test_learning_voice_renderer.py \
  tests/test_korean_style_quality.py \
  -q
```

## Phase 5. 제품화, 운영 지표, 팀 통합

상태: DONE

목표:

- 생성된 문제와 피드백이 실제 사용 후에도 품질을 유지하는지 추적한다.
- 오답 맞춤 학습 콘텐츠와 미니 점검 문제를 제공한다.
- 실제 서비스 비용과 품질을 관리한다.
- 팀 통합과 UI 개발에 필요한 문서를 유지한다.

포함 기능:

- 개념 카드
- 빈칸 문제
- OX 문제
- 순서 배열
- 짝 맞추기
- 풀이 예시
- 오답 맞춤 연습
- 미니 모의고사
- `ProblemItemAnalytics`: 사용 후 문항 통계 저장
- 시도 수, 정답률, 평균 점수, 선택지 분포, 오답 유형 분포 추적
- 제출 시 `elapsed_time_sec`, `hint_count`를 받아 평균 풀이 시간과 힌트 사용률 추적
- `sample_size_status`, `statistics_confidence`, `correct_rate_smoothed`로 초기 통계 과신 방지
- 초기에는 사용 통계보다 `professor_grade_score.final_score` 기반 문항 자체 품질을 우선
- 작동하지 않는 오답 보기와 자주 빠지는 rubric 기준 감지
- 재검토 필요 문항 표시
- 같은 사용자와 같은 자료에서 이미 만든 문제는 다시 저장하지 않도록 기존 문제 signature를 비교
- `ProblemRegenerationCandidate`: 통계가 나쁜 문항을 재생성 후보로 등록
- `ProblemTemplateAnalytics`: 같은 사용자/자료 안에서 유사 문항 템플릿 단위 통계 저장
- `UsageLedger`: LLM 호출별 모델, 토큰, 예상 비용 기록
- 사용량 summary는 목록 조회 limit에 묶이지 않고 SQL aggregate로 전체 기간을 합산
- `GET /api/problems/{problem_id}/analytics` 문항 통계 조회 API
- `GET /api/problem-analytics` 사용자별 문항 통계 목록 API
- `GET /api/problem-template-analytics` 사용자별 문항 템플릿 통계 목록 API
- `GET /api/problem-regeneration-candidates` 재생성 후보 목록 API
- `GET /api/usage-ledger` 사용자별 LLM 사용량 조회 API
- eval fixture
- OpenAI live smoke test
- API 비용 제한 설정
- 제품 품질 기준 문서: [docs/problem-feedback-quality-application-plan.md](docs/problem-feedback-quality-application-plan.md)
- UI 목적 문서: [docs/problem-feedback-system-flow.md](docs/problem-feedback-system-flow.md)

완료된 판단:

- 오답 맞춤 콘텐츠, 미니 점검 문제, 문항 통계, 템플릿 통계, 비용 원장, 재생성 후보 조회 API까지 구현했다.
- 실제 PDF 파일 파싱과 Vector DB 내부 검색/저장은 김태훈 파트 담당이므로, 우리 파트에서는 `SearchService` 계약, generated artifact outbound 계약, 고정 chunk 기반 통합 테스트로 검증한다.
- OpenAI live smoke test는 `pytest -m llm`로 분리되어 있으며, API key와 결제 한도가 있는 환경에서만 실행한다.
- 프론트엔드 연동은 README와 API response schema 기준으로 진행한다.

Phase 7로 넘긴 외부 통합 확인:

- 실제 김태훈 RAG 서버를 띄운 상태에서 `/search` end-to-end 테스트
- 실제 PDF 업로드부터 RAG 색인, 문제 생성, 제출, 피드백까지 전체 플로우 테스트
- 통합 서버에서 document/tutor 파트와 router 충돌 여부 확인

검증:

```bash
.venv/bin/python -m pytest \
  tests/test_learning_content_contracts.py \
  tests/test_learning_content_agent.py \
  tests/test_learning_content_service.py \
  tests/test_learning_content_api.py \
  tests/test_eval_runner.py \
  tests/test_problem_template_analytics.py \
  tests/test_usage_ledger.py \
  tests/test_problem_feedback_service.py \
  -q
```

## Phase 6. 평가 루프 차별화

상태: DONE

목표:

- 단순 “자료 기반 문제 생성”이 아니라, **오답을 줄이는 시험 대비 훈련 시스템**으로 만든다.
- 사용자가 푼 결과를 바탕으로 문제 품질, 피드백, 후속 문제, 복습 우선순위가 계속 좋아지게 한다.
- 네 담당 범위인 문제 생성, 채점, 피드백, 오답 개선, LLM 비용 관리 안에서만 구현한다.

포함할 기능:

### 1. 재생성 실행 루프

상태: DONE

- `ProblemRegenerationCandidate`에 쌓인 후보를 실제 새 문제 생성 요청으로 연결한다.
- 같은 문제나 너무 비슷한 문제는 다시 만들지 않는다.
- 재생성 이유를 새 문제의 metadata에 남긴다.
- 재생성 후 기존 문제와 새 문제를 비교할 수 있게 한다.
- 정답률이 너무 높을 때만 난이도와 사고 단계를 올리고, 정답률이 너무 낮을 때는 모호함과 근거 부족을 줄인다.

완료 기준:

- `POST /api/problem-regeneration-candidates/{candidate_id}/regenerate`
- 재생성 결과가 기존 문제와 다른지 검증
- 후보 상태가 `open -> resolved` 또는 `queued`로 바뀜
- 기존 문제 재탕 방지 테스트 통과

### 2. 단계형 힌트 API

상태: DONE

- 제출 전 힌트는 정답을 직접 노출하지 않는다.
- 시험 모드에서는 힌트를 막고, 연습 모드에서는 단계별 힌트를 제공한다.
- 힌트 사용량은 제출 결과와 mastery 업데이트에 반영한다.

힌트 단계:

1. 문제 다시 읽기
2. 필요한 개념 떠올리기
3. 첫 단계 질문
4. 부분 예시
5. 풀이 구조
6. 제출 후 전체 풀이

완료 기준:

- `POST /api/problems/{problem_id}/hints`
- 제출 전에는 `answer`, `correct_choice`, `full_solution`이 노출되지 않음
- `hint_count`가 제출과 통계에 반영됨
- 힌트를 많이 본 정답은 mastery 상승폭이 작아짐

### 3. 비용 원장과 모델 사용 정책

상태: DONE

- OpenAI 호출별 모델, 기능, 토큰, 예상 비용을 저장한다.
- 고급 모델을 쓴 경우 이유를 남긴다.
- 월정액 서비스에서 손익을 계산할 수 있게 한다.

완료 기준:

- `UsageLedger` 모델과 repository
- 문제 생성, 주관식 채점, 피드백 문장화의 사용량 기록
- deterministic fallback은 비용으로 기록하지 않음
- 기능별/사용자별 비용 조회 가능
- `GET /api/usage-ledger` 조회 API
- `GET /api/usage-ledger/summary` 사용자별 총 토큰, 예상 비용, 예산 상태 조회 API
- `LLM_MONTHLY_USER_BUDGET_KRW`, `LLM_BUDGET_WARNING_RATIO` 기반 `not_configured | ok | warning | exceeded` 상태 계산
- 모델 가격은 `.env`의 token당 단가 설정으로 조정 가능

### 4. 사용자 품질 신고 루프

상태: DONE

- 사용자가 “너무 쉬움”, “정답이 이상함”, “피드백이 불친절함” 같은 문제를 신고할 수 있게 한다.
- 신고는 eval fixture와 재생성 후보로 이어질 수 있어야 한다.
- 문제/피드백/학습 콘텐츠는 본인에게 노출된 대상만 신고할 수 있다.
- 문제 품질에 영향을 주는 신고는 `ProblemRegenerationCandidate`로 연결한다.
- 말투 신고처럼 문체 개선에 가까운 신고는 신고 데이터만 저장하고, 문제 재생성 후보로 만들지는 않는다.

완료 기준:

- `POST /api/quality-reports`
- 신고 사유 enum
- 본인에게 노출된 문제/피드백/학습 콘텐츠만 신고 가능
- 신고된 문제는 재검토 후보로 연결 가능

### 5. 문항 템플릿 단위 통계

상태: DONE

- 초기에는 개별 문제 통계가 부족하므로, 유사한 문항을 템플릿 단위로 묶어 본다.
- 예: `item_model_id + concept + difficulty + problem_type`
- 같은 유형에서 반복되는 실패 패턴을 찾는다.
- 사용자/문서 경계를 지키기 위해 `user_id + document_id + item_model_id + concept + difficulty + problem_type` 단위로 집계한다.
- 개별 문제 통계가 부족할 때는 템플릿 통계도 `sample_size_status`로 신뢰도를 표시한다.
- 표본이 적은 동안은 템플릿 안의 문항 자체 품질 평균을 우선 보고, 표본이 충분해지면 사용 통계를 더 반영한다.
- 템플릿 통계가 나빠지면 `template:*` 사유로 재생성 후보에 자동 연결한다.

완료 기준:

- `ProblemTemplateAnalytics`
- 개별 문항 통계와 템플릿 통계를 구분
- 표본 수가 적으면 개별 문항 품질 점수를 우선
- 표본 수가 쌓이면 템플릿 통계를 품질 개선에 사용
- `GET /api/problem-template-analytics`
- 템플릿 단위 실패 패턴이 `ProblemRegenerationCandidate`로 이어짐

### 6. 피드백 후 행동 이벤트

상태: DONE

- 피드백 이후 사용자가 실제로 어떤 행동을 했는지 저장한다.
- 다음 행동 버튼 클릭, 다시 풀기 완료, 후속 문제 완료, 도움 됐어요 평점을 기록한다.
- 피드백 이벤트는 본인 피드백에 대해서만 저장할 수 있다.
- 연결 대상 문제나 학습 콘텐츠가 있으면 본인 소유인지 확인한다.

완료 기준:

- `FeedbackActionEvent`
- `POST /api/feedback/{feedback_id}/actions`
- `GET /api/feedback/{feedback_id}/actions`
- 이벤트 payload validation
- 본인 피드백/문제/학습 콘텐츠 소유권 검증

### 7. 시험 대비 세트 준비도 판정

상태: DONE

- 문제 세트를 바로 만들기 전에 자료와 풀이 기록이 충분한지 먼저 판단한다.
- 검색 근거가 없거나 다른 문서 chunk가 섞이면 `not_ready`로 막는다.
- 일반 연습 요청에서 기록이 적으면 `diagnostic_ready`로 낮춘다.
- 반복 오답이나 낮은 mastery 기록이 있으면 `personalized_ready`로 올린다.
- 사용자가 고난도/시험 대비를 원하면 자료 양이 많지 않아도 `exam_ready`로 열어둔다.
- 단, 외부 사실을 넣지 않고 자료 안의 개념·공식·관계를 바탕으로 가능한 최고 수준까지 응용한다.
- 초기 사용자에게 개인 맞춤 세트라고 과장하지 않고, 먼저 짧은 진단 세트를 권장한다.

완료 기준:

- `POST /api/assessment-sessions/readiness`
- 자료 준비도, 풀이 기록 점수, 품질 게이트 점수 분리 반환
- 빈 검색 결과와 다른 문서 chunk 혼입 차단
- 진단/개인맞춤/시험대비 상태 분기 테스트 통과

### 8. 시험 대비 세트 실행과 재도전 추적

상태: DONE

- readiness가 가능한 경우 저장형 assessment session을 만든다.
- 세트 문제는 제출 전 정답, 해설, rubric을 숨긴다.
- 세트 단위 제출과 일부 제출 진행 상태를 지원한다.
- report에서 점수, 완료율, 풀이시간, 시간 초과 여부, 잘한 개념, 약점 개념, 개념별 결과, 다음 행동을 반환한다.
- retry endpoint로 같은 자료와 요청 조건의 새 세트를 만들고 이전 세트 대비 점수 변화를 비교한다.
- history endpoint로 원본 세트부터 다시 풀기 세트까지 attempt 목록, 최고 점수, 최신 점수 변화, 전체 trend를 반환한다.

완료 기준:

- `POST /api/assessment-sessions/generate`
- `GET /api/assessment-sessions/{session_id}`
- `POST /api/assessment-sessions/{session_id}/submit`
- `GET /api/assessment-sessions/{session_id}/report`
- `POST /api/assessment-sessions/{session_id}/retry`
- `GET /api/assessment-sessions/{session_id}/history`
- 정답 숨김, 일부 제출, 시간 제한, 개념별 리포트, retry 비교, history trend 테스트 통과

검증:

```bash
.venv/bin/python -m pytest \
  tests/test_problem_feedback_service.py \
  tests/test_problem_feedback_api.py \
  tests/test_assessment_session_readiness.py \
  tests/test_usage_ledger.py \
  tests/test_quality_report_api.py \
  tests/test_problem_template_analytics.py \
  -q
```

LLM key가 있을 때만:

```bash
OPENAI_API_KEY=... .venv/bin/python -m pytest tests/test_openai_smoke_llm.py -q -m llm
```

테스트 모델만 바꾸려면 `OPENAI_SMOKE_PROBLEM_MODEL`, `OPENAI_SMOKE_GRADING_MODEL`을 함께 설정한다.

실제 김태훈 RAG 서버가 있을 때만:

```bash
RAG_AGENT_URL=http://localhost:8000 \
RAG_SMOKE_DOCUMENT_ID=실제_문서_ID \
.venv/bin/python -m pytest tests/test_rag_agent_live_smoke.py -q -m rag
```

## 공통 검증

큰 변경 뒤에는 아래를 실행한다.

```bash
.venv/bin/python -m pytest -q
PYTHONPYCACHEPREFIX=/tmp/problem_agent_pycache .venv/bin/python -m compileall app tests
```

## 유지할 핵심 문서

- [README.md](README.md): 실행 방법과 API 테스트
- [problem-feedback-roadmap.md](problem-feedback-roadmap.md): 현재 실행 로드맵
- [docs/problem-feedback-integration-contracts.md](docs/problem-feedback-integration-contracts.md): 팀 연동 계약
- [docs/problem-feedback-system-flow.md](docs/problem-feedback-system-flow.md): 전체 흐름
- [docs/problem-feedback-quality-application-plan.md](docs/problem-feedback-quality-application-plan.md): 제품 품질 기준
- [docs/problem-feedback-human-tone-strategy.md](docs/problem-feedback-human-tone-strategy.md): 사용자 문체 기준
- [docs/problem-feedback-shared-server-integration.md](docs/problem-feedback-shared-server-integration.md): document/tutor 파트와 같은 서버로 합칠 때의 기준
- [team-architecture-and-roles.md](team-architecture-and-roles.md): 팀 역할 경계

## Phase 7. RAG 통합 안정화

상태: IN_PROGRESS

목표:

- 김태훈 RAG Agent의 실제 응답 형태가 조금 바뀌어도 문제 생성 파트가 깨지지 않게 한다.
- Search/RAG 결과가 다른 문서와 섞이거나 빈 결과로 들어오는 상황을 명확히 차단한다.
- 생성된 문제/피드백/평가 리포트/학습 콘텐츠/학습 신호 색인 payload가 정답 유출 없이 Vector DB로 넘어갈 수 있게 유지한다.
- 생성된 문제/피드백/평가 리포트/학습 콘텐츠/학습 신호를 김태훈 Vector DB 색인 API로 전송할 수 있게 한다.

현재 구현:

- `SearchService`가 표준 Search Agent와 김태훈 RAG Agent를 모두 지원한다.
- RAG search endpoint 경로는 `RAG_AGENT_SEARCH_PATH`로 바꿀 수 있다.
- RAG chunk batch endpoint가 있으면 `RAG_AGENT_CHUNKS_PATH`로 연결할 수 있고, 없으면 cached chunk/source snapshot을 쓴다.
- Search/RAG API가 인증을 요구하면 `SEARCH_AGENT_API_KEY`, `SEARCH_AGENT_API_KEY_HEADER`로 같은 헤더를 보낸다.
- RAG 응답은 `results`, `documents`, `chunks`, `items`, `data`, `matches`, `contexts`, `nodes` 형태를 모두 받을 수 있다.
- chunk 본문은 `text`, `content`, `page_content`, `document`, `body`, nested `document.page_content` 중 가능한 값을 사용한다.
- page, source, concepts는 `metadata` 안에 있어도 변환한다.
- RAG가 `chunk_id`, `id`, `node_id`를 주면 그대로 쓰고, 없으면 안정적인 `rag_...` ID를 만든다.
- 같은 `/search` 검색 결과 안에서 중복 chunk ID는 첫 결과만 쓰고 제거한다.
- 요청한 `document_id`와 다른 결과가 오면 `SearchAgentError`로 실패한다.
- RAG 결과가 비어 있으면 문제 생성으로 넘어가지 않고 실패한다.
- 실제 서버 검증용 `tests/test_rag_agent_live_smoke.py`를 제공한다.
- `GeneratedArtifactPublisher`가 생성된 문제, 피드백, `assessment_report`, `learning_content`, `learning_signal`을 `GENERATED_ARTIFACT_INDEX_URL`로 전송한다.
- 색인 API가 인증을 요구하면 `GENERATED_ARTIFACT_API_KEY`, `GENERATED_ARTIFACT_API_KEY_HEADER`로 헤더를 보낸다.
- 색인 API 타임아웃은 `GENERATED_ARTIFACT_TIMEOUT_SECONDS` 기본 3초로 LLM 타임아웃과 분리한다.
- 문제 artifact에는 정답/해설을 넣지 않고, 피드백/학습 콘텐츠/학습 신호 artifact는 사용자별 private visibility로 보낸다.
- 평가 리포트 artifact는 총점, 완료율, 시간 초과, 강점/약점 개념, 복습 추천, 재도전 변화만 보내고 문항별 세부 결과는 보내지 않는다.
- artifact 색인 본문은 4,000자로 제한하고, 평가 리포트와 학습 신호의 개념/복습 목록은 상위 20개까지만 보내서 대량 사용자 상황의 색인 payload 크기를 제한한다.
- `problem_feedback_route_keys()`와 `find_problem_feedback_route_conflicts(app)`로 공유 서버 include 전 route 충돌을 점검할 수 있다.
- README/개발 계획/공유 서버 통합 문서가 실제 `/api/*` route를 빠뜨리면 `tests/test_integration_contracts.py`에서 실패한다.
- `AUTO_CREATE_TABLES=true`는 SQLite 데모 DB에서만 허용하고, PostgreSQL은 김태훈 DB/Vector DB 저장소 연결 없이 `create_all()`로 시작하지 못하게 막는다.

남은 작업:

- 김태훈 서버와 색인 데이터가 준비된 상태에서 `pytest -m rag` 실행
- RAG 쪽에서 안정적인 `chunk_id`를 내려줄지 최종 협의
- 생성 산출물 색인 endpoint 실제 경로 확정
- 생성 산출물 색인 API가 받을 최종 인증 헤더 이름 확정
- 실제 document/tutor 라우터가 준비된 통합 서버에서 `find_problem_feedback_route_conflicts(app)` 결과 확인

검증:

```bash
.venv/bin/python -m pytest tests/test_search_service_contract.py tests/test_generated_artifact_publisher.py -q

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

`tests/test_problem_agent_live_e2e_smoke.py`는 기본적으로 RAG 조회와 artifact write만 실제 서버로 검증하고 문제 생성은 fallback으로 돌린다. OpenAI 문제 생성까지 포함해 검증하려면 `PROBLEM_AGENT_E2E_SMOKE_USE_OPENAI=true`와 `OPENAI_API_KEY=...`를 함께 설정한다.

```bash
PROBLEM_AGENT_E2E_SMOKE_ENABLED=true \
PROBLEM_AGENT_E2E_SMOKE_USE_OPENAI=true \
OPENAI_API_KEY=... \
RAG_AGENT_URL=http://localhost:8001 \
SEARCH_AGENT_API_KEY=... \
GENERATED_ARTIFACT_INDEX_URL=http://localhost:8001/generated-artifacts/index \
GENERATED_ARTIFACT_API_KEY=... \
PROBLEM_AGENT_E2E_SMOKE_DOCUMENT_ID=실제_문서_ID \
PROBLEM_AGENT_E2E_SMOKE_CONCEPT=핵심_개념 \
.venv/bin/python -m pytest tests/test_problem_agent_live_e2e_smoke.py -q -m llm
```

## 다음 발전 우선순위

1. **RAG 실제 end-to-end 테스트**: 김태훈 RAG 출력으로 문제 생성, 제출, 피드백, 통계 업데이트까지 한 번에 확인한다.
2. **김태훈 DB/Vector DB 저장 계약 확정**: generated artifact 색인 endpoint, 인증 헤더, chunk batch 조회 방식을 실제 서버 기준으로 고정한다.
3. **통합 서버 패키지 정리**: `document_agent`, `tutor_agent`, `problem_agent`를 같은 서버에 올릴 때 `app` 패키지 충돌을 제거한다.
