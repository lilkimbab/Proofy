# 문제 생성 · 피드백 고도화 심층 연구 로드맵

이 문서는 현재 구현을 바탕으로, 앞으로 무엇을 더 하면 제품 경쟁력이 커지는지 정리한 심층 연구 노트다.

핵심 결론은 단순하다.

> 우리는 “PDF에서 퀴즈를 만들어주는 기능”이 아니라, “내 자료로 시험처럼 풀고, 틀린 이유를 줄여주는 평가 루프”를 만들어야 한다.

NotebookLM, Quizlet, 범용 LLM은 이미 자료 기반 요약, 퀴즈, 플래시카드, 질의응답을 제공한다. 따라서 우리 파트의 차별점은 콘텐츠 종류가 아니라 아래 흐름에 있어야 한다.

```text
자료 근거
→ 평가 설계
→ 문제 생성
→ 답안 제출
→ 기준별 채점
→ 오답 원인 진단
→ 맞춤 후속 문제
→ 해결 여부 추적
→ 다음 출제와 mastery 업데이트
```

## 1. 현재 구현의 위치

이미 잘 되어 있는 부분:

- 자료 chunk 기반 문제 생성
- 제출 전 정답/해설 숨김
- 객관식 코드 채점
- 주관식 rubric 기반 채점
- `evaluation_details.rubric_results` 기반 기준별 채점 결과
- `ItemDesignBrief`
- `TeacherReviewChecklist`
- `ProfessorGradeItemScore`
- `StudentResponseSimulationReport`
- 문항 통계와 템플릿 통계
- 재생성 후보 관리
- 사용자 품질 신고
- UsageLedger 기반 비용 기록
- RAG Agent 호환 어댑터
- 생성 문제/피드백 Vector DB 전송 준비

아직 더 키울 수 있는 부분:

- 실제 RAG 자료 기반 고난도 문제 품질 검증
- 시험 대비 문제 세트 설계
- 오개념 단위의 장기 추적
- confidence 기반 학습 상태 분류
- 피드백 이후 행동 추적
- 복습 문제 예약 큐
- 비용 대비 품질 자동 조절
- 실제 사용 데이터 기반 문항 개선

## 2. 연구 기반 제품 방향

### 2.1 Evidence-Centered Design을 더 강하게 적용

좋은 문제는 단순한 질문 문장이 아니라, “무엇을 평가할 것인지”와 “어떤 답변을 근거로 능력을 판단할 것인지”가 설계된 객체다.

Evidence-Centered Design 관점에서는 크게 아래 3가지를 명확히 해야 한다.

- Student model: 학습자가 무엇을 알고 있어야 하는가
- Evidence model: 어떤 답변/행동이 그 지식을 보여주는가
- Task model: 어떤 문제 상황이 그 증거를 끌어내는가

현재 `ItemDesignBrief`가 이 방향을 일부 구현하고 있다. 다음에는 이를 더 명시적으로 강화할 수 있다.

추가하면 좋은 필드:

```json
{
  "student_model_claim": "학습자는 수요 증가가 균형가격 상승 압력을 만든다는 관계를 설명할 수 있다.",
  "evidence_rules": [
    "수요 증가와 가격 상승을 원인-결과로 연결한다.",
    "공급 조건이 고정되어 있다는 조건을 언급한다."
  ],
  "task_constraints": [
    "자료에 없는 시장 사례를 임의로 만들지 않는다.",
    "정답이 단순 정의 암기로 풀리지 않게 한다."
  ],
  "valid_response_features": [
    "원인-결과 순서",
    "조건 해석",
    "자료 근거"
  ]
}
```

제품 효과:

- 문제 생성이 더 일관된다.
- 주관식 채점이 “느낌”이 아니라 설계된 근거에 따라 돌아간다.
- 사용자가 왜 감점됐는지 더 납득할 수 있다.

우선 구현:

- `ItemDesignBrief`에 `student_model_claim`, `evidence_rules`, `task_constraints` 추가
- `ProblemQualityChecker`에서 `evidence_rules`가 rubric과 연결되는지 확인
- 주관식 채점 결과에 `evidence_rule_id`를 남김

## 3. 자동 문항 생성 고도화

### 3.1 Cognitive Item Model Bank

문항 모델은 “문제를 어떤 사고 구조로 만들지”를 정하는 틀이다.

현재 item model이 이미 존재한다. 다음에는 각 model별로 더 명확한 생성 규칙과 거부 규칙을 붙이면 좋다.

예:

