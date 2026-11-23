# 문제 생성 + 피드백 전체 흐름

작성일: 2026-05-06

이 문서는 박준 담당 파트가 전체 서비스 안에서 어떤 순서로 동작하는지 정리한다. PDF 업로드, OCR, 문서 구조화, vector DB, Search Agent 내부 구현은 다른 담당 파트의 영역이며, 여기서는 Search Agent가 반환한 chunk 이후의 흐름만 다룬다.

## 1. 팀 전체 흐름

```text
사용자 자료 업로드
  ↓
Document/OCR 파트
  - PDF/이미지/텍스트 처리
  - 섹션 분리
  - 구조화 문서 생성
  ↓
DB/Search 파트
  - chunk 저장
  - embedding 생성
  - vector DB 검색
  - 관련 chunk 반환
  ↓
문제 생성 + 피드백 파트
  - 문제 생성
  - 정답/해설/rubric 생성
  - 품질 검증
  - 답안 제출
  - 채점/피드백
  - UserConceptStat 업데이트
```

## 2. 문제 생성 흐름

```text
POST /api/problems/generate
  ↓
GenerateProblemRequest 검증
  - document_id
  - concepts
  - type
  - count
  - difficulty
  - bloom_level
  - goal
  - course_level
  - target_rigor
  - quality_mode
  - depth
  - problem_style
  - user_requirements
  ↓
UI 선택값 정규화
  - problem_style=calculation_practice 등 제한된 preset 우선
  - unsafe user_requirements 사전 거부
  - 월 생성 수/고난도 생성 수/LLM 예산 한도 검사
  ↓
SearchService.search_chunks(...)
  ↓
retrieved chunk 검증
  - chunk 없음 거부
  - 중복 chunk_id 거부
  - 다른 document_id chunk 거부
  ↓
LearningTaskStrategyRouter
  - 전체 chunk에서 반복되는 topic_label 추출
  - 전체/지역 맥락을 합쳐 core_keywords 추출
  - 조유찬 파트가 제공한 tags/metadata를 즉시 반영
  - 관련 chunk의 지역 신호와 전체 chunk의 반복 신호를 함께 보고 content_forms 판단
  - cognitive_operations 판단
  - response_modes 판단
  - recommended_strategies 선택
  - 추천/가능/비추천 학습 콘텐츠 형식 선택
  ↓
MaterialReadinessAnalyzer
  - 자료 준비도 score
  - sufficient / limited / insufficient
  - 만들 수 있는 문제 전략
  - 위험한 생성 전략
  ↓
AssessmentBlueprintPlanner
  - 개념별 문제 수
  - 목표 Bloom level
  - 필요한 근거
  - 경고
  ↓
ProblemAgent
  - LLM 또는 결정적 대체 응답으로 문제 생성
  - 객관식: 문제, 보기, 정답, 보기별 해설
  - 주관식: 문제, 모범 답안, rubric
  ↓
ProblemQualityChecker
  - 필드/형식 검증
  - source_chunk_ids 검증
  - 자료 기반성 검증
  - definition-only 위험 검증
  - answer leak 검증
  - prompt injection leak 검증
  - deep 요청 품질 검증
  ↓
Problem 저장
  ↓
정답/해설/rubric 숨김 응답
```

## 3. 답안 제출과 피드백 흐름

```text
POST /api/problems/{problem_id}/submit
  ↓
사용자/문제 소유권 검증
  ↓
중복 제출 검증
  ↓
Submission 저장 전 답안 검증
  - 객관식: choice_id 필요
  - 주관식: text 또는 OCR text 필요
  ↓
채점
  - 객관식: LLM 없이 코드로 결정 채점
  - 주관식: rubric + source chunk + 사용자 답안을 기준으로 채점
  ↓
Feedback 생성
  - is_correct
  - score / max_score
  - mistake_type
  - weak_concepts
  - summary
  - feedback
  - recommended_review
  - 주관식: evaluation_details.rubric_results
  - 주관식: evaluation_details.confidence_reasons
  - 주관식: evaluation_details.confidence가 낮으면 조심스러운 copy 문체 적용
  - 주관식: low confidence이면 rubric별 confidence도 low로 보수 처리
  - 주관식: 경계 점수/low confidence/근거 부족이면 needs_grading_review 표시
  - copy.next_action_type / copy.next_action_label
  - copy.secondary_action_type / copy.secondary_action_label
  ↓
UserConceptStat 업데이트
  - 정답: mastery + 0.05
  - 오답: mastery - 0.08
  - 반복 오답: 복습 추천
  ↓
피드백 응답
  - action_type은 후속 행동 이벤트에 그대로 사용
  - label은 화면 표시용 문구로만 사용
```

## 4. 품질 상태 의미

