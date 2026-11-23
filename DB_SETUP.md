# Supabase DB 연결 방법

## 1. Supabase SQL 실행

Supabase 프로젝트의 SQL Editor에서 `SUPABASE_SCHEMA.sql` 내용을 실행합니다.

생성되는 핵심 테이블:

- `documents`
- `document_sections`
- `document_chunks`
- `questions`

그리고 `pgvector` 검색 함수 `match_document_chunks`가 생성됩니다.

이미 기본 스키마를 만든 뒤라면 추가 마이그레이션도 실행합니다.

- `SUPABASE_MIGRATION_INTERACTIVE_QUESTIONS.sql`: 질문 기록에 선택 영역 정보를 추가합니다.
- `SUPABASE_MIGRATION_ANNOTATIONS.sql`: 문서 위 질문/메모 기록 테이블을 추가합니다.
- `SUPABASE_MIGRATION_EMBEDDING_JSON.sql`: Ollama처럼 1536차원이 아닌 embedding도 저장할 수 있게 합니다.

## 2. 환경변수 설정

프로젝트 루트에 `.env.local`을 만들고 아래 값을 입력합니다.

```env
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_STORAGE_BUCKET=study-files

OPENAI_API_KEY=
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_CHAT_MODEL=gpt-4.1-mini
```

`OPENAI_API_KEY`는 아직 비워둬도 됩니다.

## 2-1. Storage 버킷

Supabase Storage에서 `study-files` 버킷을 만듭니다. 다른 이름을 쓰려면 `SUPABASE_STORAGE_BUCKET` 값을 바꾸면 됩니다.

## 3. 저장소 동작 방식

- `SUPABASE_URL`과 `SUPABASE_SERVICE_ROLE_KEY`가 있으면 Supabase DB를 사용합니다.
- 둘 중 하나라도 없으면 기존 `data/study-agent.json` 로컬 저장소를 사용합니다.

## 4. 주의

`SUPABASE_SERVICE_ROLE_KEY`는 서버 API에서만 사용해야 합니다. 브라우저 컴포넌트로 전달하면 안 됩니다.

## 5. Auth 연결

서버 API는 `Authorization: Bearer <supabase-access-token>` 헤더가 오면 Supabase Auth의 현재 사용자로 데이터를 분리합니다.

아직 로그인 UI를 붙이기 전에는 `guest` 사용자로 로컬 fallback이 동작합니다.
