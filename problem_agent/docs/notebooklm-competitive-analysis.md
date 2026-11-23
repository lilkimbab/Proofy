# 경쟁 제품 분석과 차별화 전략

작성일: 2026-05-07

목적: NotebookLM, Quizlet, Khanmigo, Duolingo Max, 범용 AI 도구와 비교해서 우리 문제 생성 + 피드백 파트가 어디서 경쟁력을 가져가야 하는지 정리한다.

## 1. 결론

NotebookLM은 매우 강한 경쟁자다. 특히 **자료 업로드 → 자료 기반 질의응답 → 요약/학습 가이드/플래시카드/퀴즈/마인드맵/오디오 요약** 흐름은 우리가 만들려는 전체 서비스와 많이 겹친다.

Quizlet은 플래시카드, Learn, AI Practice Test 쪽이 강하다. Khanmigo는 “답을 바로 주는 AI”가 아니라 “다음 문제를 더 잘 풀게 만드는 튜터”에 가깝다. Duolingo Max는 사용자에게 보이는 말투와 즉시 피드백 경험이 강하다.

다만 NotebookLM은 기본적으로 “문서 이해와 학습 자료 변환”에 강한 제품이다. 우리가 잡아야 할 차별점은 “자료를 이해하게 해준다”가 아니라 **시험 대비 평가 루프**다.

우리가 이길 수 있는 지점:

- 사용자가 답을 제출한다.
- 객관식은 결정적으로 채점한다.
- 주관식은 rubric 기준으로 채점한다.
- 왜 틀렸는지 오답 유형을 남긴다.
- 약점 개념을 User Model에 쌓는다.
- 오답 맞춤 연습을 이어서 생성한다.
- 고난도/대학 시험 대비 문제를 자료 범위 안에서 만들고 검증한다.
- 제출 전 정답을 숨기고, 제출 후 해설을 공개한다.

따라서 우리 제품의 포지셔닝은 이렇게 가야 한다.

```text
경쟁 서비스 다수: 자료를 정리하고 퀴즈로 바꿔주는 학습 도구
우리 서비스: 자료를 바탕으로 시험처럼 풀고, 채점받고, 오답을 줄이는 학습 훈련 도구
```

## 2. NotebookLM이 제공하는 핵심 기능

공식 도움말 기준으로 NotebookLM은 다음 기능을 제공한다.

### 2.1 자료 입력

지원 source:

- PDF
- Microsoft Word
- Text, Markdown
- CSV, PowerPoint
- Google Docs, Slides, Sheets
- 웹 URL
- YouTube public video URL
- ePub
- 이미지
- 오디오 파일
- 복사한 텍스트

각 source는 최대 500,000 words 또는 업로드 파일 200MB까지 가능하다. 기본 NotebookLM은 notebook당 50 sources를 지원한다.

의미:

- 자료 입력 쪽은 NotebookLM이 매우 강하다.
- 우리 프로젝트에서 PDF/OCR/Parser/Search 파트가 약하면 사용자는 NotebookLM을 더 편하게 느낄 가능성이 높다.
- 문제 생성 + 피드백 파트만 놓고 보면 우리 담당 범위는 아니지만, 전체 제품 경쟁력에는 큰 영향을 준다.

### 2.2 자료 기반 질의응답

NotebookLM은 사용자가 올린 source를 기반으로 질문에 답하고 citation을 제공한다. 공식 FAQ에서는 답이 source에 없으면 답변하지 않는 방향이라고 설명한다.

의미:

- “자료 기반 답변” 자체는 차별점이 아니다.
- 우리도 source grounding을 기본값으로 해야 한다.
- 차별화는 citation 표시보다 더 엄격한 “근거 없는 문제 저장 거부”에서 나와야 한다.

### 2.3 학습 콘텐츠 생성

NotebookLM Studio에서는 다음 output을 만들 수 있다.

- Audio Overview
- Video Overview
- Mind map
- Report
- FAQ
- Study guide
- Briefing document
- Data table
- Flashcards
- Quizzes
- Slide decks
- Infographics

특히 flashcards/quizzes는 개수와 난이도를 조절할 수 있고, Explain 버튼으로 카드나 답변 설명을 볼 수 있다.

의미:

- 플래시카드, 퀴즈, 학습 가이드, 마인드맵은 이미 NotebookLM이 제공한다.
- 우리 학습 콘텐츠 확장은 “종류가 많다”만으로는 경쟁력이 부족하다.
- 우리 콘텐츠는 반드시 채점/피드백/User Model과 연결되어야 한다.

### 2.4 모바일 학습

NotebookLM 모바일 앱은 다음을 지원한다.

- source에 질문하기
- Audio Overview 듣기
- flashcards/quizzes 복습
- infographic/slide deck 보기
- 웹/PDF/YouTube를 NotebookLM으로 공유하기

의미:

- 이동 중 학습 UX는 NotebookLM이 강하다.
- 우리 제품이 웹 API만 있으면 체감 경쟁력이 낮다.
- 프론트에서 “오답 복습”, “짧은 점검 문제”, “힌트 보고 다시 풀기” 같은 모바일 친화 흐름이 필요하다.

## 3. 가격과 사용량 한도

공식 도움말 기준 사용량은 다음과 같다.

| 구분 | Standard | Plus | Pro | Ultra |
| --- | ---: | ---: | ---: | ---: |
| notebooks | 100/user | 200/user | 500/user | 500/user |
| sources | 50/notebook | 100/notebook | 300/notebook | 600/notebook |
| chats | 50/day | 200/day | 500/day | 5K/day |
| Audio Overviews | 3/day | 6/day | 20/day | 200/day |
| Video Overviews | 3/day | 6/day | 20/day | 200/day |
| Reports | 10/day | 20/day | 100/day | 1K/day |
| Flashcards | 10/day | 20/day | 100/day | 1K/day |
| Quizzes | 10/day | 20/day | 100/day | 1K/day |
| Mind maps | 10/day | 20/day | 100/day | 1K/day |

Google은 NotebookLM을 Google AI Plans, Google Cloud, Google Workspace와 연결한다. Google 공식 블로그에서는 NotebookLM Plus를 Google One AI Premium에 포함하고, 미국 학생에게 $9.99/month 할인도 언급했다. 최신 도움말에서는 Plus/Pro/Ultra 구조가 더 세분화되어 있으므로, 출시 가격 비교 시에는 항상 최신 Google AI Plans 가격을 다시 확인해야 한다.

의미:

- NotebookLM의 무료 한도만 해도 꽤 크다.
- 월 10,000원 상품으로 NotebookLM의 source/요약/오디오 기능을 정면으로 따라가기는 어렵다.
- 대신 우리는 “시험 대비 문제/채점/오답 루프”를 좁고 깊게 가져가야 한다.

## 4. 우리와 직접 겹치는 부분

| 영역 | NotebookLM | 우리 서비스 |
| --- | --- | --- |
| PDF/자료 업로드 | 강함 | 다른 팀 담당 |
| 자료 기반 Q&A | 강함 | Tutor Agent 담당 |
| 요약/학습 가이드 | 강함 | Document/Roadmap 파트 담당 |
| 플래시카드 | 제공 | 학습 콘텐츠로 제공 |
| 퀴즈 | 제공 | 객관식/OX/빈칸/순서/짝 맞추기 제공 |
| 마인드맵 | 제공 | 후순위 |
| 오디오/비디오 요약 | 매우 강함 | 현재 범위 아님 |
| 답안 제출 | 제한적 | 핵심 기능 |
| 객관식 코드 채점 | 명확히 드러나지 않음 | 핵심 기능 |
| 주관식 rubric 채점 | 약하거나 일반 설명 중심 | 핵심 기능 |
| 오답 유형 분석 | 약함 | 핵심 기능 |
| User Model 업데이트 | 제한적/불명확 | 팀 전체 핵심 구조 |
| 오답 맞춤 연습 | 약함 | 핵심 차별점 |
| 시험 대비 고난도 출제 | 일반 quiz 난이도 조절 중심 | 핵심 차별점으로 가져가야 함 |

## 5. NotebookLM의 강점

### 5.1 자료 입력과 생태계

Google Docs, Slides, YouTube, 웹 URL, PDF, 이미지, 오디오 등 입력 범위가 넓다. Google Drive/Workspace와 붙는 점도 강하다.

우리 대응:

- 문제 생성 + 피드백 파트가 이 영역을 직접 구현하면 역할이 겹친다.
- 대신 Search/RAG contract를 명확히 하고, 어떤 자료 입력이 들어오든 chunk만 받으면 안정적으로 동작해야 한다.

### 5.2 사용자가 바로 이해하는 결과물

Audio Overview, Study Guide, Mind Map, Infographic은 사용자에게 직관적이다. “문제를 풀기 전 자료를 이해하는 단계”에서 강하다.

우리 대응:

- 우리는 “이해한 뒤 시험처럼 확인하는 단계”로 포지셔닝한다.
- 문제/피드백 화면에서 학생이 다음 행동을 바로 하도록 만들어야 한다.

### 5.3 무료/번들 가격 경쟁력

기본 무료 한도가 크고, 유료도 Google AI Plans에 번들로 들어간다. 사용자는 별도 학습 앱보다 Google 생태계 안에서 해결하려 할 수 있다.

우리 대응:

- 가격으로 정면 승부하면 어렵다.
- 한국 학생/대학생 시험 대비, 오답노트, 주관식 채점, 자료 기반 예상문제 품질로 승부해야 한다.

## 6. NotebookLM의 약점 또는 빈틈