```text
passed
  저장 가능한 정상 문제

limited_source
  자료 근거는 있지만 요청 수준에 비해 제한적임

needs_review
  standard 모드에서는 저장할 수 있지만, 품질 경고가 있음

rejected
  strict 모드 또는 핵심 정책 위반으로 저장하지 않음
```

현재 API는 `quality_status`를 문제별로 반환하고, 문제 생성 응답에는 `learning_task_strategy`, `material_readiness`, `blueprint`, `quality_summary`를 함께 반환한다.

학습 콘텐츠 추천은 저장용 분류 작업이 아니다. `/api/learning-contents/recommendations`는 현재 검색된 chunk와 `tags`, `metadata`만 보고 즉시 `problem_options`, `content_options`, `selectable_content_types`, `available_content_types`, `recommended_content_types`, `not_recommended_content_types`를 반환한다. `problem_options`는 객관식, 주관식, 고난도 응용 주관식처럼 문제 생성 파트가 제공할 수 있는 문제 선택지다. `content_options`는 OX, 빈칸, 매칭 같은 보조 학습 형식에 한글 이름과 추천 상태를 붙인 기능 목록이다. 화면 구성, 버튼 배치, 실제 호출 조립은 UI 파트가 결정한다. `not_recommended_content_types`는 기본 추천이 아니라는 뜻이지 무조건 차단하라는 뜻은 아니다. 단, `mistake_drill`, `mini_exam`처럼 별도 workflow가 필요한 형식은 전용 API를 사용한다.

## 5. Deep 주관식 흐름

`depth=deep`은 `short_answer`에서만 허용한다.

```text
depth=deep 요청
  ↓
자료 형태와 준비도 분석
  ↓
단순 정의형 문제 제한
  ↓
적용/분석/비교/평가형 문제 생성
  ↓
rubric 2개 이상 요구
  ↓
자료 기반성 약하면 strict 모드에서 거부
```

예:

```json
{
  "document_id": "demo_doc",
  "concepts": ["뉴턴 제2법칙"],
  "type": "short_answer",
  "count": 1,
  "goal": "exam_prep",
  "course_level": "university",
  "target_rigor": "high",
  "quality_mode": "strict",
  "depth": "deep",
  "problem_style": "calculation_practice"
}
```

## 6. 여러 자료가 들어오는 경우

여러 자료 사이의 관계 계산은 우리 파트가 직접 하지 않는다.

우리 파트가 받는 것:

```text
Search Agent가 반환한 retrieved chunks
향후 Search/DB 팀이 제공할 topic/document group metadata
```

우리 파트가 하는 것:

```text
같은 group이면 하나의 blueprint로 묶음
다른 group이면 blueprint를 분리함
group이 없거나 애매하면 자동 병합하지 않음
서로 다른 group을 섞는 문제는 사용자가 비교/통합을 명시했을 때만 허용
```

## 6.1 주제 판단 방식

문제 생성 파트는 한 문장이나 한 chunk만 보고 주제를 확정하지 않는다.

```text
전체 맥락:
  - 여러 chunk에서 반복되는 concepts
  - 반복되는 section_title
  - 전체 chunk에서 자주 등장하는 핵심어

지역 맥락:
  - 요청 concept와 직접 연결되는 chunk
  - 해당 chunk 안의 공식/관계/절차/지문/코드 단서

최종 판단:
  - 모호한 요청이면 전체 맥락의 반복 주제를 우선한다.
  - 요청 concept가 구체적이면 그 concept와 연결된 chunk의 단서를 유지한다.
  - 관련 없는 단일 chunk의 code/formula/table 신호가 전체 전략을 바꾸지 못하게 한다.
```

예를 들어 경제학 자료 여러 chunk 중 부록에 코드 예시가 하나 있어도, 전체 반복 주제가 `수요와 공급`이면 문제 전략은 경제 개념 관계 중심으로 잡는다. 반대로 사용자가 `뉴턴 제2법칙`을 명시했고 관련 chunk에 `F = ma`가 있다면, 주변 chunk가 일반 설명이어도 공식/관계 전략을 유지한다.

## 7. 직접 테스트 가능한 범위

현재 직접 테스트 가능한 것:

- Search Agent mock 또는 demo chunk 기반 문제 생성
- 객관식/주관식 생성
- deep 주관식 생성
- 정답/해설 제출 전 숨김
- 답안 제출
- 객관식 코드 채점
- 주관식 대체 응답/LLM 채점 경로
- 피드백 응답
- 품질 gate

현재 직접 테스트할 수 없는 것:

- 실제 PDF 업로드
- OCR/vision 처리
- 실제 vector DB 검색
- 자료 간 similarity 계산
- Search Agent의 ranking 품질

이 항목은 각 담당 파트와 통합된 뒤 end-to-end로 검증한다.
