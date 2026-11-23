# 문제 생성 + 피드백 제품 품질 기준

이 문서는 상업 서비스 기준에서 문제 생성/피드백 품질을 관리하기 위한 최소 기준이다. 긴 연구 메모는 이 문서로 통합했다.

## 1. 제품 품질 목표

사용자는 “자료를 넣으면 바로 쓸 만한 문제와 피드백이 나온다”는 경험을 기대한다. 따라서 우리 파트는 아래 4가지를 동시에 만족해야 한다.

- **자료 기반성**: 업로드 자료 밖의 내용을 임의로 끌어오지 않는다.
- **문제 난이도**: 단순 암기형만 만들지 않고, 요청에 따라 응용/분석/계산형 문제까지 만든다.
- **피드백 품질**: 정답 여부만 말하지 않고, 헷갈린 지점과 다음 행동을 제안한다.
- **비용 통제**: 모든 요청에 고가 모델을 쓰지 않고, 필요한 경우에만 높은 모델/검증 단계를 사용한다.

## 2. 자료 기반성

모든 문제와 학습 콘텐츠는 `source_chunk_ids`를 가진다.

저장 전 거부해야 하는 경우:

- source chunk가 비어 있음
- 요청한 `document_id`가 아닌 chunk를 사용함
- 자료에 없는 수치나 조건을 만들어 냄
- 원문을 긴 문장 그대로 복제함
- 문제의 정답이 source chunk로 설명되지 않음

권장 보강:

- 문제 생성 시 실제 사용한 chunk 일부를 `evidence_snapshot`으로 저장한다.
- snapshot은 피드백 근거로만 쓰고, 다른 사용자나 공용 문제 은행에 재사용하지 않는다.

## 3. 고난도 문제 생성

사용자가 아래 뉘앙스를 말하면 고난도 출제 전략을 자동 적용한다.

- 시험 대비
- 예상 문제
- 고난도
- 수능 30번 수준
- 대학 시험형
- 여러 개념을 섞어서
- 풀이 과정이 필요한 문제

자동 적용할 전략:

- 검색 chunk 수 증가
- 후보 문제를 더 많이 만든 뒤 품질 검증으로 추림
- 단순 정의형 문제 비율 축소
- 여러 개념 연결 요구
- 계산형 자료라면 LaTeX 수식과 단계별 풀이 요구
- 주관식은 rubric과 부분 점수 기준 강화

주의:

- “고난도”가 항상 어려운 수식 문제라는 뜻은 아니다.
- 국어/법/경제/역사처럼 계산이 아닌 과목은 사례 분석, 비교, 논증, 원인-결과 판단으로 난이도를 올린다.
- 자료가 너무 얕으면 무리해서 고난도처럼 꾸미지 말고, 가능한 범위의 응용 문제로 만든다.

## 4. 문제 품질 Gate

객관식 필수 조건:

- 보기 4개
- 정답 1개
- 보기 ID 중복 없음
- 빈 보기 없음
- 정답이 보기 안에 있음
- 모든 보기에 해설 있음
- 오답 보기는 그럴듯하지만 명확히 틀려야 함

주관식 필수 조건:

- 모범 답안
- rubric
- 부분 점수 기준
- max score 계산 가능
- 채점 기준이 source chunk와 연결됨
- 제출 후 criterion별 점수, 감점 근거, 다음 행동을 `evaluation_details`로 반환함

계산형/수식형 필수 조건:

- 문제 조건이 충분함
- 단위가 명확함
- 풀이에 필요한 식을 제공하거나 자료에서 근거를 찾을 수 있음
- 답안과 풀이 과정이 서로 맞음
- 수식은 LaTeX로 표현함

## 5. 피드백 품질 기준

오답 피드백은 아래 순서를 따른다.

```text
정답 여부
헷갈린 지점
자료 기반 이유
다음 행동
```

피해야 할 문장:

- 오답입니다.
- 이해도가 부족합니다.
- 사용자의 응답을 분석한 결과
- 다음 학습을 진행하세요.

권장 문장:

- 여기서 헷갈린 건 원인과 결과의 순서예요.
- 자료에서는 A가 먼저 나오고, 그 다음 B가 이어진다고 설명해요.
- 순서를 표시하면서 다시 풀어볼까요?