공식 기능을 기준으로 볼 때, 아래 부분은 우리에게 기회가 된다.

### 6.1 “문서 이해”는 강하지만 “평가 루프”는 약하다

NotebookLM의 quiz/flashcards는 복습 도구에 가깝다. 사용자가 답안을 제출하고, 채점 기준별 점수를 받고, 약점 개념이 누적되고, 다음 문제가 자동으로 바뀌는 구조는 우리 서비스가 더 강하게 만들 수 있다.

제품 방향:

- 문제 풀이 결과를 반드시 저장한다.
- mistake_type, weak_concepts, recommended_review를 누적한다.
- 다음 문제 생성에 오답 이력을 반영한다.

### 6.2 시험 대비 고난도 문제 품질을 명확히 보장하기 어렵다

NotebookLM은 quiz difficulty를 easy/medium/hard로 조절할 수 있지만, 대학 시험 수준의 “조건 적용, 계산, 비교, 논증, rubric 채점”까지 제품 구조로 보장하는지는 명확하지 않다.

제품 방향:

- `goal=exam_prep`
- `course_level=university`
- `target_rigor=high`
- `depth=deep`
- `quality_mode=strict`

이 조합을 우리 서비스의 대표 기능으로 만든다.

### 6.3 정답 공개 정책과 시험 UX

우리 서비스는 제출 전 정답/해설/rubric을 숨기고, 제출 후 공개한다. 이 구조는 실제 문제 풀이 UX에 중요하다.

제품 방향:

- 문제 조회 API에서 제출 전/후 응답 차이를 계속 엄격히 유지한다.
- 학습 콘텐츠도 제출 전 정답 숨김 정책을 유지한다.

### 6.4 한국어 교육 문체와 코칭

NotebookLM은 강력하지만 한국 학생의 시험 대비 UX에 최적화된 문체를 보장하지는 않는다. 우리는 피드백 문체를 “친근하지만 존댓말을 쓰는 교육자” 방향으로 따로 설계하고 검증하고 있다.

제품 방향:

- `LearningVoiceRenderer`
- `LearningCopyQualityChecker`
- 비난 없는 오답 피드백
- 다음 행동 제안

이 부분을 계속 강화한다.

## 7. 우리가 가져가야 할 차별화 문장

마케팅/기획에서 이렇게 말할 수 있어야 한다.

나쁜 포지셔닝:

```text
PDF를 넣으면 요약과 퀴즈를 만들어주는 AI 학습 도구
```

이건 NotebookLM과 너무 겹친다.

좋은 포지셔닝:

```text
내 자료에서 시험 문제를 만들고, 내가 푼 답을 채점해서, 다음에 무엇을 고쳐야 할지 알려주는 AI 학습 코치
```

더 구체적으로:

```text
자료를 읽어주는 AI가 아니라, 내 자료로 시험처럼 연습하고 오답을 줄여주는 AI
```

## 8. 기능 우선순위 조정

NotebookLM과 경쟁하려면 아래 기능을 먼저 해야 한다.

### 1순위: 오답 맞춤 연습 강화

이유:

- NotebookLM과 가장 덜 겹친다.
- 우리 담당인 문제 생성 + 피드백 영역에 정확히 들어맞는다.
- 상업 서비스에서 “다시 쓰게 만드는 이유”가 된다.

구현 방향:

- 객관식 오답 보기마다 `distractor_rationale`을 더 구조화한다.
- 주관식 피드백에서 rubric별 부족 요소를 저장한다.
- `mistake_drill` 생성 시 같은 개념을 다른 조건/형식으로 묻는다.

### 2순위: 시험 대비 고난도 문제 생성 품질

이유:

- 사용자가 돈을 내는 이유가 된다.
- 단순 flashcard/quiz는 NotebookLM 무료 기능과 겹친다.

구현 방향:

- high/deep/strict 요청에서 후보를 더 만들고 품질 검증으로 걸러낸다.
- 자료에 공식/조건/절차가 있으면 계산형/적용형 문제를 우선한다.
- 자료가 정의 중심이어도 근거리 응용 문제를 만들되, 외부 개념을 억지로 섞지 않는다.

### 3순위: 채점 근거 UX

이유:

- 주관식 채점은 신뢰가 핵심이다.
- 점수만 주면 사용자가 불신한다.

구현 방향:

- rubric criterion별 점수와 근거를 반환하는 schema로 확장한다.
- source reference label을 사용자 문장에 자연스럽게 넣는다.
- 낮은 confidence는 “정답/오답 확정”보다 “이 부분을 다시 확인해보자”로 안내한다.

### 4순위: 미니 모의고사

이유:

- 시험 대비 상품에 잘 맞는다.
- 하지만 구현 전에 문제 품질이 먼저 안정되어야 한다.

구현 방향:

- 5문제 단위로 시작한다.
- 개념 분포와 난이도 분포를 blueprint로 관리한다.
- 결과 후 약점 요약과 다음 연습을 제공한다.

