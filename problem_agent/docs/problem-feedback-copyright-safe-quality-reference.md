# 저작권 안전 문제 품질 레퍼런스 전략

목표는 실제 출제자가 만든 것처럼 응용력과 진단력이 있는 문제를 만들되, 기출문제나 상업 문제은행의 표현을 복사하거나 모델 학습 자료처럼 쓰지 않는 것이다.

## 원칙

- 좋은 문제의 **원칙**만 참고한다.
- 실제 문제의 문장, 보기, 해설, 수치, 지문 구성은 저장하지 않는다.
- eval fixture는 모두 우리 자료 chunk와 새로 만든 가상 상황으로 작성한다.
- 외부 문제를 프롬프트에 그대로 넣어 변형 생성하지 않는다.
- 문제 품질 기준은 문항 작성 가이드에서 추상화한 체크리스트로만 반영한다.
- 상업 서비스에서는 출처 권리가 확인된 공개/허가 자료가 아니면 수집하지 않는다.

## 허용

- 공개 문항 작성 가이드에서 품질 기준 추출
- “좋은 distractor는 오개념을 겨냥해야 한다” 같은 추상 규칙 사용
- “stem만 보고도 무엇을 묻는지 알 수 있어야 한다” 같은 구조 규칙 사용
- 가상의 표, 숫자, 사례를 직접 만들어 eval로 추가
- 공개 라이선스가 명확한 자료라도 원문 문제 복제가 아니라 새 문항 생성 검증에만 사용

## 금지

- 기출문제, 학원 문제, 문제은행 문항을 그대로 저장
- 보기나 해설을 일부만 바꾼 유사 문항 생성
- 저작권 있는 문제를 LLM prompt에 넣고 “비슷하게 만들어줘”라고 지시
- 출처와 라이선스가 불명확한 문제를 eval fixture에 포함
- 경쟁 서비스의 문제 스타일을 문장 단위로 모방

## 품질 기준으로 추상화할 항목

- 학습 목표나 평가 주장과 직접 연결된다.
- stem은 모호하지 않고, 불필요한 정보가 적다.
- 고난도 문제는 조건, 비교, 계산, 오류 탐지, 근거 선택 중 하나 이상을 요구한다.
- 객관식은 정답 하나가 명확하고, 오답은 실제 오개념이나 실수 경로와 연결된다.
- 보기는 길이, 문법, 형식이 지나치게 다르지 않아야 한다.
- “모두 정답”, “정답 없음”, 너무 절대적인 표현은 기본적으로 피한다.
- 주관식은 rubric이 관찰 가능한 답안 근거를 기준으로 나뉜다.
- 피드백은 점수 설명보다 다음 행동을 먼저 떠올릴 수 있게 한다.
- 일반 사용자는 부담 없는 존댓말, 짧은 문장, 구체적 다음 행동을 받는다.

## 구현 방식

1. 외부 공개 가이드는 `quality_reference_note`로만 요약한다.
2. 코드에는 출처 문장을 넣지 않고 규칙 이름만 남긴다.
3. eval은 실제 문제가 아니라 새 자료 chunk와 새 candidate로 만든다.
4. invalid case에는 왜 나쁜 문제인지 `expected_error_substrings`를 둔다.
5. 상업 배포 전에는 문제 생성 결과의 원문/외부 문제 overlap 샘플 검사를 별도 운영 QA로 둔다.

## 모델 라우팅 기준

기본 문제와 고난도 문제는 같은 생성 모델로 처리하지 않는다. 품질과 비용을 함께 보려면 아래처럼 나눈다.

- 기본 개념 확인, 일반 객관식, 짧은 주관식은 비용 효율 모델을 사용한다.
- 고난도, 시험 대비, `target_rigor=high`, `depth=deep`, `hard`, `analyze/evaluate/create` 요청은 상위 문제 생성 모델을 사용한다.
- 상위 모델을 쓰더라도 실제 문제나 문제은행 문항을 프롬프트에 넣어 모방시키지 않는다.
- 모든 tier에서 `ProblemQualityChecker`, item model별 검증, rubric dry-run, source grounding 검증을 공통으로 통과해야 한다.
- 비용 절감은 고난도 모델을 낮추는 방식보다 후보 수, 재시도 횟수, 자료 부족 사전 차단으로 조절한다.

## UI 기반 생성 정책

사용자가 직접 프롬프트를 작성하게 하지 않는다. 프론트는 아래 선택지만 제공하고, 백엔드는 이를 `GenerateProblemRequest`로 변환한다.