모든 오답 피드백은 `recommended_review` 또는 다음 행동을 포함한다.

주관식 피드백은 총점만 보여주지 않는다. `evaluation_details.rubric_results`에 각 기준의 만점, 획득 점수, 맞은 부분, 빠진 부분, 다음 행동을 남긴다. 사용자가 “왜 이 점수인지” 납득할 수 있어야 한다.
사용자가 `grading_unfair`로 피드백을 신고하면 재검토 후보에 feedback 점수, evaluation confidence, low-confidence criterion, missed criterion 맥락을 함께 남긴다.

## 6. 문체 기준

제품 목소리:

```text
옆자리에서 같이 공부해 주는 차분하고 친근한 학습 코치
```

기본 말투:

- 존댓말
- 부드러운 해요체
- 너무 딱딱하지 않음
- 과장된 칭찬 금지
- 감정 표현은 적절히 사용

문제 본문은 실제 시험 문제처럼 간결하게 쓴다.
친근한 문체는 주로 피드백, 힌트, 다음 행동 안내에 사용한다.

## 7. 비용 최적화

기본 원칙:

- 객관식 채점에는 LLM을 쓰지 않는다.
- 객관식 피드백은 기본 템플릿으로 처리한다.
- 일반 문제 생성은 비용 효율 모델을 쓴다.
- 고난도/주관식/엄격 검증이 필요한 경우에만 상위 모델로 승격한다.
- chunk 길이와 출력 토큰 수를 제한한다.

현재 주요 설정:

```env
PROBLEM_MODEL=gpt-5.4-mini
PROBLEM_QUALITY_MODEL=gpt-5.5
LEARNING_CONTENT_MODEL=gpt-5.4-mini
LEARNING_CONTENT_QUALITY_MODEL=gpt-5.5
FEEDBACK_MODEL=gpt-5.4-nano
GRADING_MODEL=gpt-5.4-mini
GRADING_QUALITY_MODEL=gpt-5.5
LLM_CHUNK_CHAR_LIMIT=1800
LLM_MAX_OUTPUT_TOKENS_PROBLEM=2500
LLM_MAX_OUTPUT_TOKENS_LEARNING_CONTENT=1800
LLM_MAX_OUTPUT_TOKENS_FEEDBACK=900
LLM_REASONING_EFFORT_LEARNING_CONTENT=low
```

운영에서는 사용량 로그를 수집해 월정액 가격과 모델 라우팅을 조정한다.

## 8. Eval 기준

기본 테스트는 API key 없이 통과해야 한다.

Eval에서 볼 항목:

- 자료 밖 내용 생성 여부
- 정답 정확성
- 보기 품질
- 주관식 rubric 적절성
- 계산형 문제 풀이 가능성
- 피드백 문체
- 다음 행동 제안 여부
- 내부 용어 노출 여부
- JSON Schema 준수

고난도 문제 생성 품질은 `evals/problem_generation/high_rigor_realistic_materials.jsonl`로 따로 본다.

이 세트는 실제 PDF 대신 Search/RAG가 돌려줄 법한 chunk 텍스트를 사용한다. 물리, 수학, 경제, 생물, 통계, 컴퓨터과학, 문학, 정책 자료를 섞어서 단순 정의형 문제가 아닌지 확인한다.

고난도 eval 추가 기준:

- 문제 하나가 근거 chunk를 충분히 인용하는가
- 여러 개념을 함께 써야 풀리는가
- 계산형 문제는 LaTeX 수식과 풀이 가능한 조건을 갖는가
- 주관식은 rubric 항목이 충분하고 부분 점수 기준이 있는가
- 객관식 오답은 그럴듯한 오개념과 연결되는가
- 자료 밖 사실이나 원문 긴 문장 복제가 없는가
- 문제 문체가 번역투나 AI 템플릿처럼 보이지 않는가

Live LLM 테스트는 명시적으로만 실행한다.

```bash
OPENAI_API_KEY=... .venv/bin/python -m pytest tests/test_openai_smoke_llm.py -q -m llm
```

## 9. 다음 보강 우선순위