## 9. 가격 전략에 주는 영향

NotebookLM 무료/저가 한도가 크기 때문에, 월 10,000원으로 단순 문서 요약/퀴즈 기능을 팔기는 어렵다.

대신 가격 메시지는 이렇게 가야 한다.

```text
기본 요금제: 자료 기반 문제 생성과 오답 피드백
시험 대비 팩: 고난도 예상문제, 주관식 채점, 미니 모의고사, 오답 맞춤 연습
```

NotebookLM과 다른 점을 가격표에도 드러내야 한다.

| 기능 | 기본 | 시험 대비 |
| --- | ---: | ---: |
| 일반 퀴즈/개념 카드 | 포함 | 포함 |
| 주관식 채점 | 제한 | 확대 |
| 고난도 예상문제 | 제한 | 확대 |
| 미니 모의고사 | 제한 | 포함 |
| 오답 맞춤 연습 | 기본 제공 | 고급 제공 |
| rubric 기반 피드백 | 일부 | 포함 |

## 10. 우리 코드에 반영할 체크리스트

이미 잘 잡은 것:

- source_chunk_ids 필수
- 제출 전 정답 숨김
- 객관식 코드 채점
- 주관식 rubric 채점 경로
- 오답 유형/약점 개념/recommended_review 반환
- 학습 콘텐츠 정답 숨김
- 문체 렌더러/문체 검증기
- high/deep/strict 요청 구분

더 보강할 것:

- 오답 보기 rationale을 schema 수준으로 분리
- 주관식 rubric별 점수 반환
- feedback confidence 반환
- 시험 대비 문제 세트 coverage report
- 월 credit과 고비용 기능 한도
- `gpt-5.5` 호출 한도와 자동 downgrade
- 사용자가 “NotebookLM으로도 되는 기능”과 “우리 앱에서만 강한 기능”을 UI에서 구분

## 11. 최종 판단

NotebookLM과 경쟁력은 있다. 하지만 경쟁 방식이 중요하다.

정면 승부하면 불리한 영역:

- 자료 업로드 편의성
- 문서 요약
- 마인드맵
- 오디오/비디오 요약
- Google Drive/Workspace 연동
- 무료 사용량

우리가 집중하면 이길 수 있는 영역:

- 실제 시험처럼 문제 풀이
- 정답 숨김과 제출 후 해설
- 주관식 rubric 채점
- 오답 원인 분석
- 약점 개념 누적
- 오답 맞춤 연습
- 대학 시험 대비 심층 문제
- 한국어 학습 코칭 문체

따라서 앞으로 기능 확장은 “NotebookLM처럼 더 많은 콘텐츠를 만드는 방향”이 아니라, **문제를 풀고 난 뒤 학습자가 다음 문제를 더 잘 풀게 만드는 방향**으로 가야 한다.

## 12. NotebookLM 외 경쟁 제품 분석

### 12.1 Quizlet

Quizlet은 우리가 가장 조심해야 할 직접 경쟁자다. 단순 플래시카드 앱이 아니라, 업로드한 노트나 학습 세트를 바탕으로 AI Practice Test를 만들고, 객관식/서술형 문제 유형과 시간 제한까지 설정할 수 있다. 공식 도움말 기준으로 Practice Tests는 업로드한 노트나 flashcard set을 full-length practice test로 바꾸며, 문제 수, 문제 유형, 제한 시간을 고를 수 있다.

Quizlet의 강점:

- 이미 학생들이 많이 쓰는 플래시카드/테스트 UX가 있다.
- uploaded notes, flashcard sets 기반 practice test를 제공한다.
- 객관식, written question, timer를 제공한다.
- Learn 모드가 사용자의 학습 행동을 바탕으로 더 어려운 항목에 집중한다.

우리에게 불리한 점:

- 플래시카드, OX, 기본 퀴즈만 만들면 Quizlet과 너무 겹친다.
- “시험 대비 문제를 자동으로 만든다”는 문구도 이미 Quizlet이 강하게 사용한다.

우리에게 기회가 되는 점:

- Quizlet Practice Tests는 공식 도움말상 sciences/humanities와 영어 사용 조건이 붙어 있다.
- written response 길이 제한이 있어 긴 주관식 풀이 채점에는 한계가 있을 수 있다.
- 우리가 강하게 가져갈 수 있는 부분은 한국어 자료, 긴 주관식 답안, 풀이 과정, rubric별 채점, 오답 보기별 진단, 오답 맞춤 재출제다.

따라서 Quizlet을 이기려면 “문제 종류가 많다”가 아니라 아래 메시지가 필요하다.

```text
단순 테스트 생성이 아니라, 내가 왜 틀렸는지 보고 같은 실수를 줄이는 시험 대비 훈련
```

### 12.2 Khanmigo

