# 문제 생성 + 피드백 개발 계획 요약

상세 이력은 줄이고, 실제 개발 판단에 필요한 내용만 남긴다.

## 1. 목표

사용자가 업로드한 학습 자료를 바탕으로:

- 문제를 생성하고
- 답안을 채점하고
- 왜 맞고 틀렸는지 설명하고
- 다음 학습 행동을 추천한다.

## 2. 기술 구조

```text
FastAPI
→ ProblemService / FeedbackService
→ ProblemAgent / FeedbackAgent
→ QualityChecker
→ Repository
→ SearchService
```

Search/RAG와 운영 저장소는 김태훈 DB/Vector DB 파트와 연결한다. 현재 repository는 로컬 테스트와 데모용이다.

## 3. API

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
POST /api/problems/{problem_id}/submit
GET  /api/feedback/{feedback_id}
POST /api/feedback/{feedback_id}/actions
GET  /api/feedback/{feedback_id}/actions
GET  /api/problem-analytics
GET  /api/problem-template-analytics
GET  /api/problem-regeneration-candidates
POST /api/problem-regeneration-candidates/{candidate_id}/regenerate
GET  /api/usage-ledger
GET  /api/usage-ledger/summary
POST /api/quality-reports

POST /api/learning-contents/generate
POST /api/learning-contents/recommendations
GET  /api/learning-contents/{content_id}
POST /api/learning-contents/mistake-drills/generate
POST /api/learning-contents/mini-exams/generate
```

## 4. 문제 생성 정책

- 문제는 자료 chunk 안에서 출제한다.
- 정답/해설은 서버에 저장하지만 제출 전에는 숨긴다.
- 객관식은 보기 4개와 보기별 해설을 가진다.
- 주관식은 모범 답안과 rubric을 가진다.
- 고난도 요청은 검색 범위와 생성 후보 수를 늘리고, 검증을 더 엄격하게 한다.
- 수식/계산형 문제는 LaTeX와 단계별 풀이를 사용한다.

## 5. 피드백 정책

- 객관식 채점은 코드로 처리한다.
- 주관식은 rubric 기반으로 LLM 채점한다.
- 피드백은 비난하지 않고, 헷갈린 지점과 다음 행동을 제안한다.
- UserConceptStat를 업데이트해 반복 오답 개념을 복습 추천에 넣는다.

## 6. 모델 라우팅

기본은 비용 효율, 필요할 때만 상위 모델이다.

- 일반 문제 생성: `PROBLEM_MODEL`
- 문제 품질 검증: `PROBLEM_QUALITY_MODEL`
- 학습 콘텐츠 생성: `LEARNING_CONTENT_MODEL`
- 학습 콘텐츠 품질 검증: `LEARNING_CONTENT_QUALITY_MODEL`
- 일반 피드백: 템플릿 또는 `FEEDBACK_MODEL`
- 주관식 채점: `GRADING_MODEL`
- 고위험/고난도 채점: `GRADING_QUALITY_MODEL`

## 7. 품질 검증

필수 검증:

- JSON Schema 준수
- source chunk 존재
- source chunk가 요청 문서에 속함
- source chunk ID 중복 없음
- 자료 밖 수치 생성 방지
- 원문 장문 복제 방지
- rubric 점수 합계 검증
- 사용자 문체 금지어 검사

## 8. 팀 연동

김태훈 파트:

- Search/RAG로 chunk 제공
- 안정적인 chunk ID 제공 여부 협의
- 최종 DB 저장소 연동

왕호진 파트:

- 인증된 `user_id` 제공

조유찬 파트:

- 구조화 문서, 학습 단위, 로드맵 연동

한상훈 파트:

- Guard/Personalization/Tutor와 사용자 경험 연결

## 9. 현재 다음 작업

1. 김태훈 RAG 서버와 실제 end-to-end smoke test 실행
2. 생성 산출물 색인 endpoint 최종 경로와 인증 헤더 확정
3. document/tutor/rag 파트와 같은 서버로 합칠 때 route/package 충돌 점검
4. 실제 PDF/RAG/LLM 샘플로 고난도 문제와 assessment session 품질 eval set 구축
5. 김태훈 DB/Vector DB 저장 adapter, 색인 endpoint, 인증 헤더 기준 확정