현재 기능은 “자료 기반 문제 생성 + 채점 + 피드백”까지 도달했다. 다음 발전 방향은 단순 콘텐츠를 늘리는 것이 아니라, 사용자가 실제로 더 잘 풀게 되는 평가 루프를 강화하는 것이다.

### 9.1 실제 RAG 자료 기반 end-to-end 검증

가장 먼저 해야 한다.

현재 로컬 테스트는 고정 chunk와 mock RAG로 안정성을 확인한다. 하지만 상업 서비스 품질은 실제 PDF → chunk → RAG 검색 → 문제 생성 → 제출 → 피드백까지 연결했을 때 결정된다.

해야 할 일:

- 김태훈 RAG 서버에 실제 PDF 3~5개를 색인한다.
- 같은 자료에서 쉬운 문제, 중간 문제, 고난도 문제를 각각 생성한다.
- 생성 문제마다 `source_chunk_ids`, `source_refs`, `evidence_snapshot`이 실제 chunk와 맞는지 확인한다.
- 검색 결과가 얕거나 한쪽 개념에 치우칠 때 문제 품질이 어떻게 떨어지는지 기록한다.
- 실패 사례를 eval fixture로 저장한다.

완료 기준:

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

기본 E2E smoke test는 비용을 막기 위해 fallback 문제 생성을 사용한다. OpenAI 문제 생성까지 포함한 라이브 검증이 필요하면 `PROBLEM_AGENT_E2E_SMOKE_USE_OPENAI=true`와 `OPENAI_API_KEY=...`를 추가한다.

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

### 9.2 시험 대비 세트 생성기

NotebookLM도 자료 기반 flashcard와 quiz, 난이도 조절을 제공한다. 따라서 우리 파트는 “퀴즈를 만든다”보다 “시험지처럼 풀 수 있는 세트를 설계한다”에 집중해야 한다.

추가할 개념:

- `AssessmentSessionReadiness`
- `AssessmentSessionPlan`
- `ProblemSetBlueprint`
- `ExamCoverageReport`

현재 적용한 기준:

- 자료 근거가 없거나 다른 문서 chunk가 섞이면 `not_ready`로 막는다.
- 자료는 있지만 풀이 기록이 적고 일반 연습 요청이면 `diagnostic_ready`로 보고, 개인 맞춤 세트라고 과장하지 않는다.
- 반복 오답이나 낮은 mastery가 있으면 `personalized_ready`로 올린다.
- 사용자가 고난도/시험 대비를 원하면 자료 양이 많지 않아도 `exam_ready`로 열어둔다.
- 이때 외부 사실은 추가하지 않고, 자료 안의 개념·공식·관계를 새로운 상황으로 바꾸는 응용 문제를 우선한다.
- readiness 응답의 `recommended_blueprint`는 상태에 맞는 문제 수, 개념 분포, Bloom 수준, 전략, 필요한 근거를 구조화한다.
- readiness 응답의 `coverage_report`는 요청 개념의 자료 근거 coverage, 예상 난이도/문제 유형/Bloom 분포, 예상 풀이 시간을 보여준다.
- 세트 생성 전에 `POST /api/assessment-sessions/readiness`로 이 상태를 먼저 확인한다.
- `POST /api/assessment-sessions/generate`는 readiness가 가능할 때 정답이 숨겨진 저장형 문제 세트를 생성한다.
- `POST /api/assessment-sessions/{session_id}/submit`과 `GET /api/assessment-sessions/{session_id}/report`는 세트 단위 제출, 일부 제출 진행 상태, 점수 비율, 총 풀이시간, 시간 초과 여부, 잘한 개념, 약점 개념, 개념별 결과, 다음 행동을 반환한다.
- `POST /api/assessment-sessions/{session_id}/retry`는 같은 자료와 요청 조건으로 새 세트를 만들고, 새 리포트에서 이전 점수 대비 변화와 개념별 점수 변화를 비교한다.
- `GET /api/assessment-sessions/{session_id}/history`는 여러 번 다시 풀었을 때 attempt 목록, 최고 점수, 최신 점수 변화, 전체 trend를 반환한다.

문제 세트는 아래 균형을 가져야 한다.