Khanmigo는 가장 배울 점이 많은 제품이다. Khan Academy는 최근 연구에서 AI 튜터 품질을 response latency, next-item correctness, cognitive engagement quality로 측정한다고 공개했다. 특히 학생의 최근 풀이 이력과 선행 개념 부족 신호를 제공했을 때 다음 문제 정답률이 개선되었다고 설명한다.

Khanmigo의 강점:

- 답을 바로 주기보다 학생이 생각하게 만드는 튜터 UX가 강하다.
- 학생의 최근 학습 이력과 선행 개념 부족 여부를 모델 입력으로 쓰는 방향을 검증했다.
- 빠른 응답, 비용 절감, 정확성 유지까지 같이 측정한다.
- 학습자/부모용 가격이 $4/month로 낮아 가격 기준도 공격적이다.

우리에게 불리한 점:

- “AI 튜터”라는 포지션만으로는 Khanmigo와 경쟁하기 어렵다.
- 범용 코칭 품질과 교육 브랜드 신뢰도는 Khan Academy가 강하다.

우리에게 기회가 되는 점:

- Khanmigo는 Khan Academy 콘텐츠 기반 강점이 크고, 사용자가 올린 학교 PDF/과제자료 중심 시험 대비와는 방향이 다르다.
- 우리는 특정 수업 자료에서 문제를 만들고, 실제 답안 제출과 채점 기록을 쌓을 수 있다.
- 이미 `UserConceptStat`, `choice_diagnostic`, `mistake_drill` 방향을 잡았기 때문에 Khanmigo식 “다음 문제 정답률”을 우리 지표로 삼기 좋다.

따라서 Khanmigo에서 가져올 핵심은 기능이 아니라 운영 방식이다.

- 오답 피드백 이후 다음 문제 정답률을 기록한다.
- 힌트 제공 후 정답률을 기록한다.
- 같은 개념 반복 오답이 줄었는지 본다.
- 빠른 모델과 고품질 모델을 나눠서 latency와 비용을 같이 관리한다.
- raw 대화 전체를 넣기보다, 최근 풀이 이력과 약점 개념을 짧은 구조화 신호로 넣는다.

### 12.3 Duolingo Max

Duolingo Max는 우리가 문체와 피드백 UX에서 참고할 만하다. 공식 블로그 기준으로 Roleplay와 Video Call 같은 생성형 AI 기능을 제공하고, Roleplay 후에는 정확도와 복잡도에 대한 AI 피드백과 다음에 개선할 팁을 준다. 또 AI 응답 오류를 신고하게 하고, 사람이 AI-generated content의 정확성과 tone을 계속 검토한다고 설명한다.

Duolingo Max의 강점:

- 사용자가 바로 이해하는 짧고 친근한 피드백 UX가 강하다.
- 결과 후 “어떻게 더 나아질지”를 알려주는 구조가 있다.
- AI 답변 오류 신고와 사람이 보는 품질 관리 흐름을 갖고 있다.

우리에게 기회가 되는 점:

- 우리는 언어 학습 한 분야가 아니라 사용자의 실제 자료 기반 학습이 중심이다.
- `LearningVoiceRenderer`, `LearningCopyQualityChecker`를 이미 분리했으므로, 피드백 내용과 말투 품질을 따로 검증할 수 있다.
- 교육자처럼 친근한 존댓말, 이모티콘, 다음 행동 제안은 우리 제품의 체감 품질을 크게 올릴 수 있다.

주의할 점:

- 문제 본문은 시험 문제처럼 담백해야 한다.
- 친근한 말투는 피드백, 힌트, 복습 안내에 집중한다.
- 과장된 칭찬이나 근거 없는 위로는 오히려 신뢰를 낮춘다.

### 12.4 범용 AI 도구

ChatGPT, Claude, Gemini 같은 범용 AI는 사용자가 직접 “이 자료로 고난도 문제 만들어줘”라고 요청하면 높은 품질의 문제를 만들 수 있다. 따라서 단순히 LLM으로 문제를 생성하는 것 자체는 차별점이 아니다.

범용 AI 대비 우리의 강점은 제품 구조에서 나와야 한다.

- 제출 전 정답을 숨긴다.
- 답안 제출 후에만 채점과 해설을 보여준다.
- 객관식은 LLM 없이 코드로 채점한다.
- 주관식은 rubric 기준으로 채점하고 근거를 남긴다.
- 오답 유형과 약점 개념을 저장한다.
- 다음 문제 생성에 방금 틀린 선택지와 misconception을 반영한다.
- 자료 근거가 부족하면 문제 저장을 거부한다.
- 월 비용과 고급 모델 호출을 통제한다.

범용 AI가 잘하는 일:

- 한 번에 좋은 문제를 만들어내는 생성 품질
- 다양한 과목에 대한 유연한 추론
- 긴 설명과 예시 생성