| item model | 좋은 사용 | 거부해야 할 경우 |
| --- | --- | --- |
| `definition_with_boundary` | 비슷한 용어 구분 | 고난도 요청인데 단순 정의만 묻는 경우 |
| `concept_comparison` | 두 개념 차이 설명 | 비교 기준이 source에 없는 경우 |
| `error_detection` | 잘못된 풀이 찾기 | 오류가 너무 노골적인 경우 |
| `case_based_application` | 새 사례 적용 | 자료 밖 배경지식이 필요한 경우 |
| `data_interpretation` | 표/수치/그래프 해석 | source에 데이터 근거가 없는 경우 |
| `misconception_contrast` | 흔한 착각 비교 | 오개념이 명확하지 않은 경우 |

추가 구현:

- `ItemModelSpec`
- `allowed_cognitive_levels`
- `required_evidence_types`
- `disallowed_patterns`
- `minimum_reasoning_steps`
- `preferred_feedback_strategy`

### 3.2 고난도 문제의 정의를 더 엄격히 하기

고난도는 문장을 어렵게 쓰는 것이 아니다. 아래 중 2개 이상이 들어가야 한다.

- 조건이 2개 이상
- 개념이 2개 이상 연결됨
- 풀이 단계가 3단계 이상
- 계산/비교/반례/오류 탐지가 필요함
- 자료의 표현을 그대로 외워서는 풀 수 없음
- 답안에서 근거를 설명해야 함

거부해야 할 고난도 문제:

- “설명하시오”만 있는 주관식
- 자료 문장을 거의 그대로 물어보는 문제
- 숫자만 바꾼 단순 대입 문제
- 정답이 여러 개 가능한 문제
- 자료 밖 지식이 있어야 풀 수 있는 문제

추가 구현:

- `cognitive_demand_score` 산식 보강
- `high_rigor_requires_transfer_or_reasoning` rule
- `simple_substitution_only` flag
- 고난도 문제 eval fixture 30개 이상 추가

## 4. 객관식 문제 품질 강화

### 4.1 4지선다가 항상 정답은 아니다

객관식은 보기가 많을수록 좋은 것이 아니다. 연구에서는 많은 distractor가 실제로는 거의 선택되지 않는 경우가 많고, 그럴듯한 오답이 2개뿐이면 3지선다가 더 나을 수 있다는 근거가 있다.

현재는 4개 보기를 기본으로 검증한다. 하지만 상업용 품질을 생각하면 아래 정책이 더 낫다.

정책:

- 기본은 4지선다
- 그럴듯한 오답이 3개 안 나오면 3지선다 허용
- filler distractor를 넣느니 보기 수를 줄인다
- 모든 오답은 misconception 또는 mistake_type과 연결한다

추가 필드:

```json
{
  "option_count_policy": "four_if_plausible_else_three",
  "distractor_function_claims": [
    {
      "choice_id": "B",
      "target_misconception": "질량이 커질수록 가속도도 커진다고 착각함",
      "why_plausible": "힘과 질량의 곱이라는 표현만 보고 관계를 반대로 해석할 수 있음",
      "repair_strategy": "같은 힘에서 질량만 바꾸는 비교 문제를 풀게 한다."
    }
  ]
}
```

품질 검증:

- 오답 선택지가 너무 짧거나 너무 길면 경고
- 정답만 전문적인 표현이면 경고
- “모두 정답”, “정답 없음”은 기본 거부
- 문법 단서로 정답이 보이면 거부
- 선택지 하나도 선택되지 않으면 non-functioning distractor 후보 등록

### 4.2 실제 선택지 분포 기반 distractor 개선

현재 문항 통계는 선택지 분포를 저장한다. 다음에는 이 데이터를 선택지 개선에 직접 써야 한다.

판단 기준:

- 오답 선택률 5% 미만: non-functioning distractor 후보
- 상위권/고득점자가 많이 고른 오답: 문항 모호성 후보
- 하위권만 많이 고른 오답: 좋은 진단형 distractor 가능성
- 정답보다 특정 오답이 더 많이 선택됨: 정답 오류 또는 stem 모호성 후보

구현 아이디어:

- `ChoiceDistractorAnalytics`
- `non_functioning_choice_ids`
- `ambiguous_choice_ids`
- `diagnostic_choice_ids`
- 재생성 후보 reason에 `non_functioning_distractor:{choice_id}` 추가

## 5. 주관식 채점 고도화

### 5.1 Rubric Evidence Grader를 더 엄격히 만들기

현재 rubric별 점수와 감점 근거를 저장한다. 다음에는 “학생 답안 근거”와 “source 근거”를 더 명확히 분리해야 한다.

필드 예:

```json
{
  "criterion_id": "crit_001",
  "criterion": "조건이 고정되었을 때 수요 증가가 가격 상승 압력으로 이어짐을 설명한다.",
  "max_points": 2,
  "awarded_points": 1,
  "evidence_from_student_answer": "수요가 늘면 가격이 변한다고 썼음",
  "evidence_from_source": "자료 3문단에서 수요 증가와 가격 상승 압력 관계를 설명함",
  "missing_point": "공급이 고정되어 있다는 조건을 언급하지 않음",
  "next_action": "조건을 먼저 쓰고, 그 다음 결과를 한 문장으로 연결해보세요.",
  "confidence": "medium"
}
```

중요한 규칙:

- 학생 답안에 없는 내용을 맞았다고 처리하지 않는다.
- source에 없는 내용을 정답 근거로 쓰지 않는다.
- OCR confidence가 낮으면 채점 confidence도 낮춘다.
- 애매한 경우 `needs_review`를 켠다.

### 5.2 애매한 주관식의 2단계 채점

모든 주관식 답안을 고급 모델로 채점하면 비용이 커진다. 대신 아래처럼 처리한다.

```text
1차 채점: 비용 효율 모델
→ 점수 경계가 명확하면 저장
→ 애매한 경우만 상위 모델 재검토
```

상위 모델 재검토 조건:

- score ratio가 pass threshold 주변
- rubric criterion 간 충돌
- confidence가 low
- OCR confidence가 낮음
- 학생이 채점 불공정 신고

효과:

- 비용 절감
- 중요한 채점만 더 정확하게 처리
- 사용자가 이의제기했을 때 재채점 루프 가능

## 6. Confidence 기반 학습 상태 분류

현재는 정답/오답과 hint_count에 더해, 학습자가 직접 표시한 `confidence_level`을 반영한다.

추가 입력:

```json
{
  "confidence_level": 1
}
```

분류:

| 결과 | 확신 | 상태 | 다음 행동 |
| --- | --- | --- | --- |
| 정답 | 높음 | secure_mastery | 더 어려운 문제 |
| 정답 | 낮음 | fragile_mastery | 비슷한 문제 1개 더 |
| 오답 | 높음 | high_confidence_misconception | 오개념 교정 |
| 오답 | 낮음 | knowledge_gap | 개념 카드/쉬운 예시 |

이 방식은 사용자가 자기 상태를 더 잘 파악하게 하고, 추천도 자연스럽다.

현재 구현:

- `SubmitAnswerRequest.confidence_level`
- `LearningState`
- `Feedback.learning_state`
- `Submission.confidence_level`
- `UserConceptStat` 업데이트에 confidence 반영
- 정답 + 낮은 확신은 `fragile_mastery`로 분류하고 mastery 상승폭을 줄인다.
- 오답 + 높은 확신은 `high_confidence_misconception`으로 분류하고 mastery 감소폭을 키운다.
- 부분 점수가 있는 오답은 `partial_understanding`으로 분류하고 감소폭을 완화한다.

예:

```text
정답 + confidence 낮음:
맞았어요. 다만 확신이 낮았다면 아직 흔들릴 수 있어요. 조건만 바꾼 문제를 하나 더 풀어보면 안정적이에요.

오답 + confidence 높음:
이건 단순 실수보다 개념 방향이 반대로 잡혔을 가능성이 있어요. 먼저 오개념 비교 문제로 한 번 짚고 갈게요.
```

## 7. Knowledge Tracing Lite

딥러닝 knowledge tracing은 데이터가 많이 필요하고 설명이 어렵다. 초기 상업 서비스에는 해석 가능한 규칙 기반 모델이 더 맞다.

추천 공식:

```text
mastery_delta =
  base_delta
  * score_ratio
  * difficulty_weight
  * cognitive_demand_weight
  * confidence_adjustment
  * hint_penalty
  * repeated_mistake_penalty
  * recency_adjustment
```

예상 weight:

```text
difficulty_weight:
  easy = 0.8
  medium = 1.0
  hard = 1.25

hint_penalty:
  0 hints = 1.0
  1-2 hints = 0.75
  3+ hints = 0.45

confidence_adjustment:
  correct + high confidence = +10%
  correct + low confidence = -30%
  wrong + high confidence = 오개념 penalty 증가
  wrong + low confidence = 지식 부족으로 분류
```

추가 저장:

- `last_practiced_at`
- `last_mastery_delta`
- `learning_state`
- `repeated_mistake_count`
- `remediation_success_count`
- `remediation_failure_count`

주의:

- 숫자는 처음부터 완벽할 수 없다.
- 초기에는 사람이 이해할 수 있는 규칙으로 시작하고, 데이터가 쌓이면 보정한다.

## 8. 복습 문제 예약 큐

오답이나 낮은 confidence는 곧바로 다음 문제뿐 아니라 “나중에 다시 풀 문제”로 이어져야 한다.

