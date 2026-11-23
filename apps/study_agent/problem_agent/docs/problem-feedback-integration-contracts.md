# 문제 생성 + 피드백 파트 연동 계약

이 문서는 박준 담당 **문제 생성 + 피드백** 파트가 다른 팀 파트와 주고받아야 하는 데이터 계약을 정리한다.

중요한 책임 경계:

- 박준 파트는 DB/Search 인프라를 직접 구현하지 않는다.
- 김태훈 파트는 데이터베이스, Vector DB, Search Agent를 담당하고 최종 원천 저장소 역할을 한다.
- 박준 파트는 문제 생성/채점/피드백 로직과 저장할 데이터의 형태를 정의한다.
- 현재 SQLAlchemy repository는 로컬 테스트와 데모를 위한 임시 저장소다.
- 최종 통합에서는 김태훈 DB/Search/RAG에서 chunk를 받아 쓰고, 생성된 문제·피드백·학습 신호 artifact를 다시 김태훈 DB/Vector DB로 보낸다.
- 사용자 인증/계정 DB는 왕호진 파트가 담당한다. 박준 파트 API는 인증 결과로 전달된 `user_id`가 반드시 있어야 동작한다.

---

## 1. Search Agent 계약

### 1.1 `/search`

문제 생성 시 관련 자료 chunk를 가져오는 endpoint다.

요청:

```json
{
  "document_id": "doc_001",
  "concepts": ["뉴턴 제2법칙"],
  "difficulty": "medium",
  "query": "뉴턴 제2법칙",
  "top_k": 6
}
```

응답:

```json
[
  {
    "chunk_id": "chunk_001",
    "document_id": "doc_001",
    "content": "뉴턴의 제2법칙은 F = ma이다.",
    "page": 12,
    "section_title": "뉴턴의 운동 법칙",
    "concepts": ["뉴턴 제2법칙", "힘", "질량", "가속도"],
    "tags": ["science", "formula", "concept_relation"],
    "metadata": {
      "subject_domain": "science",
      "content_forms": ["formula", "concept_relation"]
    }
  }
]
```

필수 필드:

- `chunk_id`
- `document_id`
- `content`
- `concepts`

권장 필드:

- `page`
- `section_title`
- `tags`: 자료 생성 파트가 붙인 가벼운 분류 태그
- `metadata`: `subject_domain`, `content_forms`, `source_type` 등 즉시 추천에 쓸 수 있는 보조 정보

검증 규칙:

- 응답 chunk의 `document_id`는 요청한 `document_id`와 같아야 한다.
- 문제 생성 결과의 `source_chunk_ids`는 Search Agent가 반환한 chunk ID 안에 있어야 한다.
- Search Agent가 없거나 오류가 나면 박준 파트 API는 `503`으로 실패한다.
- Search/RAG endpoint가 인증을 요구하면 `SEARCH_AGENT_API_KEY`, `SEARCH_AGENT_API_KEY_HEADER`로 같은 헤더를 붙인다.

설정 예:

```env
SEARCH_AGENT_URL=http://localhost:8001
SEARCH_AGENT_API_KEY=
SEARCH_AGENT_API_KEY_HEADER=X-API-Key
```

김태훈 RAG Agent 호환:

- `RAG_AGENT_URL`을 쓰는 경우 우리 파트는 김태훈 RAG 응답을 `RetrievedChunk`로 변환한다.
- endpoint 경로는 기본 `/search`를 쓰며, 통합 서버 prefix가 있으면 `RAG_AGENT_SEARCH_PATH`로 바꾼다.
- `/chunks/batch`에 해당하는 RAG endpoint가 있으면 `RAG_AGENT_CHUNKS_PATH`를 설정한다. 없으면 `RAG_AGENT_FETCH_PATH=/fetch`로 `id` 필터 조회를 사용하고, 그것도 끄면 검색 시 저장한 source snapshot/cache를 사용한다.
- 문제/피드백 파트는 조유찬 Document Agent가 텍스트화하고 청킹한 결과를 사용하므로 기본값은 `RAG_AGENT_TEXT_ONLY=true`다.
- `RAG_AGENT_TEXT_ONLY=true`이면 RAG 호출에 `X-RAG-Text-Only: true` 헤더를 보낸다. 김태훈 RAG 서버는 가능하면 이 헤더를 보고 image/base64 payload를 제외한다.
- 응답 목록 키는 `results`, `documents`, `chunks`, `items`, `data`, `matches`, `contexts`, `nodes`를 허용한다.
- 본문 필드는 `parent_text`, `text`, `content`, `page_content`, `document`, `body` 중 하나를 허용한다. `parent_text`가 있으면 문제 생성용 본문으로 우선 사용하고, `document`가 객체이고 그 안에 `page_content`나 `content`가 있어도 받는다.
- `source`, `section_title`, `page`, `concepts`, `tags`, `content_forms`, `subject_domain`은 최상위 또는 `metadata` 내부에 있어도 된다.
- `score`는 chunk `metadata.score`로 보존한다.
- `image`가 오면 기본적으로 `metadata.image_available=true`, `metadata.image_omitted=text_only`만 저장한다. base64 payload는 문제/피드백 생성에 쓰지 않는다.
- `chunk_id`, `id`, `node_id`가 있으면 그대로 쓰고, 없으면 안정적인 `rag_...` chunk ID를 만든다.
- RAG endpoint가 인증을 요구해도 별도 설정명을 만들지 않고 `SEARCH_AGENT_API_KEY`, `SEARCH_AGENT_API_KEY_HEADER`를 함께 사용한다.
- ngrok 임시 endpoint를 쓸 때는 `RAG_AGENT_SKIP_NGROK_WARNING=true`로 `ngrok-skip-browser-warning: true` 헤더를 보낼 수 있다.
- 요청한 `document_id`와 다른 문서 결과가 오면 문제 생성을 중단한다.
- 결과가 비어 있으면 문제 생성을 중단한다.

### 1.2 `/chunks/batch`

피드백 생성 시 문제에 연결된 chunk를 다시 가져오는 endpoint다.

요청:

```json
{
  "document_id": "doc_001",
  "chunk_ids": ["chunk_001", "chunk_002"]
}
```

응답:

```json
[
  {
    "chunk_id": "chunk_001",
    "document_id": "doc_001",
    "content": "뉴턴의 제2법칙은 F = ma이다.",
    "page": 12,
    "section_title": "뉴턴의 운동 법칙",
    "concepts": ["뉴턴 제2법칙"]
  }
]
```

### 1.3 생성 산출물 색인 API

문제/피드백 파트가 생성한 문제, 피드백, 평가 리포트, 학습 콘텐츠, 학습 신호를 김태훈 Vector DB에서 나중에 검색할 수 있게 보내는 outbound endpoint다. 실제 endpoint 경로는 김태훈 파트가 정하고, 우리 쪽은 `.env`의 `GENERATED_ARTIFACT_INDEX_URL`에 전체 URL을 넣어서 호출한다.

예:

```env
GENERATED_ARTIFACT_INDEX_URL=http://localhost:8001/generated-artifacts/index
GENERATED_ARTIFACT_PUBLISH_ENABLED=true
GENERATED_ARTIFACT_PUBLISH_FAIL_FAST=false
GENERATED_ARTIFACT_API_KEY=
GENERATED_ARTIFACT_API_KEY_HEADER=X-API-Key
GENERATED_ARTIFACT_TIMEOUT_SECONDS=3
```

문제 생성 후 전송 payload:

```json
{
  "artifact_id": "prob_001",
  "artifact_type": "problem",
  "user_id": "user_001",
  "document_id": "doc_001",
  "content": "문제: 뉴턴 제2법칙에 대한 설명으로 가장 적절한 것은?\n보기:\n- A. 알짜힘은 질량과 가속도의 곱이다.\n- B. 외부 힘이 없어도 항상 가속한다.\n정답과 해설은 제출 전 검색 결과에 노출하지 않습니다.",
  "metadata": {
    "schema_version": "problem_artifact.v1",
    "producer": "problem_agent",
    "problem_id": "prob_001",
    "question": "뉴턴 제2법칙에 대한 설명으로 가장 적절한 것은?",
    "problem_type": "multiple_choice",
    "difficulty": "medium",
    "bloom_level": "understand",
    "concepts": ["뉴턴 제2법칙"],
    "source_refs": [
      {
        "document_id": "doc_001",
        "chunk_id": "chunk_001",
        "page": 12,
        "section_title": "뉴턴의 운동 법칙"
      }
    ],
    "quality_status": "passed",
    "item_model_id": "concept_comparison",
    "answer_hidden_until_submission": true
  },
  "source_chunk_ids": ["chunk_001"],
  "visibility": "hidden_until_submission",
  "created_at": "2026-05-07T12:00:00+09:00"
}
```

피드백 생성 후 전송 payload:

```json
{
  "artifact_id": "fb_001",
  "artifact_type": "feedback",
  "user_id": "user_001",
  "document_id": "doc_001",
  "content": "피드백 요약: 원인과 결과의 순서가 헷갈렸어요.\n피드백: 자료에서는 A가 먼저 나오고 그 다음 B가 이어진다고 설명해요.\n복습 추천: 뉴턴 제2법칙",
  "metadata": {
    "schema_version": "feedback_artifact.v1",
    "producer": "problem_agent",
    "feedback_id": "fb_001",
    "problem_id": "prob_001",
    "submission_id": "sub_001",
    "summary": "원인과 결과의 순서가 헷갈렸어요.",
    "is_correct": false,
    "score": 0,
    "max_score": 1,
    "mistake_type": "concept_misunderstanding",
    "weak_concepts": ["뉴턴 제2법칙"],
    "recommended_review": ["뉴턴 제2법칙"],
    "source_chunk_ids": ["chunk_001"]
  },
  "source_chunk_ids": ["chunk_001"],
  "visibility": "private",
  "created_at": "2026-05-07T12:03:00+09:00"
}
```

평가 세트 최종 제출 후 전송 payload:

```json
{
  "artifact_id": "assessment_report:asess_001",
  "artifact_type": "assessment_report",
  "user_id": "user_001",
  "document_id": "doc_001",
  "content": "평가 세트 리포트: asess_001\n점수: 1/2\n완료율: 100%\n잘한 개념: 힘\n약점 개념: 뉴턴 제2법칙\n복습 추천: 뉴턴 제2법칙\n다음 행동: 뉴턴 제2법칙을 다시 확인해 보세요.",
  "metadata": {
    "schema_version": "assessment_report_artifact.v1",
    "producer": "problem_agent",
    "session_id": "asess_001",
    "retry_of_session_id": "asess_000",
    "status": "submitted",
    "problem_count": 2,
    "submitted_count": 2,
    "correct_count": 1,
    "total_score": 1,
    "max_score": 2,
    "score_ratio": 0.5,
    "completion_ratio": 1,
    "total_elapsed_time_sec": 330,
    "time_limit_seconds": 300,
    "time_over_limit": true,
    "strong_concepts": ["힘"],
    "weak_concepts": ["뉴턴 제2법칙"],
    "recommended_review": ["뉴턴 제2법칙"],
    "next_step": "뉴턴 제2법칙을 다시 확인해 보세요.",
    "previous_score_ratio": 0.25,
    "score_delta": 0.25,
    "concept_score_deltas": {"뉴턴 제2법칙": 0.5},
    "concept_summary": [
      {
        "concept": "뉴턴 제2법칙",
        "status": "needs_review",
        "score_ratio": 0.5,
        "submitted_count": 2,
        "problem_count": 2
      }
    ]
  },
  "source_chunk_ids": [],
  "visibility": "private"
}
```

학습 콘텐츠 생성 후 전송 payload:

```json
{
  "artifact_id": "content_001",
  "artifact_type": "learning_content",
  "user_id": "user_001",
  "document_id": "doc_001",
  "content": "학습 콘텐츠: cloze\n개념: 뉴턴 제2법칙\n빈칸: 힘은 질량과 ____의 곱이다.",
  "metadata": {
    "schema_version": "learning_content_artifact.v1",
    "producer": "problem_agent",
    "content_id": "content_001",
    "content_type": "cloze",
    "interaction_mode": "auto_gradable",
    "concepts": ["뉴턴 제2법칙"],
    "difficulty": "medium",
    "bloom_level": "understand",
    "quality_status": "passed",
    "quality_score": 0.9,
    "source_chunk_ids": ["chunk_001"],
    "private_payload_available": true
  },
  "source_chunk_ids": ["chunk_001"],
  "visibility": "private"
}
```

학습 신호 전송 payload:

```json
{
  "artifact_id": "learning_signal:fb_001",
  "artifact_type": "learning_signal",
  "user_id": "user_001",
  "document_id": "doc_001",
  "content": "학습 신호: 뉴턴 제2법칙\n점수: 0/1\n학습 상태: high_confidence_misconception\n복습 추천: 뉴턴 제2법칙",
  "metadata": {
    "schema_version": "learning_signal_artifact.v1",
    "producer": "problem_agent",
    "problem_id": "prob_001",
    "submission_id": "sub_001",
    "feedback_id": "fb_001",
    "concepts": ["뉴턴 제2법칙"],
    "is_correct": false,
    "score": 0,
    "max_score": 1,
    "mistake_type": "concept_misunderstanding",
    "learning_state": "high_confidence_misconception",
    "weak_concepts": ["뉴턴 제2법칙"],
    "recommended_review": ["뉴턴 제2법칙"],
    "mastery_updates": [
      {
        "concept": "뉴턴 제2법칙",
        "attempts": 2,
        "correct_count": 0,
        "wrong_count": 2,
        "mastery": 0.34,
        "mistake_types": ["concept_misunderstanding"],
        "should_review": true
      }
    ],
    "source_chunk_ids": ["chunk_001"]
  },
  "source_chunk_ids": ["chunk_001"],
  "visibility": "private"
}
```

중요 정책:

- 문제 artifact의 `content`에는 정답과 해설을 넣지 않는다.
- 피드백 artifact는 사용자별 private 데이터로 취급한다.
- 평가 리포트 artifact는 최종 제출된 평가 세트만 보낸다. 학생 학습에 필요한 총점, 완료율, 시간, 강점/약점 개념, 복습 추천, 재도전 변화만 담고 문항별 세부 결과, feedback id 목록, 원문 답안은 넣지 않는다.
- 학습 콘텐츠 artifact는 사용자별 private 데이터로 취급한다. 빈칸, OX, 순서 배열, 매칭처럼 정답이 있는 콘텐츠는 색인 본문과 metadata에 정답, 해설, 정답 순서를 넣지 않는다.
- 학습 신호 artifact는 사용자별 private 데이터로 취급하고, 원문 답안이나 정답/해설을 넣지 않는다.
- Vector DB 검색 시 최소한 `user_id`, `document_id`, `artifact_type`, `visibility`로 필터링해야 한다.
- 사용자 이름은 현재 문제/피드백 파트가 직접 알지 못한다. 계정 파트에서 필요하면 `user_id`와 매핑한다.
- 색인 API가 인증을 요구하면 `GENERATED_ARTIFACT_API_KEY`, `GENERATED_ARTIFACT_API_KEY_HEADER`로 헤더를 보낸다.

용량 정책:

- Vector DB에는 검색과 개인화에 필요한 색인용 요약만 보낸다.
- artifact `content`는 4,000자 안에서 잘라 보낸다. 원문 장문이나 풀이 전문은 별도 저장소에서 관리하고 Vector DB 색인 본문에는 넣지 않는다.
- 평가 리포트와 학습 신호의 개념 목록, 복습 추천, mastery update, 개념별 요약은 상위 20개까지만 보낸다.
- 문항별 세부 결과 배열, feedback id 목록, 원문 답안, 정답, 해설, 전체 rubric은 색인 payload에 넣지 않는다.
- 사용자가 많아지면 실시간 요청 경로에서 직접 Vector DB write를 기다리지 않고, 김태훈 파트의 queue/outbox 또는 batch index API로 넘기는 구성을 우선한다.
- 오래된 artifact retention, 압축, cold storage, embedding 재생성 정책은 김태훈 DB/Vector DB 운영 정책에서 정하되, 우리 파트는 `artifact_type`, `created_at`, `user_id`, `document_id` 필드를 항상 보내서 보존 기간을 적용할 수 있게 한다.
- 색인 API 타임아웃은 LLM 타임아웃과 분리한다. `GENERATED_ARTIFACT_TIMEOUT_SECONDS` 기본값은 3초이며, 느린 Vector DB write가 문제 생성/제출 요청을 오래 막지 않게 한다.
- API 호출 실패는 기본적으로 문제 생성/피드백 저장을 막지 않는다. 통합 테스트에서 실패를 즉시 보고 싶으면 `GENERATED_ARTIFACT_PUBLISH_FAIL_FAST=true`를 사용한다.

---

## 2. DB 저장 계약

이 계약은 실제 DB 테이블 구현을 강제하지 않는다. 김태훈 파트가 어떤 DB 구조를 쓰더라도, 박준 파트는 아래 데이터를 저장하고 다시 조회할 수 있으면 된다.

### 2.1 Problem

문제 생성 결과 저장 payload다.

```json
{
  "user_id": "user_001",
  "document_id": "doc_001",
  "type": "multiple_choice",
  "difficulty": "medium",
  "bloom_level": "understand",
  "question": "뉴턴의 제2법칙에 대한 설명으로 가장 적절한 것은?",
  "choices": [
    { "id": "A", "text": "알짜힘은 질량과 가속도의 곱이다." },
    { "id": "B", "text": "외부 힘이 없어도 항상 가속한다." },
    { "id": "C", "text": "질량이 클수록 같은 힘에서 가속도는 커진다." },
    { "id": "D", "text": "힘은 항상 속도와 같은 방향이다." }
  ],
  "answer": { "choice_id": "A", "text": "알짜힘은 질량과 가속도의 곱이다." },
  "explanation": "뉴턴의 제2법칙은 F = ma로 표현된다.",
  "choice_explanations": {
    "A": "자료 내용과 일치한다.",
    "B": "자료 근거가 없는 설명이다.",
    "C": "자료의 질량과 가속도 관계를 반대로 설명한다.",
    "D": "자료에서 설명한 법칙과 직접 관련이 없다."
  },
  "rubric": null,
  "concepts": ["뉴턴 제2법칙"],
  "source_chunk_ids": ["chunk_001"],
  "quality_status": "passed"
}
```

중요 정책:

- `answer`, `explanation`, `choice_explanations`, `rubric`은 서버에는 저장하되 제출 전 사용자 응답에서는 숨긴다.
- 정답/해설은 성공한 `Feedback`이 생성된 뒤에만 공개한다.
- `source_chunk_ids`가 없는 문제는 저장하지 않는다.
- `source_chunk_ids`는 Search Agent가 실제 반환한 chunk에 포함되어야 하고, 같은 `document_id`에 속해야 한다.
- `source_chunk_ids`는 중복되면 안 된다.
- 생성된 문제의 `document_id`, `type`, `difficulty`, `bloom_level`은 사용자의 생성 요청과 일치해야 한다.
- 객관식은 `choices` 4개와 정답 1개가 필요하다.
- 객관식은 `choice_explanations`가 모든 보기 ID를 포함해야 하며 `rubric`은 `null`이어야 한다.
- 객관식 `choice_explanations`에는 존재하지 않는 보기 ID가 들어가면 안 된다.
- 주관식은 `choices`, `choice_explanations`가 `null`이어야 하고 `answer.text`와 `rubric`이 필요하다.
- 요청한 개수보다 유효한 문제가 적게 생성되면 일부만 저장하지 않고 전체 요청을 실패시킨다.

### 2.2 Submission

사용자 답안 제출 payload다.

```json
{
  "problem_id": "prob_001",
  "user_id": "user_001",
  "confidence_level": 4,
  "answer": {
    "choice_id": "C",
    "text": "C",
    "solution_steps": ""
  }
}
```

주관식 답안:

```json
{
  "problem_id": "prob_002",
  "user_id": "user_001",
  "answer": {
    "text": "뉴턴의 제2법칙은 힘, 질량, 가속도의 관계를 설명한다.",
    "solution_steps": "F = ma를 사용했다."
  }
}
```

태블릿 필기 답안:

```json
{
  "problem_id": "prob_002",
  "user_id": "user_001",
  "answer": {
    "input_mode": "tablet_ocr",
    "ocr_text": "뉴턴의 제2법칙은 힘, 질량, 가속도의 관계를 설명한다.",
    "ocr_confidence": 0.91,
    "tablet_image_url": "https://example.test/submissions/sub_001.png"
  }
}
```

정책:

- 객관식 제출에는 `answer.choice_id`가 필요하다.
- 주관식 제출에는 `answer.text`가 필요하다.
- `confidence_level`은 선택값이며 1~4 범위다. 학습자가 답에 얼마나 확신했는지 나타낸다.
- `confidence_level`이 없으면 기존 mastery 업데이트 규칙을 그대로 사용한다.
- `confidence_level`이 있으면 정답/오답을 `secure_mastery`, `fragile_mastery`, `high_confidence_misconception`, `knowledge_gap`, `partial_understanding` 같은 학습 상태로 분류한다.
- `input_mode=tablet_ocr`이고 `answer.text`가 없으면 박준 파트는 `ocr_text`를 채점용 텍스트로 사용한다.
- OCR/vision 자체 구현과 이미지 저장 인프라는 박준 파트가 담당하지 않는다. 박준 파트는 OCR/vision 결과를 받아 채점한다.
- `ocr_confidence`는 0.0~1.0 범위다.

### 2.3 Feedback

피드백 생성 결과 저장 payload다.

```json
{
  "submission_id": "sub_001",
  "problem_id": "prob_001",
  "user_id": "user_001",
  "is_correct": false,
  "score": 0,
  "max_score": 1,
  "mistake_type": "concept_misunderstanding",
  "learning_state": "high_confidence_misconception",
  "weak_concepts": ["뉴턴 제2법칙"],
  "summary": "핵심 개념을 조금 다르게 이해했어.",
  "feedback": "정답은 A야. C를 고른 걸 보면 질량과 가속도의 관계를 헷갈린 것 같아.",
  "recommended_review": ["뉴턴 제2법칙"],
  "source_chunk_ids": ["chunk_001"],
  "choice_diagnostic": {
    "selected_choice_id": "C",
    "selected_choice_text": "가속도는 항상 0이다.",
    "correct_choice_id": "A",
    "correct_choice_text": "힘은 질량과 가속도의 곱이다.",
    "selected_choice_explanation": "헷갈린 지점: 가속도를 항상 0으로 본 점.",
    "correct_choice_explanation": "자료 내용과 일치한다.",
    "misconception": "가속도를 항상 0으로 본 점.",
    "repair_strategy": "$F = ma$ 관계로 다시 확인한다.",
    "mistake_type": "concept_misunderstanding"
  },
  "copy": {
    "title": "개념의 방향이 조금 헷갈리셨군요 🤔",
    "body": "개념 자체는 보셨는데, 관계의 방향이 살짝 바뀌었어요.",
    "next_action_type": "review_concept_card",
    "next_action_label": "개념 카드로 30초 복습",
    "secondary_action_type": "solve_similar",
    "secondary_action_label": "비슷한 문제 풀기"
  }
}
```

주관식 피드백은 `evaluation_details`에 rubric별 채점 결과와 채점 신뢰도 이유를 함께 저장한다.