우리 제품이 더 잘해야 하는 일:

- 매번 같은 품질 기준으로 저장한다.
- 사용자가 실제로 풀고 제출하게 만든다.
- 풀이 기록을 누적해서 다음 문제를 바꾼다.
- 비용이 예측 가능한 월정액 경험을 제공한다.

## 13. 경쟁력을 높이기 위한 보강 우선순위

### 13.1 주관식 rubric 채점 근거를 더 자세히 보여주기

현재 주관식 채점은 큰 구조가 잡혀 있지만, 상업 서비스에서는 점수만으로 부족하다. 사용자는 “왜 이 점수인지”를 알아야 신뢰한다.

권장 구현:

- rubric criterion별 `max_points`, `awarded_points`, `evidence`, `missing_point`, `next_action`을 응답에 포함한다.
- 총점만 보여주지 말고, 부족한 기준 1~2개만 사용자에게 보여준다.
- 근거가 애매하면 confidence를 낮추고 단정 표현을 피한다.

차별화 효과:

- Quizlet식 written question review보다 깊어진다.
- 범용 AI 채점보다 일관성을 만들 수 있다.
- 대학 시험 대비 주관식/서술형에서 돈을 낼 이유가 된다.

### 13.2 시험 대비 문제 세트에 blueprint report 추가

고난도 문제 1개를 잘 만드는 것도 중요하지만, 시험 대비에서는 세트 품질이 더 중요하다. 사용자는 “이 문제 세트가 내 자료를 균형 있게 반영했는지”를 알고 싶어 한다.

권장 구현:

- 문제 세트 생성 결과에 `coverage_report`를 붙인다.
- 포함 필드:
  - 다룬 개념
  - 난이도 분포
  - 문제 유형 분포
  - 계산/분석/정의/비교 비율
  - 빠진 개념
  - 자료 근거가 부족해서 제외한 개념

차별화 효과:

- NotebookLM/Quizlet의 “퀴즈 생성”보다 시험지에 가까워진다.
- 학생이 “너무 쉬운 문제만 나왔다”는 불신을 줄일 수 있다.

### 13.3 오답 맞춤 문제를 제품의 대표 기능으로 만들기

이미 `choice_diagnostic`과 `mistake_drill` 방향은 잘 잡았다. 이제 이걸 UI와 API에서 전면 기능으로 만들어야 한다.

권장 구현:

- 오답 후 버튼을 “비슷한 문제 풀기”보다 구체적으로 만든다.
  - “헷갈린 선택지만 바꿔서 다시 풀기”
  - “같은 개념을 조건만 바꿔서 풀기”
  - “풀이 흐름 먼저 보고 다시 풀기”
- 다음 문제에는 이전 오답 선택지의 misconception이 반영되어야 한다.
- 다음 문제를 맞히면 `mistake_resolved=true` 같은 이벤트를 남긴다.

차별화 효과:

- NotebookLM/Quizlet과 가장 덜 겹친다.
- “틀린 뒤 바로 좋아지는 느낌”을 만들 수 있다.

### 13.4 비용과 품질을 동시에 관리하는 credit 시스템

경쟁 서비스는 무료/저가 한도가 강하다. 우리는 월정액에서 손해를 보지 않으려면 사용자별 비용 관리가 필수다.

권장 구현:

- 사용자별 월 credit 사용량 저장
- 고급 모델 호출 수 저장
- `strict/high/deep` 요청은 더 많은 credit 차감
- credit 80% 이상에서 자동 절약 모드
- credit 초과 시 기존 문제 복습/객관식 코드 채점은 유지하고, 새 고난도 생성만 제한

차별화 효과:

- 월 10,000원 또는 12,900원 요금제를 현실적으로 운영할 수 있다.
- API 비용 폭주를 막는다.

### 13.5 AI 답변 신고와 품질 개선 루프

Duolingo Max처럼 사용자가 “이 피드백이 이상해요”, “문제가 너무 쉬워요”, “자료에 없는 내용 같아요”를 신고할 수 있어야 한다.

권장 구현:

- 문제/피드백에 `report_reason` 수집 API 추가
- 이유 enum:
  - `too_easy`
  - `too_hard`
  - `not_grounded`
  - `answer_wrong`
  - `explanation_unclear`
  - `tone_awkward`
  - `copyright_concern`
- 신고된 항목은 eval set에 자동 편입할 수 있게 저장한다.

차별화 효과:

- 실제 사용자 피드백으로 문제 품질을 빠르게 개선할 수 있다.
- 상업 서비스에서 신뢰와 운영 안정성을 높인다.

## 14. 지금 코드 기준 보강 후보

아래 순서로 진행하는 것이 가장 합리적이다.

1. **주관식 rubric criterion별 점수 응답**
   - 바로 상업 품질에 영향을 준다.
   - 현재 구조와 가장 자연스럽게 연결된다.