추가 모델:

```json
{
  "review_item_id": "review_001",
  "user_id": "user_001",
  "concept": "수요와 공급",
  "source_problem_id": "problem_001",
  "mistake_type": "concept_misunderstanding",
  "due_at": "2026-05-10T09:00:00Z",
  "priority": 0.82,
  "interval_days": 2,
  "review_count": 1,
  "status": "due"
}
```

우선순위:

- 높은 확신 오답
- 반복 오답
- 고난도 핵심 개념
- 최근 시험 대비 세트에서 틀린 개념
- 주관식 rubric에서 반복 누락된 기준

정책:

- 맞으면 interval 증가
- 틀리면 interval 감소
- 같은 mistake_type이 반복되면 priority 증가
- 너무 많은 review가 쌓이면 핵심 개념만 압축

## 9. 시험 대비 문제 세트 생성기

사용자는 “문제 하나”보다 “시험 대비용으로 쓸 만한 세트”를 원할 가능성이 높다.

현재 API:

```text
POST /api/assessment-sessions/readiness
POST /api/assessment-sessions/generate
GET  /api/assessment-sessions/{session_id}
POST /api/assessment-sessions/{session_id}/submit
GET  /api/assessment-sessions/{session_id}/report
POST /api/assessment-sessions/{session_id}/retry
GET  /api/assessment-sessions/{session_id}/history
```

세트 생성 기준:

- 사용자가 요청한 시간
- 문제 수
- 난이도 분포
- 개념 coverage
- 약점 개념 포함
- 새 문제 비율
- 주관식/객관식 비율
- 예상 풀이 시간
- 고난도 transfer 문제 포함 여부

결과 리포트:

```json
{
  "score": 72,
  "strong_concepts": ["기본 정의"],
  "weak_concepts": ["조건 해석", "원인-결과 연결"],
  "repeated_mistakes": ["term_confusion"],
  "next_plan": [
    "조건 해석 문제 2개",
    "오개념 비교 문제 1개",
    "주관식 답안 다시 쓰기 1개"
  ]
}
```

차별점:

- NotebookLM식 quiz보다 실제 시험 연습에 가깝다.
- 제출 후 분석 리포트가 User Model로 이어진다.
- 후속 문제 생성과 복습 큐까지 연결된다.

## 10. 비용 대비 품질 최적화

### 10.1 모델 라우팅

현재 설정은 방향이 좋다. 다음에는 더 세밀하게 라우팅한다.

추천:

| 작업 | 기본 모델 | 상위 모델 조건 |
| --- | --- | --- |
| 일반 객관식 생성 | mini | 품질 gate 반복 실패 |
| 고난도/시험형 문제 생성 | quality model | 기본값으로 상위 모델 사용 |
| 객관식 채점 | 코드 | 사용 금지 |
| 객관식 피드백 | nano/템플릿 | 문체 rewrite 필요 |
| 주관식 채점 | mini | low confidence, 이의제기, 경계 점수 |
| 품질 judge | mini/코드 | 고난도 최종 승인 |

### 10.2 tiered generation → quality gate → targeted retry

기본 문제와 고난도 문제는 처음부터 생성 모델을 다르게 둔다. 상업 서비스에서는 아주 저급 모델로 고난도까지 만들려고 하기보다, 기본 문제는 비용 효율 모델, 고난도·시험형 문제는 상위 모델을 쓰는 편이 품질과 신뢰도에 맞다.

```text
기본 문제: mini로 후보 생성
고난도/시험형 문제: quality model로 후보 생성
→ deterministic quality gate
→ professor_grade_score 계산
→ 통과 후보 저장
→ 실패 이유가 명확한 near-pass 후보만 같은 tier에서 targeted retry
```

절대 하면 안 되는 것:

- premium polish가 source_chunk_ids를 바꾸는 것
- 자료에 없는 외부 사실을 추가하는 것
- 문제를 완전히 새로 바꿔 evidence와 어긋나는 것

### 10.3 월정액 기준 비용 방어

운영 정책 스캐폴딩:

- 사용자별 월 예산 경고 구간: 고급 모델 사용을 줄이고 기본 모델 중심으로 생성한다.
- 월 예산 위험 구간: 고난도 요청만 premium 모델을 허용하고, 일반 요청은 mini/fallback 중심으로 처리한다.
- 월 예산 초과 구간: 새 고비용 생성은 제한하고 기존 문제 복습, 객관식 코드 채점, 저장된 피드백 조회처럼 비용이 낮은 기능을 유지한다.
- 품질 신고가 많은 경우만 예외를 허용한다.

구체적인 비율과 제한량은 지금 정하지 않는다. 수익 계산, 실제 사용자당 평균 사용량, 다른 팀 API 비용을 합쳐 계산한 뒤 `.env`에서 켠다.