```json
{
  "submission_id": "sub_002",
  "problem_id": "prob_002",
  "user_id": "user_001",
  "is_correct": false,
  "score": 2,
  "max_score": 4,
  "mistake_type": "incomplete_answer",
  "learning_state": "partial_understanding",
  "weak_concepts": ["뉴턴 제2법칙"],
  "summary": "답안에 더 보완할 지점이 있어.",
  "feedback": "정답 여부: 아직 정답은 아니에요.\n헷갈린 지점: 조건 해석이 일부 빠졌어요.\n올바른 개념: 같은 힘 조건에서는 질량과 가속도의 관계를 함께 설명해야 해요.\n복습 추천: 뉴턴 제2법칙",
  "recommended_review": ["뉴턴 제2법칙"],
  "source_chunk_ids": ["chunk_001"],
  "evaluation_details": {
    "confidence": "medium",
    "confidence_reasons": [
      "문제의 근거 chunk를 다시 확인해 rubric 채점 기준과 비교했습니다.",
      "일부 rubric만 충족되어 부분 점수 판단으로 처리했습니다.",
      "rubric 항목 수와 채점 결과 항목 수가 일치합니다."
    ],
    "needs_grading_review": true,
    "grading_review_reasons": [
      "부분 점수가 통과/오답 경계에 가까워 rubric 판단 재검토가 필요합니다."
    ],
    "rubric_results": [
      {
        "criterion": "F = ma의 변수 관계를 설명한다.",
        "max_points": 2,
        "awarded_points": 2,
        "matched": true,
        "evidence_from_answer": "힘은 질량과 가속도의 곱이다.",
        "missing_point": null,
        "next_action": null,
        "confidence": "high"
      },
      {
        "criterion": "같은 힘 조건에서 질량이 클수록 가속도는 작아진다고 설명한다.",
        "max_points": 2,
        "awarded_points": 0,
        "matched": false,
        "evidence_from_answer": null,
        "missing_point": "같은 힘 조건에서 질량과 가속도의 방향 관계가 빠졌어요.",
        "next_action": "같은 힘일 때 질량만 바꿔서 가속도 변화를 한 문장으로 써보세요.",
        "confidence": "medium"
      }
    ]
  }
}
```

피드백 본문은 사용자에게 보여주기 쉽도록 아래 라벨을 포함하는 것을 기본으로 한다.

```text
정답 여부:
헷갈린 지점:
올바른 개념:
복습 추천:
```

`choice_diagnostic`은 객관식 제출 이후 API 응답과 통계 이벤트에 사용할 구조화 진단 정보다.
DB에 새 컬럼으로 저장하지 않더라도, 현재 구현은 저장된 `choice_explanations`, 제출한 `choice_id`, 정답 보기 정보를 바탕으로 같은 값을 파생할 수 있다.

`copy.next_action_type`과 `copy.secondary_action_type`은 프론트가 `/api/feedback/{feedback_id}/actions`에 그대로 보낼 수 있는 구조화 enum이다. `next_action_label`과 `secondary_action_label`은 화면 표시용 문구이므로 라벨에서 action을 추론하지 않는다.

`evaluation_details.confidence_reasons`는 사용자에게 그대로 긴 설명으로 노출하기보다, 채점 재검토 표시나 “OCR 인식 결과 기준으로 채점했어요” 같은 짧은 안내에 사용할 수 있다.
`evaluation_details.confidence`가 `low`이면 `copy.body`도 더 조심스러운 문체로 내려간다. OCR/필기 인식이나 답안 근거가 애매한 경우 프론트는 이 상태를 확정 채점처럼 과하게 강조하지 않는다.
OCR/필기 인식 신뢰도가 낮거나 근거 chunk가 부족하면 전체 confidence를 `low`로 낮추고, rubric별 `rubric_results[].confidence`도 `low`로 맞춘다.
`needs_grading_review`는 점수 경계, low confidence, 근거 부족 같은 이유로 상위 모델 또는 운영자 재검토 후보임을 나타낸다.

`learning_state`는 confidence가 함께 제출된 경우 학습 상태를 더 세밀하게 표현한다.

- `secure_mastery`: 확신 있게 맞힘
- `fragile_mastery`: 맞혔지만 확신이 낮음
- `high_confidence_misconception`: 확신 있게 틀림
- `knowledge_gap`: 확신이 낮고 틀림
- `partial_understanding`: 일부 기준은 맞았지만 완전한 정답은 아님
- `unreported`: confidence가 제출되지 않음

### 2.3.1 FeedbackActionEvent

피드백을 본 뒤 사용자가 어떤 행동을 했는지 저장하는 payload다. 피드백 품질의 목표는 “좋은 문장”이 아니라 다음 행동과 성취 개선이므로, 프론트는 주요 버튼 클릭과 후속 학습 완료를 이 endpoint로 보내면 된다.

API:

```text
POST /api/feedback/{feedback_id}/actions
GET  /api/feedback/{feedback_id}/actions
```

예시:

```json
{
  "event_type": "next_action_clicked",
  "action_type": "review_concept_card",
  "event_metadata": {
    "surface": "feedback_card"
  }
}
```

### 2.3.2 AssessmentSessionReadiness

시험 대비 문제 세트는 자료와 풀이 기록이 어느 정도 쌓였을 때 품질이 좋아진다. 그래서 세트를 만들기 전에 readiness endpoint로 현재 상태를 먼저 확인한다.

API:

```text
POST /api/assessment-sessions/readiness
POST /api/assessment-sessions/generate
GET  /api/assessment-sessions/{session_id}
POST /api/assessment-sessions/{session_id}/submit
GET  /api/assessment-sessions/{session_id}/report
POST /api/assessment-sessions/{session_id}/retry
GET  /api/assessment-sessions/{session_id}/history
```

응답 상태:

- `not_ready`: 검색 근거가 없거나 다른 문서 chunk가 섞여 있어 세트 생성 기준으로 쓰기 어렵다.
- `diagnostic_ready`: 자료는 있지만 풀이 기록이 적어서 짧은 진단 세트가 적절하다.
- `personalized_ready`: 반복 오답이나 낮은 mastery 기록을 바탕으로 개인 맞춤 세트를 만들 수 있다.
- `exam_ready`: 사용자가 고난도/시험 대비를 원했고, 자료 근거 안에서 응용 문제 세트를 구성할 수 있다.

자료 양이 적더라도 검색된 근거 chunk가 있으면 고난도 요청을 막지 않는다. 대신 응답의 `warnings`에 제한을 표시하고, 자료에 없는 외부 사실을 새로 넣지 않는 방식으로 출제해야 한다.

예시 응답:

```json
{
  "status": "diagnostic_ready",
  "score": 0.54,
  "material_score": 0.61,
  "learner_history_score": 0.0,
  "quality_gate_score": 0.65,
  "total_attempts": 0,
  "covered_concepts": ["뉴턴 제2법칙", "질량과 가속도"],
  "weak_concepts": [],
  "can_generate_source_based_set": true,
  "can_generate_personalized_set": false,
  "can_generate_exam_set": false,
  "recommended_blueprint": {
    "goal": "concept_mastery",
    "course_level": "high_school",
    "target_rigor": "standard",
    "total_count": 3,
    "distribution": [
      {
        "concept": "뉴턴 제2법칙",
        "problem_type": "multiple_choice",
        "bloom_level": "understand",
        "count": 3,
        "points": 1,
        "strategies": ["basic_concept_check"],
        "required_evidence": ["source_chunk_ids"]
      }
    ],
    "warnings": []
  },
  "coverage_report": {
    "requested_concepts": ["뉴턴 제2법칙"],
    "source_covered_concepts": ["뉴턴 제2법칙"],
    "weak_or_missing_concepts": [],
    "coverage_ratio": 1.0,
    "difficulty_distribution": {
      "medium": 3
    },
    "problem_type_distribution": {
      "multiple_choice": 3
    },
    "bloom_distribution": {
      "understand": 3
    },
    "estimated_time_minutes": 6,
    "includes_multi_concept_items": false,
    "warnings": []
  },
  "recommended_next_step": "아직 풀이 기록이 적으니 3~5문제 진단 세트로 약한 부분을 먼저 찾는 게 좋아요."
}
```