2. **문제 세트 coverage report**
   - 시험 대비 기능의 신뢰도를 높인다.
   - 고난도 문제 품질 검증과 잘 맞는다.

3. **오답 맞춤 문제 결과 추적**
   - `choice_diagnostic` 이후 자연스러운 다음 단계다.
   - Khanmigo식 next-item correctness 지표로 발전시킬 수 있다.

4. **credit/usage ledger**
   - 상업화에서 반드시 필요하다.
   - 모든 팀 API 비용을 합쳐 관리할 기반이 된다.

5. **사용자 신고/품질 개선 루프**
   - 정답 오류, 근거 부족, 어색한 문체를 실제 데이터로 잡을 수 있다.
   - eval set을 운영 데이터로 키울 수 있다.

반대로 지금 당장 우선순위를 낮춰도 되는 것:

- 오디오/비디오 요약
- 마인드맵 고도화
- 자료 업로드/OCR 자체 구현
- 모든 과목별 전용 agent 분리
- 무제한 Q&A 챗봇 기능

이 기능들은 경쟁 서비스와 겹치거나 다른 팀 역할과 겹친다. 우리 파트는 당분간 **문제 품질, 채점 신뢰도, 오답 후 다음 행동**에 집중하는 것이 더 낫다.

## 15. 적은 API 비용으로 좋은 문제를 만드는 전략

경쟁력은 모델 이름 하나로 결정되지 않는다. 사용자가 체감하는 품질은 **문제 후보를 어떻게 만들고, 무엇을 버리고, 언제 비싼 모델을 쓰는지**에서 나온다.

### 15.1 현재 모델 비용 관점

공식 가격 기준으로 `gpt-5.5`는 `gpt-5.4-mini`보다 출력 토큰 단가가 훨씬 비싸다. 그래서 고난도 요청이 들어올 때마다 `gpt-5.5`가 문제 여러 개를 처음부터 생성하게 하면 월정액 구조가 흔들린다.

현재 코드의 좋은 점:

- 일반 문제는 `gpt-5.4-mini`를 쓴다.
- 짧은 피드백은 `gpt-5.4-nano` 또는 템플릿으로 처리할 수 있다.
- 객관식 채점은 코드로 한다.
- 품질 검증은 상당 부분 코드로 한다.
- 후보를 만들고 `ProblemQualityChecker`로 걸러낸다.

현재 코드의 비용 리스크:

- `hard` 또는 높은 Bloom level 요청은 바로 `gpt-5.5`로 간다.
- strict/high/deep 요청은 후보 수가 늘어나므로, 비싼 모델에서 출력 토큰이 커질 수 있다.
- 고급 모델 호출 이유와 원가가 아직 사용자/요청 단위로 기록되지 않는다.

### 15.2 권장 아키텍처: cheap draft, code judge, premium polish

고품질 문제 생성은 아래 3단계가 가장 현실적이다.

```text
1. cheap draft
   gpt-5.4-mini로 후보 문제를 만든다.

2. code judge
   ProblemQualityChecker가 자료 근거, 문제 구조, 중복, 단순 정의 반복, rubric 품질을 점수화한다.

3. premium polish
   좋은데 아쉬운 후보 1~2개만 gpt-5.5로 보정한다.
```

이 방식의 장점:

- 고급 모델을 모든 후보에 쓰지 않는다.
- 품질이 낮은 후보를 비싼 모델로 고치기 전에 버릴 수 있다.
- 코드 검증 점수가 남기 때문에 “왜 이 문제가 좋은지”를 설명할 수 있다.
- 월정액 비용을 예측하기 쉽다.

### 15.3 문제 유형별 비용 전략

| 문제 유형 | 기본 전략 | 고급 모델 사용 조건 |
| --- | --- | --- |
| 객관식 개념 확인 | mini 생성 + 코드 검증 | 거의 사용하지 않음 |
| 객관식 응용/계산 | mini 후보 여러 개 + 코드 랭킹 | 후보가 모두 단순하거나 계산 근거가 약할 때 |
| 주관식 일반 | mini 생성 + rubric 검증 | rubric이 너무 얕거나 source 근거가 약할 때 |
| 주관식 심층/대학 시험 | mini로 skeleton 생성 후 필요 시 gpt-5.5 보정 | 최종 저장 후보 1~2개만 |
| 오답 맞춤 문제 | 기존 오답 진단 seed + mini 생성 | 반복 오답인데 해결률이 낮을 때 |
| 피드백 문체 | renderer/템플릿 우선 | 사용자 신고가 많은 문체만 보정 |

### 15.4 Gemini/Claude를 바로 붙일지에 대한 판단

Google Gemini 계열은 Flash/Flash-Lite가 매우 저렴한 편이라 대량 후보 생성에는 매력적이다. Claude Haiku도 빠르고 안정적인 선택지다. 다만 지금 당장 여러 provider를 붙이면 다음 문제가 생긴다.