프론트에 직접 “비용 초과”라고 말하지 않는다.

사용자 문구:

```text
이번에는 빠르게 풀 수 있는 문제 위주로 먼저 준비했어요. 더 깊은 문제는 이어서 따로 만들어볼게요.
```

## 11. 실제 사용자 데이터 기반 품질 개선

### 11.1 초기 통계는 조심해서 봐야 한다

시도 수가 적을 때는 정답률이 왜곡된다.

현재 `sample_size_status`, `correct_rate_smoothed`, `statistics_confidence`가 들어가 있어서 방향이 좋다.

다음에는 아래를 추가한다.

- Wilson interval 또는 Beta-binomial confidence interval
- 정답률 신뢰구간
- 선택지별 선택률 신뢰도
- user_level별 정답률

초기 판단 우선순위:

```text
1. professor_grade_score
2. teacher_review_checklist
3. LLM/code quality gate
4. smoothed correct rate
5. raw correct rate
```

### 11.2 문항 분석 지표

추가하면 좋은 지표:

- corrected item-total correlation 대체값
- discrimination proxy 개선
- average_time_sec outlier
- hint-before-correct rate
- rubric criterion miss rate
- distractor selection entropy
- non-functioning distractor ratio

재생성 조건:

- 정답률이 너무 높고 풀이 시간이 짧음: 너무 쉬움
- 정답률이 낮고 풀이 시간이 긴데 신고도 많음: 모호하거나 근거 부족
- 특정 오답이 정답보다 많이 선택됨: 정답/문항 오류 가능성
- 특정 rubric 기준이 거의 항상 빠짐: 문제 요구사항이 불명확할 수 있음

## 12. RAG와 결합할 때 추가할 것

### 12.1 answer leakage 방지

Vector DB에 문제, 피드백, 해설까지 들어가면 검색 중 정답이 노출될 수 있다.

필수 metadata:

```json
{
  "artifact_type": "problem",
  "visibility": "hidden_until_attempted",
  "contains_answer": false,
  "contains_explanation": false,
  "user_id": "user_001",
  "document_id": "doc_001"
}
```

검색 목적별 필터:

| purpose | 허용 | 차단 |
| --- | --- | --- |
| problem_generation | concept, source chunk | answer, solution, feedback |
| hint | concept, source chunk | correct_answer, full_solution |
| feedback_generation | source chunk, target problem rubric | 다른 문제 정답 |
| tutoring | concept, summary | hidden answer |

### 12.2 generated artifact indexing

생성 문제와 피드백을 Vector DB에 넣는 것은 좋지만, 반드시 private/user scoped여야 한다.

원칙:

- 문제 artifact: 정답/해설 제외
- 피드백 artifact: private
- source_refs 유지
- user_id 필수
- document_id 필수
- schema_version 필수
- 삭제 요청 시 추적 가능해야 함

## 13. 저작권과 데이터 정책

사용자가 올린 자료를 기반으로 개인 문제를 만드는 것은 제품적으로 필요하다. 다만 리스크를 줄이려면 아래 원칙이 필요하다.

금지:

- 업로드 자료를 공용 문제 은행에 섞기
- 다른 사용자 문제 생성에 재사용
- 모델 학습 데이터로 사용
- 원문 문장을 길게 그대로 복제한 문제 생성
- 해설에 원문을 길게 붙여넣기

허용 방향:

- 사용자 본인의 학습 세션 안에서만 사용
- source_refs와 evidence_snapshot은 검증용으로만 저장
- 문제는 원문 표현보다 개념 관계와 사고 과정을 평가하도록 재구성
- 삭제 요청 시 generated artifact도 함께 삭제할 수 있게 metadata 유지

## 14. 구현 우선순위

### P0. 바로 다음에 하면 좋은 것

1. 실제 RAG end-to-end test set 만들기
2. 시험 대비 문제 세트 blueprint 설계
3. confidence 기반 피드백 문체 분기 강화
4. 피드백 행동 이벤트와 remediation 결과 연결
5. 실제 사용 데이터로 mastery delta 보정

이 5개는 제품 방향과 바로 연결된다.

### P1. 데이터가 조금 쌓이면 할 것

1. 오개념 그래프
2. 복습 문제 예약 큐
3. choice distractor analytics
4. 비용 기반 premium polish 정책
5. 주관식 2단계 채점

### P2. 사용자가 늘어난 뒤 할 것

1. IRT/CAT 기반 adaptive testing
2. 문항 노출 제어
3. user cohort별 난이도 보정
4. fairness/DIF 점검
5. 교사용 item review dashboard