- 핵심 개념 coverage
- 난이도 분포
- 문제 유형 분포
- Bloom/cognitive level 분포
- 예상 풀이 시간
- 이미 생성한 문제와의 중복도
- 주관식/객관식 비율
- 개념 간 연결 문제 포함 여부

좋은 출력 예:

```json
{
  "session_goal": "시험 대비",
  "estimated_time_minutes": 25,
  "coverage": {
    "covered_concepts": ["수요", "공급", "균형가격"],
    "weak_or_missing_concepts": ["탄력성"]
  },
  "difficulty_distribution": {
    "easy": 1,
    "medium": 3,
    "hard": 2
  },
  "warnings": [
    "탄력성은 검색된 자료 근거가 부족해서 고난도 문제에서 제외했습니다."
  ]
}
```

우선순위:

1. 문제 하나의 품질
2. 문제 세트 전체의 균형
3. 사용자의 약점 반영

### 9.3 오개념 그래프

현재는 오답 유형과 약점 개념을 저장한다. 다음 단계는 같은 실수가 어떤 개념과 연결되는지 누적하는 것이다.

추가할 개념:

- `MisconceptionNode`
- `ConceptMisconceptionEdge`
- `MistakePattern`

예:

```text
수요 증가 → 가격 하락으로 착각
뉴턴 제2법칙 → 질량과 가속도를 비례 관계로 착각
미분 → 접선 기울기와 평균 변화율 혼동
```

활용:

- 오답 선택지 생성 품질 개선
- 주관식 rubric 감점 이유 누적
- 오답 맞춤 문제 생성 seed 개선
- 반복 오답 시 같은 설명을 반복하지 않고 다른 접근으로 설명

주의:

- 오개념 그래프는 Search/RAG 팀의 Vector DB와 별개로, 문제/피드백 파트의 학습 진단 데이터다.
- 개인정보나 원문 자료를 공용 그래프로 섞으면 안 된다.

### 9.4 Knowledge Tracing Lite 고도화

현재 mastery 업데이트는 테스트 가능하고 단순해서 좋다. 상업 서비스에서는 조금 더 정교해야 한다.

현재는 `confidence_level`을 선택 입력으로 받아 `secure_mastery`, `fragile_mastery`, `high_confidence_misconception`, `knowledge_gap`, `partial_understanding`으로 학습 상태를 나눈다. confidence가 없으면 기존 mastery 업데이트 규칙을 유지한다.

반영할 신호:

- 정답 여부
- 점수 비율
- 문제 난이도
- cognitive demand
- confidence_level
- hint_count
- 풀이 시간
- 반복 오답 여부
- remediation 해결 여부
- 마지막 연습 이후 지난 시간

추천 계산 방향:

```text
mastery_delta =
  score_factor
  * difficulty_weight
  * confidence_adjustment
  * hint_penalty
  * recency_adjustment
  * repeated_mistake_penalty
```

초기에는 복잡한 딥러닝 knowledge tracing보다 해석 가능한 규칙 기반 모델이 낫다. 사용자에게 “왜 복습 추천이 나왔는지” 설명할 수 있어야 하기 때문이다.

### 9.5 피드백 후 다음 행동 실험

좋은 피드백은 설명에서 끝나지 않고 행동으로 이어져야 한다.

측정할 지표:

- 피드백 후 재시도율
- 다음 문제 정답률
- 힌트 사용 후 정답률
- 같은 오답 유형 반복률
- 오답 맞춤 문제 해결률
- “도움 됐어요” 비율
- 말투 신고율

필요한 구현:

- `FeedbackActionEvent`
- `next_action_clicked`
- `retry_completed`
- `followup_problem_completed`
- `helpful_rating`

현재는 `POST /api/feedback/{feedback_id}/actions`로 이벤트를 저장하고, `GET /api/feedback/{feedback_id}/actions`로 조회할 수 있다. `followup_problem_completed`는 `target_problem_id`와 함께 들어오면 연결된 `MistakeRemediationEvent`의 해결 여부를 갱신한다. 이후 단계에서는 이 이벤트를 더 모아 “피드백이 실제로 다음 정답률을 올렸는지”까지 분석한다.

프론트 버튼 예:

- 힌트만 보고 다시 풀기
- 비슷한 문제 하나 더 풀기
- 개념 카드로 30초 복습
- 풀이 흐름 보기
- 내 답 다시 써보기

### 9.6 비용 대비 품질 최적화

가격 경쟁력을 가지려면 고급 모델을 무조건 많이 쓰면 안 된다.

추천 전략:

```text
cheap draft
→ deterministic quality gate
→ near-pass 후보만 premium polish
→ usage ledger 기록
→ 품질/비용 비교
```

적용 방식:

- 일반 문제 생성: 비용 효율 모델
- 고난도 후보 생성: 비용 효율 모델로 여러 개 draft
- 품질 기준에 거의 도달한 후보만 상위 모델로 보정
- 주관식 채점은 점수 경계가 애매할 때만 상위 모델 재검토
- 야간 eval이나 대량 품질 검사는 Batch API 사용 검토

운영에서 봐야 할 값:

- 문제 1개당 평균 원가
- 고난도 문제 1개당 평균 원가
- 주관식 채점 1회당 평균 원가
- premium 모델 호출 비율
- 품질 신고당 원가
- 월정액 사용자 1명당 평균 API 비용

### 9.7 품질 보증을 위한 field test 루프

LLM judge와 deterministic checker만으로는 최종 품질을 완전히 보장할 수 없다. 실제 사용 데이터가 들어와야 문제의 난이도, 변별도, 오답 보기 품질을 판단할 수 있다.

추가할 운영 루프:

1. 생성 전 품질 gate
2. 생성 후 내부 eval
3. 사용자 풀이 통계 수집
4. 품질 신고 수집
5. 재생성 후보 등록
6. 수정 문제와 기존 문제 비교
7. 다시 field test

초기 데이터가 적을 때는 `professor_grade_score.final_score`, `teacher_review_checklist`, `sample_size_status`를 더 신뢰하고, 시도 수가 충분해지면 실제 정답률과 오답 분포 비중을 높인다.

## 10. 연구 근거와 경쟁 분석 메모

- 검색 연습은 장기 기억과 후속 학습에 도움이 된다는 연구가 많다. 따라서 우리 서비스는 요약보다 “직접 풀기 → 회상하기 → 다시 풀기” 흐름을 강화해야 한다.
- 좋은 피드백은 효과가 크지만, 방식에 따라 긍정적일 수도 부정적일 수도 있다. 그래서 정답 여부만 말하지 않고, 목표/현재 상태/다음 행동을 구조화해야 한다.
- 자동 문항 생성은 많은 문항을 빠르게 만들 수 있지만, 품질 검증이 병목이다. 현재 `TeacherReviewChecklist`, `ProfessorGradeItemScore`, LLM judge, 사용자 신고 루프를 더 강화해야 한다.
- NotebookLM은 자료 기반 flashcard, quiz, difficulty customization을 이미 제공한다. 우리 차별점은 제출 전 정답 숨김, 기준별 채점, 오답 진단, 후속 문제, mastery 업데이트에 있어야 한다.
- OpenAI 모델 가격은 mini/nano와 flagship 사이 차이가 크다. 고급 모델은 모든 요청에 쓰지 말고, 고난도 생성 보정과 애매한 주관식 채점 재검토에 제한적으로 써야 한다.

참고:

- Hattie & Timperley, “The Power of Feedback”: https://journals.sagepub.com/doi/10.3102/003465430298487
- Retrieval practice review: https://link.springer.com/article/10.1007/s10648-021-09595-9
- Automatic item generation critical review: https://pmc.ncbi.nlm.nih.gov/articles/PMC12387605/
- LLM 기반 AIG 품질관리 연구: https://www.leibniz-ipn.de/en/research/publications/instruction-tuned-large-language-models-for-quality-control-in-automatic-item-generation-a-feasibility-study
- NotebookLM 공식 기능 설명: https://support.google.com/notebooklm/answer/16206563
- NotebookLM flashcards/quizzes 공식 블로그: https://blog.google/technology/google-labs/notebooklm-app-quizzes-flashcards/
- OpenAI 모델 선택 문서: https://developers.openai.com/api/docs/models
- OpenAI API 가격: https://openai.com/api/pricing/