- 문제 형식: 객관식, 주관식
- 난이도: 쉬움, 보통, 어려움
- 목적: 개념 확인, 시험 대비, 약점 보완
- 깊이: 기본, 심층
- 문제 스타일: 개념 확인, 시험형 응용, 계산 연습, 오개념 훈련, 근거 분석, 오류 찾기
- 문제 수: 요금제 한도 안에서 선택
- 개념: 검색된 자료/목차에서 고르는 chip

프론트는 이 선택을 `problem_style` enum으로 보낸다. `user_requirements`는 내부 preset이나 제한된 UI 옵션을 문장으로 바꾼 값만 넣는다. API로 직접 들어온 `user_requirements`에 시스템 프롬프트, 이전 지시 무시, 탈옥, prompt injection 계열 문구가 있으면 생성 전에 거부한다.

문제 형식을 늘릴 때는 별도 구현 단위로 다룬다. 퀴즈, OX, 빈칸, 매칭, 순서 배열, 미니 시험은 사용자가 흥미를 잃지 않게 하는 데 좋지만, 각 형식마다 저장 schema, 결정적 채점, 품질 검증, 피드백 계약이 완성되어야 한다. 이 중 일부는 이미 `LearningContentType`과 `mini_exam` 흐름으로 분리되어 있으므로, `ProblemType`에 어설프게 추가하지 않는다.

형식 선택은 사용자에게 맡기기보다 자료 기반 추천을 기본값으로 둔다. 조유찬 파트가 chunk에 붙인 `tags`, `metadata`, `concepts`와 우리 쪽 `LearningTaskStrategyRouter`가 감지한 `content_forms`를 합쳐 즉시 추천한다. 예를 들어 수식/그래프 중심 자료에는 풀이 예시, 빈칸, OX를 먼저 추천하고, 절차나 시간 흐름이 뚜렷하지 않으면 순서 배열은 우선 추천하지 않는다. 다만 추천은 사용자 경험을 돕는 장치이지 과도한 차단 정책이 아니다. 직접 생성 가능한 형식은 만들 수 있으면 만들고, UI에서 추천 순서와 안내 문구로 자연스럽게 유도한다.

## 남용 방지 한도

- `PROBLEM_GENERATION_MONTHLY_LIMIT`: 사용자별 월 전체 문제 생성 수
- `PROBLEM_GENERATION_HIGH_RIGOR_MONTHLY_LIMIT`: 사용자별 월 고난도/심층/시험형 문제 생성 수
- `LLM_MONTHLY_USER_BUDGET_KRW`: 사용자별 월 LLM 예산
- `LLM_ENFORCE_MONTHLY_BUDGET`: 예산 초과 시 새 문제 생성, LLM 기반 피드백, LLM 기반 학습 콘텐츠 생성 차단 여부

요금제에서는 문제 생성 횟수를 무제한으로 열지 않는다. 객관식 기본 채점, 저장된 문제 복습, 오답노트 조회처럼 비용이 거의 없는 기능은 넓게 열고, 새 문제 생성, 고난도 문제 생성, 주관식 채점, LLM 학습 콘텐츠 생성처럼 LLM 비용이 드는 경로는 별도 한도로 관리한다.

## 현재 코드 연결

- `ProblemQualityChecker`: 보기 단서, all/none 보기, 약한 rubric, 출처 부족, item model별 위반을 검사한다.
- `ProfessorGradeItemDesigner`: 문항 모델, 난이도 프로필, teacher checklist, 학생 답안 시뮬레이션을 붙인다.
- `evals/problem_generation/*.jsonl`: 새로 만든 가상 자료와 새 문항으로 고난도 검증을 수행한다.
- `LearningCopyQualityChecker`: 일반 교육 사이트에 맞는 친근한 존댓말 피드백을 검사한다.

## 참고한 공개 자료

- American College of Surgeons, Multiple-Choice Item Writing Guidelines: https://www.facs.org/for-medical-professionals/education/cme-resources/test-writing/
- NCME, Classroom Assessment Standards overview: https://www.ncme.org/community/ncme-committees/classroom-assessment/task-force-standards
- U.S. Copyright Office, Copyright and Artificial Intelligence: https://www.copyright.gov/ai/index.html
- Frontiers in Psychology, Multiple-Choice Item Distractor Development Using Topic Modeling Approaches: https://www.frontiersin.org/articles/10.3389/fpsyg.2019.00825/full
- BMC Medical Education, Rarely selected distractors in high-stakes MCQ exams: https://bmcmededuc.biomedcentral.com/articles/10.1186/1472-6920-10-85