## 15. 다음 구현 후보 3개

### 후보 A. 피드백 후 행동 이벤트

가장 작고 효과가 크다.

추가:

- `FeedbackActionEvent`
- `next_action_clicked`
- `retry_completed`
- `followup_problem_completed`
- `helpful_rating`

테스트:

- 오답 피드백에는 다음 행동이 있음
- 다음 행동 클릭이 이벤트로 저장됨
- 후속 문제 완료 이벤트가 저장됨

현재 구현:

- `POST /api/feedback/{feedback_id}/actions`
- `GET /api/feedback/{feedback_id}/actions`
- 본인 피드백에 대해서만 이벤트 저장 가능
- `target_problem_id`, `target_content_id` 소유권 확인
- 도움 됐어요 평점과 후속 문제 완료 여부 저장 가능
- 후속 문제 완료 이벤트가 연결된 `MistakeRemediationEvent` 해결 여부를 갱신함

다음 보강:

- 피드백 문체 variant별 다음 행동 클릭률을 비교한다.

### 후보 B. Assessment Session

시험 대비 제품성에 가장 직접적이다.

현재 적용:

- `POST /api/assessment-sessions/readiness`
- `POST /api/assessment-sessions/generate`
- 자료 준비도, 풀이 기록, 품질 게이트 점수를 분리해서 판단
- `not_ready`, `diagnostic_ready`, `personalized_ready`, `exam_ready` 상태 반환
- 일반 연습 요청에서는 초기 사용자는 진단 세트부터 권장하고, 데이터가 쌓인 뒤 개인 맞춤 세트로 올림
- 고난도/시험 대비 요청은 자료 양이 적어도 막지 않고, 근거 안에서 가능한 최고 수준의 응용 세트로 안내함
- readiness 응답에 `recommended_blueprint`로 문제 수, 개념 분포, Bloom 수준, 전략, 필요한 근거를 함께 반환함
- readiness 응답에 `coverage_report`로 요청 개념 coverage, 예상 난이도/문제 유형/Bloom 분포, 예상 풀이 시간을 함께 반환함
- 세트 생성 endpoint는 readiness 통과 후 저장형 session을 만들고 정답·해설·rubric이 숨겨진 문제 세트를 반환함
- 저장형 session, 세트 단위 submit, 일부 제출 진행 상태, report endpoint로 완료율, 점수 비율, 총 풀이시간, 시간 초과 여부, 잘한 개념, 약점 개념, 개념별 결과, 다음 행동을 반환함
- retry endpoint로 새 세트를 만들고 이전 세트 대비 점수 변화와 개념별 점수 변화를 반환함
- history endpoint로 원본 세트부터 다시 풀기 세트까지의 attempt 목록, 최고 점수, 최신 점수 변화, 전체 trend를 반환함

테스트:

- 요청 시간과 문제 수에 맞는 세트 생성
- 개념 coverage 계산
- 고난도 요청 시 단순 recall 비율 제한
- 세트 단위 제출 후 완료율, 점수 비율, 약점 개념 리포트 반환

### 후보 C. Feedback Action Event

학습 효과 측정에 필요하다.

추가:

- 피드백 다음 행동 버튼 클릭 기록
- 재시도 완료 여부
- 다음 문제 정답 여부
- helpful rating

테스트:

- 오답 피드백에는 next_action 필수
- next_action 클릭이 이벤트로 저장됨
- 후속 문제 정답이 remediation과 연결됨

## 16. 최종 판단

지금 단계에서 가장 위험한 방향은 기능을 넓히는 것이다.

예:

- 마인드맵
- 영상 요약
- 예쁜 리포트
- 일반 Q&A 확장
- 범용 노트 정리 기능

이런 기능은 다른 팀 영역이거나 NotebookLM과 정면 경쟁하게 된다.

반대로 가장 강한 방향은 좁지만 깊은 평가 루프다.

```text
좋은 문제를 만들고
제출 전 답을 숨기고
답안을 기준별로 채점하고
틀린 이유를 추적하고
같은 실수를 줄이는 문제를 다시 내고
정말 나아졌는지 측정한다.
```

이 방향이면 우리 파트는 단순 “문제 생성 API”가 아니라 **자료 기반 시험 대비 평가 엔진**이 된다.

## 17. 통합 전 내부 고도화 우선순위

실제 RAG 서버와 통합하지 못하는 동안에도 발전시킬 수 있는 영역은 충분하다. 이때 핵심은 기능을 더 넓히는 것이 아니라, **현재 시스템 안에서 문제 품질과 학습 효과를 더 잘 판정하는 기준**을 만드는 것이다.

### 17.1 고난도 eval set을 계속 확장한다