`recommended_blueprint`는 생성 결과가 아니라, 현재 자료와 풀이 기록으로 어떤 세트 구성이 적절한지 보여주는 계획이다. UI는 이 값을 기본값으로 삼고, 실제 생성은 `POST /api/assessment-sessions/generate` 또는 일반 문제 생성 요청으로 수행한다.
`coverage_report`는 요청 개념이 검색 자료로 얼마나 덮이는지, 어떤 난이도/문제 유형/Bloom 분포가 예상되는지 보여준다. 자료 근거가 약한 개념은 `weak_or_missing_concepts`와 `warnings`에 표시한다.

`POST /api/assessment-sessions/generate`는 readiness가 `not_ready`이면 `422`로 막고, 가능하면 기존 문제 생성 엔진을 사용해 저장형 session과 정답/해설/rubric이 숨겨진 `problems`, `readiness`, `quality_summary`를 함께 반환한다. 선택값 `time_limit_seconds`가 있으면 세트 메타데이터에 저장한다.
`POST /api/assessment-sessions/{session_id}/submit`은 해당 세트의 답안을 받으며, 기존 문제별 채점·피드백 엔진을 재사용한다. 기본값은 `finalize=true`라서 모든 미제출 문제 답안이 필요하다. `finalize=false`이면 일부 문제만 먼저 채점하고 session 상태를 `in_progress`로 둔다. 이미 채점된 문제를 다시 보내면 `409`로 막는다. 각 답안의 `elapsed_time_sec`는 세트 리포트의 총 풀이시간 계산에 사용한다.
`GET /api/assessment-sessions/{session_id}/report`는 제출 수, 정답 수, 점수 비율, 완료율, 총 풀이시간, 시간 초과 여부, 잘한 개념, 약점 개념, 개념별 결과, 추천 복습, 문제별 제출 결과, 다음 행동 문구를 반환한다.
`POST /api/assessment-sessions/{session_id}/retry`는 기존 세트 요청을 바탕으로 새 세트를 만들고 `retry_of_session_id`를 남긴다. 새 세트 리포트는 `previous_score_ratio`, `score_delta`, `previous_completion_ratio`, `completion_delta`, `concept_score_deltas`로 이전 세트와 비교한다.
`GET /api/assessment-sessions/{session_id}/history`는 원본 세트부터 다시 풀기 세트까지의 `attempt_count`, `best_session_id`, `best_score_ratio`, `latest_score_delta_from_first`, `trend`, `attempts`를 반환한다.

지원 event:

- `next_action_clicked`: 피드백의 다음 행동 버튼을 누름
- `retry_completed`: 다시 풀기를 완료함
- `followup_problem_completed`: 후속 문제를 완료함
- `helpful_rating`: 피드백 도움 여부를 평가함

지원 action:

- `retry`
- `show_hint`
- `review_concept_card`
- `solve_similar`
- `see_worked_example`
- `mini_quiz`
- `mark_conditions`
- `split_steps`
- `compare_terms`
- `review_formula`
- `check_units`
- `rewrite_answer`
- `stop`

정책:

- 본인 피드백에 대해서만 이벤트를 보낼 수 있다.
- `target_problem_id`가 있으면 본인 문제인지 확인한다.
- `target_content_id`가 있으면 본인 학습 콘텐츠인지 확인한다.
- `helpful_rating`은 1~5 범위다.
- `retry_completed`, `followup_problem_completed`는 `is_successful`을 함께 보낸다.
- `followup_problem_completed`는 `target_problem_id`가 필요하며, 연결된 `MistakeRemediationEvent`가 있으면 해결 여부를 자동 갱신한다.

### 2.4 UserConceptUpdate

User DB/로드맵 파트에 넘길 학습 상태 업데이트 payload다.

```json
{
  "user_id": "user_001",
  "problem_id": "prob_001",
  "submission_id": "sub_001",
  "feedback_id": "fb_001",
  "concepts": ["뉴턴 제2법칙"],
  "is_correct": false,
  "score": 0,
  "max_score": 1,
  "mistake_type": "concept_misunderstanding",
  "learning_state": "high_confidence_misconception",
  "weak_concepts": ["뉴턴 제2법칙"],
  "recommended_review": ["뉴턴 제2법칙"],
  "mastery_updates": [
    {
      "concept": "뉴턴 제2법칙",
      "attempts": 2,
      "correct_count": 0,
      "wrong_count": 2,
      "mastery": 0.34,
      "mistake_types": ["concept_misunderstanding"],
      "should_review": true,
      "last_attempt_at": "2026-05-06T00:00:00Z"
    }
  ]
}
```

이 payload는 사용자 계정 DB를 직접 수정하라는 뜻이 아니다. 왕호진/User DB 파트 또는 로드맵 파트가 받아서 사용자 모델 업데이트에 활용할 수 있는 이벤트 데이터다.

mastery 업데이트 규칙:

- 정답이면 해당 개념의 `mastery`를 `+0.05` 한다.
- 오답이면 해당 개념의 `mastery`를 `-0.08` 한다.
- 힌트를 많이 보고 맞힌 정답은 상승폭을 줄인다.
- confidence가 낮은 정답은 `fragile_mastery`로 보고 상승폭을 줄인다.
- confidence가 높은 오답은 `high_confidence_misconception`으로 보고 감소폭을 키운다.
- 부분 점수가 있는 주관식 오답은 `partial_understanding`으로 보고 감소폭을 완화할 수 있다.
- `mastery`는 항상 `0.0 ~ 1.0` 사이로 제한한다.
- 같은 개념을 2회 이상 틀리면 `should_review=true`로 표시하고 `recommended_review`에 포함한다.

### 2.5 LearningContent

학습 콘텐츠 저장/응답 계약이다. 이 계약은 문제 생성 + 피드백 파트가 생성할 수 있는 학습 평가/연습 콘텐츠의 공통 형태를 정의한다.

지원 콘텐츠 유형:

- `flashcard`: 개념 카드
- `cloze`: 빈칸 문제
- `true_false`: OX 문제
- `ordering`: 순서 배열 문제
- `matching`: 짝 맞추기 문제
- `worked_example`: 풀이 예시
- `mistake_drill`: 오답 맞춤 연습
- `mini_exam`: 미니 모의고사
- `concept_summary_card`: 개념 확인 카드

추천 API:

```http
POST /api/learning-contents/recommendations
```

요청:

```json
{
  "document_id": "doc_001",
  "concepts": ["뉴턴 제2법칙"],
  "count": 3,
  "difficulty": "medium",
  "bloom_level": "understand"
}
```

응답:

```json
{
  "problem_options": [
    {
      "problem_type": "multiple_choice",
      "difficulty": "medium",
      "bloom_level": "understand",
      "target_rigor": "standard",
      "problem_style": "concept_check",
      "label": "객관식 빠른 확인",
      "reason": "처음 학습할 때 부담 없이 핵심 개념을 확인하기 좋습니다."
    },
    {
      "problem_type": "short_answer",
      "difficulty": "hard",
      "bloom_level": "analyze",
      "target_rigor": "high",
      "problem_style": "calculation_practice",
      "label": "고난도 응용 주관식",
      "reason": "자료에 관계, 절차, 수식, 근거 중 하나 이상이 있어 분석형 문제로 확장할 수 있습니다."
    }
  ],
  "content_options": [
    {
      "content_type": "worked_example",
      "label": "풀이 예시",
      "recommendation_level": "recommended",
      "reason": "이 자료와 잘 맞아 먼저 추천합니다."
    },
    {
      "content_type": "ordering",
      "label": "순서 배열",
      "recommendation_level": "not_recommended",
      "reason": "절차나 시간 흐름이 뚜렷할 때 더 잘 맞습니다."
    }
  ],
  "selectable_content_types": ["concept_summary_card", "flashcard", "true_false", "cloze", "matching", "ordering", "worked_example", "mini_exam"],
  "available_content_types": ["concept_summary_card", "flashcard", "true_false", "cloze", "worked_example"],
  "recommended_content_types": ["concept_summary_card", "flashcard", "true_false", "cloze", "worked_example"],
  "not_recommended_content_types": ["ordering", "matching", "mistake_drill", "mini_exam"],
  "reason": "자료에서 수식, 개념 관계 신호가 보여 핵심 정리 카드, 개념 카드, OX, 빈칸부터 추천한다.",
  "learning_task_strategy": {},
  "material_readiness": {}
}
```