- Structured Outputs 호환 방식이 provider마다 다르다.
- 품질 평가 기준을 다시 맞춰야 한다.
- 운영 장애 지점이 늘어난다.
- 팀원이 실행해야 할 환경 변수가 늘어난다.

따라서 지금 당장 provider를 늘리는 것보다, 먼저 OpenAI 안에서 아래를 완성하는 편이 낫다.

- mini 후보 생성
- code judge 점수화
- 고급 모델 호출 제한
- token/원가 기록
- eval set으로 품질 비교

그 다음 Gemini Flash-Lite 또는 Claude Haiku를 “후보 생성 전용 provider”로 A/B 테스트하는 것이 안전하다.

### 15.5 비용 절감을 위한 prompt 설계

OpenAI prompt caching은 같은 prefix가 반복될 때 입력 비용과 latency를 줄일 수 있다. 따라서 prompt는 아래처럼 구성한다.

```text
고정 지시문
JSON schema 요약
문체/품질 규칙
---
요청값
retrieved chunks
```

즉, 매번 달라지는 chunk와 사용자 요청은 뒤로 보내고, 변하지 않는 규칙은 앞에 둔다. 현재 `ProblemAgent`는 긴 규칙이 prompt 앞쪽에 있어 이 방향과 잘 맞는다. 다만 품질 규칙이 계속 길어지면 mini 모델에서도 입력 비용이 커질 수 있으므로, 다음 보강에서는 규칙을 “기본 규칙”과 “고난도 전용 규칙”으로 나누는 것이 좋다.

### 15.6 비용을 낮추면서 품질을 올리는 핵심 지표

상업화에서는 감으로 모델을 바꾸면 안 된다. 아래 지표를 봐야 한다.

- mini 후보 통과율
- 문제 1개 저장당 평균 API 원가
- `gpt-5.5` 보정 전후 품질 점수 차이
- 고급 모델 호출 후 실제 사용자 정답률/재시도율 변화
- 문제 신고율
- “너무 쉬워요” 신고율
- 오답 맞춤 문제 후 다음 문제 정답률
- 캐시 입력 token 비율
- batch/flex 사용 비율

특히 `gpt-5.5` 보정 후에도 사용자 성과가 크게 좋아지지 않는 유형은 mini로 내려야 한다. 반대로 주관식 심층 채점처럼 신뢰도가 중요한 영역은 고급 모델 사용을 유지하되 월 한도를 둔다.

### 15.7 다음 구현 방향

다음 phase는 기능 확장보다 **비용 대비 품질 최적화**가 좋다.

권장 phase:

```text
비용 대비 고품질 생성 최적화
```

포함할 작업:

1. 모델 호출 원가 추정 기록
2. 고급 모델 호출 이유 기록
3. `hard` 요청도 mini 후보 생성부터 시작하도록 라우팅 수정
4. 품질 통과 후보가 부족할 때만 premium polish 실행
5. 문제 세트별 coverage report 반환
6. mini-only vs premium-polish eval 비교

완료 기준:

- 기본 테스트는 외부 API 없이 통과
- mini-only 후보 생성 테스트 통과
- premium polish가 필요한 조건 테스트 통과
- 원가 추정 payload 테스트 통과
- 같은 품질 기준에서 `gpt-5.5` 호출 수가 줄어드는지 eval로 확인 가능

## 16. 참고 자료

- NotebookLM create notebook help: https://support.google.com/notebooklm/answer/16206563
- NotebookLM upgrade and usage limits: https://support.google.com/notebooklm/answer/16213268
- NotebookLM source types and limits: https://support.google.com/notebooklm/answer/16215270
- NotebookLM FAQ: https://support.google.com/notebooklm/answer/16269187
- NotebookLM mobile app help: https://support.google.com/notebooklm/answer/16296687
- Google blog, NotebookLM Plus in Google One AI Premium: https://blog.google/feed/notebooklm-google-one/
- Quizlet Practice Tests help: https://help.quizlet.com/hc/en-ca/articles/25946589648013-Studying-with-Practice-Tests
- Quizlet Learn: https://quizlet.com/features/learn
- Khan Academy, Khanmigo product learnings: https://blog.khanacademy.org/how-khan-academy-is-building-a-better-ai-tutor-our-most-recent-learnings/
- Khanmigo pricing: https://www.khanmigo.ai/pricing/
- Duolingo Max announcement: https://blog.duolingo.com/duolingo-max/
- OpenAI API pricing: https://platform.openai.com/docs/pricing
- OpenAI prompt caching: https://platform.openai.com/docs/guides/prompt-caching
- OpenAI Batch API: https://platform.openai.com/docs/guides/batch
- Gemini API pricing: https://ai.google.dev/gemini-api/docs/pricing
- Claude API pricing: https://www.claude.com/pricing