현재 `high_rigor_realistic_materials.jsonl`은 대표 과목 9개를 넣은 시작점이다. 다음에는 과목명을 늘리는 방식보다 자료 형태별로 늘리는 것이 좋다.

추가할 eval 유형:

- 계산형: 공식 2개 이상을 연결해야 하는 문제
- 표/그래프형: 수치를 읽고 원인이나 판단까지 설명하는 문제
- 비교형: 비슷한 개념 2개를 구분하는 문제
- 오류 탐지형: 잘못된 풀이 또는 잘못된 주장 찾기
- 근거 선택형: 지문 안의 근거를 찾아 판단하는 문제
- 조건 누락형: 답이 맞아 보여도 핵심 조건이 빠진 경우 감점하는 문제
- 자료 부족형: 고난도를 요구해도 근거가 부족하면 거부하거나 제한적으로 생성하는 문제

완료 기준:

- 고난도 problem_generation eval 30개 이상
- valid case와 invalid case를 함께 둠
- invalid case에는 `expected_error_substrings`를 반드시 둠
- OpenAI 호출 없이 `tests/test_eval_runner.py`가 통과함

### 17.2 문항 모델별 품질 기준을 분리한다

현재 품질 검증은 전반적으로 강하지만, 모든 문제 유형에 같은 기준을 적용하면 한계가 있다. 예를 들어 계산형 문제와 문학 근거 선택형 문제는 “좋은 문제”의 기준이 다르다.

추가할 기준:

- `calculation`: 단위, 식, 대입, 최종값, 해석을 모두 확인
- `data_interpretation`: 표/그래프 수치 인용, 비교 기준, 결론을 확인
- `misconception_contrast`: 오답 선택지가 실제 오개념과 연결되는지 확인
- `error_detection`: 제시된 오류가 너무 노골적이지 않은지 확인
- `evidence_selection`: 선택지가 지문 근거와 직접 연결되는지 확인

효과:

- 고난도 문제를 단순히 “어렵게 보이는 문장”으로 만들지 않는다.
- 문제 유형별 실패 이유가 더 정확해진다.
- 나중에 재생성할 때 어떤 방향으로 고쳐야 하는지 명확해진다.

### 17.3 학생 답안 시뮬레이션을 eval로 만든다

현재 `StudentResponseSimulationReport` 구조는 있다. 다음에는 실제 저장 전 검증에서 더 적극적으로 써야 한다.

추가할 dry-run:

- 완전 정답 답안은 높은 점수를 받아야 함
- 부분 정답 답안은 일부 rubric만 맞아야 함
- 흔한 오개념 답안은 정답 처리되면 안 됨
- 조건 누락 답안은 감점되어야 함
- 자료 밖 근거를 쓴 답안은 감점되어야 함

완료 기준:

- 주관식 문제마다 simulated answer 3개 이상
- full_correct가 80% 미만이면 저장 거부
- misconception answer가 70% 이상이면 rubric 재검토
- condition_missing answer가 만점이면 문제/rubric 재검토

### 17.4 선택지 품질을 사용 전에도 더 강하게 본다

실제 사용자 통계가 없어도 오답 보기 품질은 어느 정도 판단할 수 있다.

추가할 사전 검증:

- 정답만 지나치게 길거나 짧은지
- 오답이 “자료에 없음”, “전혀 아님”처럼 너무 쉽게 보이는지
- 오답 2개가 사실상 같은 뜻인지
- 오답이 target misconception 없이 filler로 들어갔는지
- 그럴듯한 오답이 2개뿐이면 3지선다를 허용할지 판단

이 방향은 non-functioning distractor 연구와도 맞다. 중요한 것은 보기 수가 아니라 실제로 선택될 만한 오답의 품질이다.

### 17.5 주관식 채점 confidence를 더 보수적으로 쓴다

주관식은 실제 서비스에서 민감하다. 사용자는 “왜 2점인지”를 납득해야 하고, 시스템은 애매한 답을 과신하면 안 된다.

보강 방향:

- rubric criterion별 confidence를 저장
- 전체 confidence가 낮으면 feedback 문체도 조심스럽게 바꿈
- OCR/필기 입력 confidence가 낮으면 채점 confidence도 낮춤
- 경계 점수대는 `evaluation_details.needs_grading_review`와 `grading_review_reasons`로 상위 모델 재검토 후보 표시
- 사용자 신고 `grading_unfair`가 들어오면 재생성 후보에 feedback score, evaluation confidence, low-confidence criterion, missed criterion 맥락을 저장

### 17.6 복습 큐를 “문제 예약” 수준으로 올린다

현재 mastery와 remediation event는 있다. 다음 단계는 약점 개념을 바로 문제 예약 큐로 바꾸는 것이다.