정책:

- 추천 API는 별도 저장이나 장기 분류 작업을 하지 않는다.
- 현재 검색된 chunk의 `tags`, `metadata`, `concepts`, `content`만 보고 즉시 판단한다.
- `problem_options`는 객관식, 주관식, 고난도 응용 주관식처럼 문제 생성 파트가 제공할 수 있는 문제 선택지다.
- `content_options`는 OX, 빈칸, 매칭 같은 보조 학습 형식에 한글 이름과 추천 상태를 붙인 기능 목록이다.
- UI 구성, 버튼 배치, 실제 호출 조립은 UI 파트가 결정한다. 이 API는 우리 파트의 생성 가능 기능과 자료 적합도만 명시한다.
- `selectable_content_types`는 프론트가 사용자에게 보여줄 수 있는 선택지다.
- `recommended_content_types`는 프론트에서 먼저 보여줄 기본 추천이다.
- `available_content_types`는 현재 자료로 특히 자연스럽게 만들 수 있는 형식이다.
- `not_recommended_content_types`는 숨기거나 뒤로 보낼 수 있지만, 일반 직접 생성 API가 지원하는 형식이면 과도하게 차단하지 않는다.
- `mistake_drill`과 `mini_exam`은 직접 생성 API가 아니라 별도 workflow API에서 생성한다.

공통 payload:

```json
{
  "id": "content_001",
  "user_id": "user_001",
  "document_id": "doc_001",
  "content_type": "flashcard",
  "interaction_mode": "study_only",
  "concepts": ["뉴턴 제2법칙"],
  "source_chunk_ids": ["chunk_001"],
  "source_revision_ids": ["rev_001"],
  "content_version": "v1",
  "difficulty": "medium",
  "bloom_level": "understand",
  "quality_status": "passed",
  "quality_report": {
    "status": "passed",
    "score": 0.9,
    "source_grounded": true,
    "flags": [],
    "reasons": []
  },
  "payload": {
    "front": "뉴턴 제2법칙에서 힘은 무엇과 관련되는가?",
    "back": "질량과 가속도와 관련된다.",
    "hint": "F = ma를 떠올려봐.",
    "explanation": "자료에서는 힘이 질량과 가속도의 곱으로 표현된다고 설명한다."
  }
}
```

중요 정책:

- 양보다 질을 우선한다. 한 번의 학습 콘텐츠 생성 요청은 최대 10개까지 허용한다.
- 모든 콘텐츠는 `document_id`, `concepts`, `source_chunk_ids`, `quality_status`, `quality_report`를 가져야 한다.
- `source_chunk_ids`가 없는 콘텐츠는 저장/반환하지 않는다.
- `quality_report.status`는 `quality_status`와 일치해야 한다.
- 콘텐츠는 Vector DB를 직접 조회하지 않고, Search/RAG Module이 반환한 chunk만 근거로 사용한다.
- `source_revision_ids`와 `content_version`은 Edit Agent 또는 문서 갱신 이후 재검증/재생성이 필요한지 판단하기 위한 후보 metadata다.
- 제출/채점이 필요한 콘텐츠와 필요 없는 콘텐츠는 `interaction_mode`로 구분한다.
- 생성 콘텐츠는 저장 전 `LearningContentQualityChecker`를 통과해야 한다.
- `LearningContentAgent`가 만든 후보의 `quality_report.action`은 기본적으로 `validate_before_save`이며, 이 값은 저장 허가가 아니라 저장 전 검증 필요 상태를 뜻한다.
- 자료 근거가 약하거나, 자료에 없는 수치를 포함하거나, 원문을 70자 이상 연속 복제한 콘텐츠는 저장하지 않는다.
- OX 문제처럼 짧은 콘텐츠도 너무 일반적인 문장이면 저장하지 않는다.
- 현재 직접 생성 가능한 콘텐츠는 `flashcard`, `cloze`, `true_false`, `ordering`, `matching`, `worked_example`, `concept_summary_card`다.
- `mistake_drill`과 `mini_exam`은 일반 생성 API가 아니라 별도 workflow API에서 생성한다.
- 내부 저장 payload와 사용자 표시 payload는 분리한다.
- `auto_gradable` 콘텐츠의 정답 필드는 API 응답에서 기본적으로 숨긴다.
- `cloze` 응답은 `prompt`만 표시하고, `answer`, `acceptable_answers`, `explanation`은 숨긴다.
- `true_false` 응답은 `statement`만 표시하고, `answer`, `correction`, `explanation`은 숨긴다.
- `ordering` 응답은 `prompt`, `items`만 표시하고, `correct_order`, `explanation`은 숨긴다.
- `matching` 응답은 정답 pair를 숨기고 `left_items`, `right_items`로 나눠 표시한다.
- 정답이 숨겨진 콘텐츠 응답에는 `private_payload_available=true`를 표시한다.

interaction mode:

```text
study_only:
  개념 카드, 풀이 예시, 개념 확인 카드처럼 채점 없이 보는 콘텐츠

auto_gradable:
  빈칸 문제, OX 문제, 순서 배열 문제, 짝 맞추기 문제처럼 코드 채점이 가능한 콘텐츠

problem_linked:
  오답 맞춤 연습처럼 기존 문제/피드백과 연결되는 콘텐츠

problem_set:
  미니 모의고사처럼 여러 문제/콘텐츠를 묶는 콘텐츠
```

현재 코드 기준:

- 스키마 위치: `app/schemas/learning_contents.py`
- 생성 후보 Agent 위치: `app/agents/learning_content_agent.py`
- 결정적 품질 검증기 위치: `app/agents/learning_content_quality_checker.py`
- 테스트 위치: `tests/test_learning_content_contracts.py`
- 생성 후보 테스트 위치: `tests/test_learning_content_agent.py`
- 생성 서비스 위치: `app/services/learning_content_service.py`
- 1차 API 위치: `app/api/learning_contents.py`
- 로컬 repository 위치: `app/repositories/learning_content_repository.py`
- API 테스트 위치: `tests/test_learning_content_api.py`

1차 API:

```text
POST /api/learning-contents/generate
GET /api/learning-contents/{content_id}
POST /api/learning-contents/mistake-drills/generate
POST /api/learning-contents/mini-exams/generate
```

주의:

- 현재 repository는 Content DB 최종 구현이 아니라 로컬 검증용 경계다.
- Content DB 담당 파트가 준비되면 같은 repository/client interface 뒤쪽 구현만 교체한다.
- 일반 생성 API는 직접 생성 가능한 콘텐츠만 처리한다.
- `mistake_drill`은 `POST /api/learning-contents/mistake-drills/generate`로만 생성한다.
- 오답 맞춤 연습은 기존 `feedback_id`를 받아 오답 유형과 약점 개념을 읽고, 실제로 풀 수 있는 새 `Problem`을 생성한 뒤 `payload.generated_problem_id`에 연결한다.
- `mini_exam`은 `POST /api/learning-contents/mini-exams/generate`로만 생성한다.
- 미니 모의고사는 먼저 자료 기반 문제를 생성하고, `payload.items[].problem_id`에 생성된 문제 ID를 연결한다.

오답 맞춤 연습 요청 예시:

```json
{
  "feedback_id": "fb_001",
  "count": 1,
  "variant_strategy": "same_concept_new_condition"
}
```

오답 맞춤 연습 payload 예시:

```json
{
  "content_type": "mistake_drill",
  "interaction_mode": "problem_linked",
  "payload": {
    "seed_problem_id": "prob_001",
    "seed_feedback_id": "fb_001",
    "target_mistake_type": "concept_misunderstanding",
    "target_concepts": ["뉴턴 제2법칙"],
    "variant_strategy": "same_concept_new_condition",
    "variant_focus": "$F = ma$ 관계로 다시 확인한다.",
    "selected_choice_id": "C",
    "selected_choice_text": "가속도는 항상 0이다.",
    "misconception": "가속도를 항상 0으로 본 점.",
    "repair_strategy": "$F = ma$ 관계로 다시 확인한다.",
    "generated_problem_id": "prob_002"
  }
}
```

미니 모의고사 요청 예시:

```json
{
  "document_id": "doc_001",
  "concepts": ["뉴턴 제2법칙"],
  "count": 5,
  "problem_type": "multiple_choice",
  "difficulty": "medium",
  "bloom_level": "understand",
  "title": "뉴턴 제2법칙 미니 점검"
}
```

미니 모의고사 payload 예시:

```json
{
  "content_type": "mini_exam",
  "interaction_mode": "problem_set",
  "payload": {
    "title": "뉴턴 제2법칙 미니 점검",
    "items": [
      {
        "problem_id": "prob_001",
        "content_type": "multiple_choice",
        "points": 1
      }
    ],
    "blueprint": {
      "total_count": 1,
      "concepts": ["뉴턴 제2법칙"],
      "problem_type": "multiple_choice"
    }
  }
}
```

---

## 3. 박준 파트가 기대하는 repository/client interface

최종 통합 시 박준 파트는 아래 동작만 필요하다.

```text
ProblemStore.create(problem_payload) -> Problem
ProblemStore.get(problem_id) -> Problem | None

LearningContentStore.create(content_payload) -> LearningContent
LearningContentStore.get(content_id) -> LearningContent | None

SubmissionStore.create(submission_payload) -> Submission

FeedbackStore.create(feedback_payload) -> Feedback
FeedbackStore.get(feedback_id) -> Feedback | None

UserConceptUpdatePublisher.publish(update_payload) -> None

SearchClient.search_chunks(request) -> list[RetrievedChunk]
SearchClient.get_chunks_by_ids(request) -> list[RetrievedChunk]
```

현재 구현의 SQLAlchemy repository는 위 interface의 로컬 테스트용 구현이다.

---

## 4. 팀별 연동 체크리스트

### 4.1 조유찬: 자료 생성 + 로드맵

자료 생성 파트가 Search/Vector DB로 넘겨야 하는 최소 chunk 필드:

- [x] `chunk_id`: 문서 안에서 유일한 chunk 식별자
- [x] `document_id`: 사용자가 업로드한 자료 식별자
- [x] `content`: 문제 생성/채점에 사용할 원문 또는 구조화 설명 텍스트
- [x] `page`: PDF/교재 기준 페이지, 없으면 `null`
- [x] `section_title`: 섹션명, 없으면 `null`
- [x] `concepts`: chunk와 연결된 핵심 개념 목록
- [ ] `tags`: subject, content form, 자료 구조를 나타내는 가벼운 태그
- [ ] `metadata`: `content_forms`, `subject_domain`, `source_type` 등 추천에 필요한 구조화 정보

박준 파트가 기대하는 조건:

- `content`는 문제를 만들 수 있을 만큼 충분히 구체적이어야 한다.
- `tags`와 `metadata`는 저장용 대분류보다 즉시 추천에 쓸 수 있는 작고 일관된 값이면 충분하다.
- chunk 안에 prompt instruction처럼 보이는 문장이 있어도 박준 파트는 이를 명령으로 따르지 않는다.
- 로드맵 파트는 `UserConceptUpdatePayload`의 `weak_concepts`, `recommended_review`, `mastery_updates`를 받아 복습 계획에 반영할 수 있다.

### 4.2 김태훈: DB + Search

Search Agent 필수 endpoint:

- [x] `POST /search`
- [x] `POST /chunks/batch`

Search Agent 응답 검증은 박준 파트에서도 한 번 더 수행한다.

- `/search` 응답의 모든 chunk는 요청한 `document_id`와 같아야 한다.
- `/search` 응답의 `chunk_id`는 가능하면 중복되지 않아야 한다. 중복되면 박준 파트는 첫 결과만 사용하고 나머지는 제거한다.
- `/chunks/batch`는 요청한 `chunk_ids`만 반환해야 한다.
- `/chunks/batch`가 extra chunk, duplicate chunk, 다른 문서 chunk를 반환하면 박준 파트 API는 `503`으로 실패한다.
- `/chunks/batch` 응답 순서가 달라도 박준 파트는 저장된 `source_chunk_ids` 순서로 context를 재정렬한다.

DB/저장소 통합 시 권장 제약:

- `feedbacks.submission_id`는 unique여야 한다.
- `problem_id + user_id` 기준으로 성공 피드백이 이미 있으면 재제출을 막아야 한다.
- `Problem.answer`, `Problem.explanation`, `Problem.choice_explanations`, `Problem.rubric`은 서버에는 저장하되 제출 전 프론트 응답에서는 숨긴다.
- `source_chunk_ids`는 빈 배열이면 안 된다.

현재 로컬 SQLAlchemy 구현은 테스트/데모용이다. 실제 운영 저장소 구현은 김태훈 파트가 확정하되, 위 payload를 저장/조회할 수 있어야 한다.

### 4.3 왕호진: 사용자 계정/개인정보 DB

박준 파트 API는 현재 `X-User-Id` 헤더로 사용자 식별자를 받는다.

운영 통합 시 정책:

- 클라이언트가 직접 임의의 `X-User-Id`를 보내는 구조가 아니어야 한다.
- 인증/세션 검증 후 API gateway 또는 백엔드 middleware가 내부 `user_id`를 주입해야 한다.
- OpenAI에는 원문 `user_id`를 보내지 않고 해시 기반 `safety_identifier`만 전달한다.
- 사용자 개인정보 저장/삭제/보존 정책은 왕호진 파트가 소유한다.

User Model 업데이트 방식:

- 박준 파트는 사용자 DB를 직접 수정하지 않는다.
- `submit_answer_with_update()`는 `UserConceptUpdatePayload`를 만든다.
- 실제 통합에서는 `UserConceptUpdatePublisher.publish(update_payload)` 또는 동일한 event bus/queue 계약으로 전달한다.
- 로컬 `UserConceptStatRepository`는 MVP 테스트용 상태 저장소다.

문제 품질 개선용 aggregate 통계:

- `ProblemItemStatPayload`는 특정 사용자의 개인정보가 아니라 문제 품질 개선용 집계 데이터 계약이다.
- 포함 가능한 값은 정답률, 평균 점수, 보기별 선택 수, 오답 유형 수처럼 비식별 aggregate 중심이다.
- 객관식은 선택지별 오답 유형 집계인 `choice_mistake_type_counts`를 포함할 수 있다.
- 개별 제출 이벤트는 `ProblemItemAttemptPayload`로 전달하고, 이 payload에는 객관식 `choice_diagnostic`이 포함될 수 있다.
- user-level 학습 이력과 개인정보 저장 정책은 왕호진 파트와 맞춘다.

개별 제출 이벤트 예시:

```json
{
  "user_id": "user_001",
  "problem_id": "prob_001",
  "document_id": "doc_001",
  "submission_id": "sub_001",
  "feedback_id": "fb_001",
  "problem_type": "multiple_choice",
  "is_correct": false,
  "score": 0,
  "max_score": 1,
  "selected_choice_id": "C",
  "mistake_type": "concept_misunderstanding",
  "choice_diagnostic": {
    "selected_choice_id": "C",
    "selected_choice_text": "가속도는 항상 0이다.",
    "correct_choice_id": "A",
    "correct_choice_text": "힘은 질량과 가속도의 곱이다.",
    "misconception": "가속도를 항상 0으로 본 점.",
    "repair_strategy": "$F = ma$ 관계로 다시 확인한다.",
    "mistake_type": "concept_misunderstanding"
  }
}
```

문항 집계 예시:

```json
{
  "problem_id": "prob_001",
  "document_id": "doc_001",
  "problem_type": "multiple_choice",
  "total_attempts": 10,
  "correct_count": 6,
  "incorrect_count": 4,
  "average_score": 0.6,
  "max_score": 1,
  "choice_selection_counts": {
    "A": 6,
    "C": 4
  },
  "choice_mistake_type_counts": {
    "C": {
      "concept_misunderstanding": 4
    }
  },
  "mistake_type_counts": {
    "concept_misunderstanding": 4
  }
}
```

### 4.3.1 저작권/자료 사용 정책 계약

사용자 업로드 자료는 기본적으로 해당 사용자 개인 학습 기능 제공에만 사용한다.

팀 공통으로 지켜야 할 정책:

- 업로드 원본, chunk, embedding, 생성 문제, 피드백은 `user_id + document_id` 범위에 묶는다.
- 다른 사용자의 문제 생성, 공용 문제 은행, 모델 학습/fine-tuning, eval set, benchmark에 재사용하지 않는다.
- 재사용이 필요한 경우에는 별도 동의와 권리 확인 절차가 필요하다.
- 사용자가 자료 삭제를 요청하면 원본, chunk, embedding, 해당 자료에서 생성된 문제/피드백 삭제 또는 비식별 aggregate 전환 정책을 따라야 한다.
- 운영 로그에는 raw source chunk와 원문에 가까운 긴 발췌를 남기지 않는다.

박준 파트 구현 요구사항:

- 문제/해설/피드백 생성 시 원문을 길게 그대로 복제하지 않는다.
- `source_chunk_ids`는 근거 연결용으로만 사용하고, 프론트 응답에 원문 장문을 노출하지 않는다.
- `ProblemQualityChecker`에서 source와 생성 산출물 간 긴 연속 문자열 overlap을 검사하는 기능을 추가한다.
- strict 모드에서 원문 복제 의심 문항은 저장하지 않는다.

담당 경계:

- 약관, 개인정보처리방침, 삭제 보존 정책의 최종 소유는 계정/개인정보 DB 파트와 서비스 운영 파트다.
- 박준 파트는 문제 생성/피드백 산출물에서 저작권 리스크를 줄이는 검증과 계약만 담당한다.

### 4.4 한상훈: 질의응답 + Guard + Personalization

Guard/Personalization은 박준 파트 내부 구현 범위가 아니다.

연동 지점:

- 문제 생성 요청 전 Guard가 부적절한 요청을 차단할 수 있다.
- 답안 제출 전 Guard가 위험/비교육적 입력을 차단할 수 있다.
- Personalization Agent는 피드백 문장을 사용자 수준에 맞게 조정할 수 있다.
- 단, 객관식 채점 결과와 주관식 rubric 점수는 Personalization이 바꾸면 안 된다.

### 4.5 프론트엔드

프론트가 반드시 지켜야 하는 UI/API 정책:

- 제출 전 문제 화면에는 `answer`, `explanation`, `choice_explanations`, `rubric`을 표시하지 않는다.
- 제출 전 자동 채점 학습 콘텐츠 화면에는 `answer`, `acceptable_answers`, `correct_order`, 정답 pair, `correction`, `explanation`을 표시하지 않는다.
- 객관식 제출에는 `answer.choice_id`가 필요하다.
- 주관식 제출에는 `answer.text` 또는 `input_mode=tablet_ocr` + `ocr_text`가 필요하다.
- 한 문제를 제출한 뒤 같은 문제를 다시 제출하면 `409`가 반환된다.
- 제출 성공 후 `GET /api/problems/{problem_id}`를 다시 호출하면 정답/해설이 포함된다.

---

## 5. 프론트엔드 응답 예시

### 5.1 제출 전 문제 응답

```json
{
  "id": "prob_001",
  "document_id": "doc_001",
  "type": "multiple_choice",
  "difficulty": "medium",
  "bloom_level": "understand",
  "question": "뉴턴의 제2법칙에 대한 설명으로 가장 적절한 것은?",
  "choices": [
    { "id": "A", "text": "알짜힘은 질량과 가속도의 곱이다." },
    { "id": "B", "text": "외부 힘이 없어도 항상 가속한다." },
    { "id": "C", "text": "질량이 클수록 같은 힘에서 가속도는 커진다." },
    { "id": "D", "text": "힘은 항상 속도와 같은 방향이다." }
  ],
  "concepts": ["뉴턴 제2법칙"],
  "source_chunk_ids": ["chunk_001"],
  "quality_status": "passed",
  "created_at": "2026-05-06T00:00:00Z",
  "explanation": null,
  "answer": null,
  "choice_explanations": null,
  "rubric": null
}
```

### 5.2 피드백 응답

```json
{
  "id": "fb_001",
  "submission_id": "sub_001",
  "problem_id": "prob_001",
  "is_correct": false,
  "score": 0,
  "max_score": 1,
  "mistake_type": "concept_misunderstanding",
  "weak_concepts": ["뉴턴 제2법칙"],
  "summary": "핵심 개념을 조금 다르게 이해했어.",
  "feedback": "정답 여부: 아직 정답은 아니야.\n헷갈린 지점: 뉴턴 제2법칙 부분을 헷갈린 것 같아.\n올바른 개념: 정답은 A야. 자료 내용과 일치한다.\n복습 추천: 뉴턴 제2법칙",
  "recommended_review": ["뉴턴 제2법칙"],
  "source_chunk_ids": ["chunk_001"],
  "created_at": "2026-05-06T00:00:00Z"
}
```

### 5.3 제출 후 문제 응답

```json
{
  "id": "prob_001",
  "document_id": "doc_001",
  "type": "multiple_choice",
  "difficulty": "medium",
  "bloom_level": "understand",
  "question": "뉴턴의 제2법칙에 대한 설명으로 가장 적절한 것은?",
  "choices": [
    { "id": "A", "text": "알짜힘은 질량과 가속도의 곱이다." },
    { "id": "B", "text": "외부 힘이 없어도 항상 가속한다." },
    { "id": "C", "text": "질량이 클수록 같은 힘에서 가속도는 커진다." },
    { "id": "D", "text": "힘은 항상 속도와 같은 방향이다." }
  ],
  "concepts": ["뉴턴 제2법칙"],
  "source_chunk_ids": ["chunk_001"],
  "quality_status": "passed",
  "created_at": "2026-05-06T00:00:00Z",
  "explanation": "뉴턴의 제2법칙은 F = ma로 표현된다.",
  "answer": { "choice_id": "A", "text": "알짜힘은 질량과 가속도의 곱이다." },
  "choice_explanations": {
    "A": "자료 내용과 일치한다.",
    "B": "자료 근거가 없는 설명이다.",
    "C": "자료의 질량과 가속도 관계를 반대로 설명한다.",
    "D": "자료에서 설명한 법칙과 직접 관련이 없다."
  },
  "rubric": null
}
```

### 5.4 주요 오류 응답

```json
{ "detail": "X-User-Id header is required" }
```

```json
{ "detail": "Problem not found" }
```

```json
{ "detail": "Problem already submitted" }
```

```json
{ "detail": "Search Agent returned chunks from a different document: chunk_001" }
```

권장 프론트 처리:

- `401`: 로그인/세션 재확인
- `404`: 문제 또는 피드백 접근 권한 없음
- `409`: 이미 제출된 문제이므로 피드백/해설 화면으로 이동
- `422`: 입력 형식 오류 표시
- `503`: Search Agent/자료 연결 문제로 재시도 안내

---

## 6. 최종 통합 전 결정해야 할 항목

- User DB 업데이트 전달 방식: 직접 함수 호출, HTTP callback, queue/event bus 중 선택
- 김태훈 저장소 제약: `problem_id + user_id` 재제출 차단을 저장소 제약으로도 둘지 결정
- Search Agent 오류 payload 표준화: `code`, `message`, `retryable` 포함 여부 결정
- Guard Agent가 문제 생성/답안 제출 전 어느 계층에서 실행될지 결정
- OCR/vision 결과의 이미지 URL 보존 기간과 개인정보 정책 결정
