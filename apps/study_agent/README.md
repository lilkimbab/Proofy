# AI 과외 선생님

사용자가 업로드한 학습 자료를 기반으로 개인 맞춤형 학습을 제공하는 AI 학습 서비스입니다.

이 저장소는 기존 프론트엔드와 백엔드 코드를 유지하면서, `main_server`와 `rag_server`를 분리해 실행할 수 있도록 정리한 버전입니다.

```text
study_agent/
  app/           # Next.js frontend
  lib/           # frontend helper
  document_agent/
  roadmap_agent/
  problem_agent/
  tutor_agent/
  rag_agent/
  main_server/   # frontend-facing backend entrypoint
  rag_server/    # RAG server entrypoint
```

## 주요 기능

- Supabase Auth 기반 로그인/회원가입
- 학습 자료 업로드
- PDF/TXT/MD 텍스트 추출
- 섹션 분리 및 chunk 생성
- Ollama 기반 로컬 AI 답변
- 문서 기반 RAG 질문 답변
- 드래그 질문/메모
- 문서 위 질문/메모 표시
- 이어 질문
- 문제 생성
- 답안 제출 및 피드백
- 학습 로드맵
- 학습 분석

## 기술 스택

- Next.js App Router
- React
- Supabase Auth
- Supabase Postgres
- Supabase Storage
- Ollama
- pdf-parse

## 실행 방법

### 1. 의존성 설치

```bash
npm install
```

### 2. 환경 변수 설정

프로젝트 루트에 `.env.local` 파일을 만듭니다.

```bash
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_STORAGE_BUCKET=study-files

AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_EMBEDDING_MODEL=embeddinggemma
OLLAMA_CHAT_MODEL=gemma3:4b

MAIN_API_BASE_URL=http://127.0.0.1:8000
RAG_SERVER_URL=http://127.0.0.1:8001
```

주의:

- `SUPABASE_SERVICE_ROLE_KEY`는 절대 GitHub에 올리면 안 됩니다.
- `.env.local`은 `.gitignore`에 포함되어 있습니다.
- `SUPABASE_ANON_KEY`는 로그인 클라이언트에서 사용됩니다.

### 3. Supabase 설정

Supabase 프로젝트를 만든 뒤 SQL Editor에서 아래 파일을 순서대로 실행합니다.

```text
SUPABASE_SCHEMA.sql
SUPABASE_MIGRATION_INTERACTIVE_QUESTIONS.sql
SUPABASE_MIGRATION_ANNOTATIONS.sql
SUPABASE_MIGRATION_EMBEDDING_JSON.sql
```

Storage에서 버킷도 만들어야 합니다.

```text
bucket name: study-files
```

Supabase Auth 설정:

1. Supabase Dashboard로 이동
2. Authentication → Providers
3. Email provider 활성화
4. 개발 중이면 Confirm email을 꺼도 됩니다.
5. 실제 서비스에서는 Confirm email을 켜고 Site URL/Redirect URLs를 설정합니다.

자세한 내용은 [AUTH_SETUP.md](./AUTH_SETUP.md), [DB_SETUP.md](./DB_SETUP.md)를 참고하세요.

### 4. Ollama 설치 및 모델 준비

Ollama가 설치되어 있어야 합니다.

MacBook RAM 16GB 기준 권장 모델:

```bash
ollama pull embeddinggemma
ollama pull gemma3:4b
ollama serve
```

이미 Ollama가 실행 중이면 `ollama serve`는 생략해도 됩니다.

자세한 내용은 [OLLAMA_SETUP.md](./OLLAMA_SETUP.md)를 참고하세요.

### 5. Backend 서버 실행

RAG server를 먼저 실행하고, 그다음 main server를 실행합니다.

```bash
cd rag_server
python3 server.py
```

```bash
cd main_server
python3 server.py
```

기본 주소:

```text
RAG server:  http://127.0.0.1:8001
Main server: http://127.0.0.1:8000
```

### 6. Frontend 개발 서버 실행

```bash
npm run dev
```

브라우저에서 접속합니다.

```text
http://127.0.0.1:4173
```

처음 화면은 로그인 화면입니다.

계정을 만들어 로그인하거나, `게스트로 둘러보기`를 눌러 샘플 상태로 확인할 수 있습니다.

## 빌드 확인

```bash
npm run build
```

## API 확인

개발 서버가 실행 중일 때 확인할 수 있습니다.

```bash
curl -sS http://127.0.0.1:4173/api/auth/session
curl -sS http://127.0.0.1:4173/api/agents/status
curl -sS http://127.0.0.1:4173/api/documents
curl -sS http://127.0.0.1:4173/api/roadmap
curl -sS http://127.0.0.1:4173/api/analytics
```

## 프로젝트 구조

```text
app/
  api/
    annotations/
    ask/
    attempts/
    auth/
    documents/
    questions/
    quizzes/
    roadmap/
    sections/
  page.jsx
  globals.css

lib/
  aiClient.js
  annotationStore.js
  auth.js
  documentProcessor.js
  fileStorage.js
  quizEngine.js
  rag.js
  store.js
  studyPlanner.js
  supabaseAdmin.js
  supabaseBrowser.js

main_server/
  server.py

rag_server/
  server.py

SUPABASE_SCHEMA.sql
SUPABASE_MIGRATION_*.sql
SERVICE_BLUEPRINT.md
SERVICE_LAUNCH_CHECKLIST.md
```

## 핵심 동작 흐름

```text
로그인
→ 자료 업로드
→ 텍스트 추출
→ 섹션 분리
→ chunk 생성
→ embedding 생성
→ 학습 화면
→ 드래그 질문/메모
→ RAG 답변
→ 문제 생성
→ 풀이 피드백
→ 학습 분석
```

## 긴 자료 처리 방식

긴 문서를 한 번에 AI에 넣지 않습니다.

```text
전체 문서
→ 섹션 분리
→ chunk 분리
→ chunk별 embedding
→ 질문 시 관련 chunk만 검색
→ 선택 텍스트와 함께 답변 생성
```

이 방식으로 토큰 낭비와 컨텍스트 초과 문제를 줄입니다.

## 현재 구현 상태

구현 완료:

- 로그인/회원가입
- 문서 업로드
- 섹션 분리
- Ollama RAG 답변
- 드래그 질문/메모
- 질문/메모 기록
- 이어 질문
- 문제 생성
- 피드백
- 학습 로드맵
- 학습 분석

확장 필요:

- DOCX/PPTX 본문 추출
- OCR
- Supabase RLS 정책
- 비밀번호 재설정 UI
- 소셜 로그인
- background job queue
- 실제 배포 환경 AI 서버
- 결제/요금제

## 참고 문서

- [SERVICE_BLUEPRINT.md](./SERVICE_BLUEPRINT.md)
- [SERVICE_LAUNCH_CHECKLIST.md](./SERVICE_LAUNCH_CHECKLIST.md)
- [AUTH_SETUP.md](./AUTH_SETUP.md)
- [DB_SETUP.md](./DB_SETUP.md)
- [OLLAMA_SETUP.md](./OLLAMA_SETUP.md)
- [IMPLEMENTATION.md](./IMPLEMENTATION.md)