큐 우선순위 예:

```text
반복 오답 + 확신 높음
> 반복 오답
> 낮은 mastery
> 오래 안 본 개념
> 새로 틀린 개념
```

필드 예:

```json
{
  "concept": "뉴턴 제2법칙",
  "due_at": "2026-05-10T00:00:00Z",
  "priority": 0.86,
  "reason": "high_confidence_misconception",
  "recommended_problem_type": "misconception_contrast"
}
```

효과:

- 단순 복습 추천이 아니라 다음에 어떤 문제를 내야 하는지 결정할 수 있다.
- 오답 맞춤 문제가 일회성이 아니라 학습 루프로 이어진다.

### 17.7 비용을 쓰기 전 자체 판정을 강화한다

통합이 늦어져도 LLM 비용 최적화는 내부에서 할 수 있다.

우선순위:

- 너무 짧거나 근거가 약한 chunk는 고급 모델 호출 전 차단
- 고난도 요청이라도 자료가 정의뿐이면 “근거리 응용”으로 제한
- deterministic quality gate를 먼저 통과한 후보만 상위 모델 보정
- 품질 점수가 낮은 후보를 무조건 재생성하지 않고, 실패 이유별로 수정 방향을 다르게 둠

실제 운영에서는 “모든 고난도 요청 = 고급 모델”이 아니라, **품질이 애매한 후보만 고급 모델**로 보내는 구조가 수익성에 유리하다.

### 17.8 지금 당장 구현 가치가 큰 순서

1. 문항 모델별 품질 기준 분리
2. 학생 답안 시뮬레이션 eval 강화
3. 고난도 eval 30개까지 확장
4. 주관식 criterion confidence 강화
5. 복습 문제 예약 큐
6. choice distractor 사전 품질 점수
7. 비용 기반 candidate pruning

가장 먼저 할 일은 `문항 모델별 품질 기준 분리`다. 이건 외부 서버 없이도 구현 가능하고, 고난도 문제 품질에 바로 영향을 준다.

### 17.9 저작권 안전 품질 레퍼런스 전략

실제 좋은 문제를 참고하더라도, 상업 서비스에서는 문제 문장이나 보기 자체를 수집하거나 변형해서 쓰면 안 된다. 참고 대상은 실제 문항이 아니라 공개된 문항 작성 원칙, 평가 기준, distractor 설계 원칙이어야 한다.

운영 기준:

- 상업 문제은행, 기출문제, 학원 문제는 eval fixture나 prompt에 직접 넣지 않는다.
- 공개 가이드는 “정답 단서 제거”, “오답의 오개념 연결”, “학습 목표와 문항 정렬” 같은 추상 규칙으로만 반영한다.
- 모든 eval 문제는 새로 만든 자료 chunk와 새 문항으로 작성한다.
- 고난도 문제 품질은 실제 문제 복제가 아니라 item model, rubric, source grounding, simulated answer dry-run으로 검증한다.

세부 정책은 [problem-feedback-copyright-safe-quality-reference.md](problem-feedback-copyright-safe-quality-reference.md)에 둔다.

## 참고 자료

- Evidence-Centered Design 개요: https://ebrary.net/76427/education/evidence_centered_design
- LLM 기반 자동 평가 systematic review: https://www.mdpi.com/2076-3417/15/10/5683
- LLM 기반 자동 문항 생성 리뷰: https://dergipark.org.tr/en/pub/ijate/article/1602294
- 자동 문항 생성 critical review: https://pmc.ncbi.nlm.nih.gov/articles/PMC12387605/
- AIG 품질관리 연구: https://atpoc.leibniz-ipn.de/en/research/publications/instruction-tuned-large-language-models-for-quality-control-in-automatic-item-generation-a-feasibility-study
- 객관식 distractor 분석: https://bmcmededuc.biomedcentral.com/articles/10.1186/1472-6920-9-40
- Nonfunctional distractor 분석: https://pmc.ncbi.nlm.nih.gov/articles/PMC7372664/
- 적응형 피드백과 자기조절학습: https://link.springer.com/article/10.1007/s10639-024-12510-8
- Confidence 기반 adaptive practice: https://cjlt.ca/index.php/cjlt/article/view/28768
- IRT와 adaptive testing: https://link.springer.com/chapter/10.1007/978-3-319-58689-2_5
- NotebookLM 공식 기능: https://support.google.com/notebooklm/answer/16206563
- NotebookLM flashcards/quizzes 공식 블로그: https://blog.google/technology/google-labs/notebooklm-app-quizzes-flashcards/
- OpenAI 모델 문서: https://developers.openai.com/api/docs/models
- OpenAI API 가격: https://openai.com/api/pricing/
