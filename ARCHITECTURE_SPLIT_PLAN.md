# Frontend / Main Server / RAG Server 분리 계획

## 목표

현재 `ontutor_total`에는 Next.js frontend와 여러 FastAPI agent/backend 코드가 섞여 있다.  
최종 목표는 다음처럼 역할을 명확히 분리하는 것이다.

```text
ontutor_total/
  ontutor/       # Frontend: Next.js UI
  main_server/   # Main API Server: orchestration, user-facing backend API
  rag_server/    # RAG Server: parsing, chunking, embedding, retrieval
```

요청 흐름은 아래처럼 단순화한다.

```text
Browser
  -> ontutor frontend
  -> main_server
  -> rag_server
```

frontend는 RAG server를 직접 호출하지 않는다. frontend는 main server만 알고, main server가 필요할 때 RAG server를 내부 호출한다.

## 현재 확인된 상태

### `ontutor/`

- Next.js frontend 중심 프로젝트다.
- 주요 파일:
  - `app/`
  - `app/api/`
  - `lib/`
  - `package.json`
  - `next.config.js`
- 현재 `lib/agentGateway.js`는 agent별 URL을 직접 사용한다.
  - `TUTOR_AGENT_URL`
  - `DOCUMENT_AGENT_URL`
  - `PROBLEM_AGENT_URL`
  - `ROADMAP_AGENT_URL`
  - `RAG_AGENT_URL`
- `ontutor` 안에도 일부 Python agent 코드가 남아 있다.
  - `document_agent/`
  - `rag_agent/`
  - `problem_agent/`
  - `tutor_agent/`

### `study_agent/`

- backend agent 중심 프로젝트다.
- 현재 `study_agent/server.py`는 여러 agent를 하나의 FastAPI 앱에 mount한다.

```text
/api/document  -> Document Agent
/api/rag       -> RAG Agent
/api/roadmap   -> Roadmap Agent
/api/problem   -> Problem Agent
/api/tutor     -> Tutor Agent
```

- `study_agent/rag_agent/server.py`는 RAG server를 단독 실행할 수 있는 구조다.
- `study_agent` 안에도 일부 frontend 파일이 남아 있다.
  - `app/`
  - `lib/`
  - `package.json`
  - `next.config.js`

## 최종 역할 분리

### `ontutor/` - Frontend

담당:

- 화면 구성
- 로그인 UI
- 업로드 UI
- 문서 뷰어
- 퀴즈/로드맵/분석 화면
- Next.js App Router

제거 또는 이동 후보:

- Python agent 코드
- vector DB 코드
- backend 서버 실행 코드

frontend는 main server만 호출한다.

```env
MAIN_API_BASE_URL=http://127.0.0.1:8000
```

브라우저에서 직접 필요한 공개 값만 `NEXT_PUBLIC_*`로 둔다.

### `main_server/` - Main API Server

담당:

- frontend용 API
- 인증된 사용자 기준 요청 처리
- document/problem/tutor/roadmap orchestration
- Supabase DB/Storage 연동
- RAG server HTTP 호출
- agent status aggregation
- validation/fallback 처리

예상 API:

```text
GET  /health
GET  /api/agents/status
POST /api/documents/upload
GET  /api/documents
GET  /api/documents/{id}
POST /api/ask
POST /api/quizzes
POST /api/attempts
GET  /api/roadmap
GET  /api/analytics
```

main server는 RAG 코드를 직접 import하지 않고 HTTP로 호출한다.

```env
API_HOST=0.0.0.0
API_PORT=8000
RAG_SERVER_URL=http://127.0.0.1:8001
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

### `rag_server/` - RAG Server

담당:

- 문서 parsing
- chunking
- embedding
- vector DB 저장
- semantic search
- filter 기반 chunk fetch
- reranking
- OCR/multimodal retrieval
- ingest job 상태 관리

기존 `study_agent/rag_agent`를 기반으로 독립화한다.

API prefix는 기존 구조와 호환되도록 `/api/rag`를 유지하는 방향을 우선 검토한다.

예상 API:

```text
GET  /health
POST /api/rag/search
POST /api/rag/fetch
POST /api/rag/add
GET  /api/rag/jobs/{job_id}
GET  /api/rag/titles
POST /api/rag/feedback
```

환경변수:

```env
API_HOST=0.0.0.0
API_PORT=8001
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_EMBEDDING_MODEL=embeddinggemma
```

## 설계 원칙

1. frontend는 main server만 호출한다.
2. main server는 RAG server를 HTTP API로 호출한다.
3. RAG server는 frontend 인증/화면 상태를 모른다.
4. RAG server는 retrieval과 vector DB 책임만 가진다.
5. agent별 내부 구현은 가능하면 main server 뒤에 숨긴다.
6. 나중에 RAG server를 GPU 서버, 별도 컨테이너, 별도 배포 환경으로 옮길 수 있게 한다.

## 작업 순서

### 1. 파일 분류

먼저 삭제하지 않고 아래 기준으로 목록을 만든다.

```text
유지: frontend
유지: main server
유지: rag server
이동 필요
삭제 후보
중복/검토 필요
```

확인 대상:

- `ontutor` 안의 Python agent 코드
- `study_agent` 안의 Next.js frontend 코드
- agent별 `server.py`, `main.py`, `routes.py`
- frontend의 `app/api/*`
- frontend의 `lib/agentGateway.js`

### 2. RAG server 독립화

- 기존 `study_agent/rag_agent/server.py`를 기준으로 독립 실행 확인
- 기본 포트를 `8001`로 설정
- `/health` 또는 `/api/rag/health` 추가
- `/api/rag` prefix 유지 여부 확정
- RAG server 단독 실행 테스트

예상 실행:

```bash
cd rag_server
python server.py
```

### 3. Main server 구성

- 기존 `study_agent/server.py`에서 RAG mount 제거
- RAG 기능은 직접 import하지 않고 `RAG_SERVER_URL`로 HTTP 호출
- document/tutor/problem/roadmap 관련 API를 main server 책임으로 정리
- `GET /api/agents/status`에서 main server와 RAG server 상태를 함께 확인

예상 실행:

```bash
cd main_server
python server.py
```

### 4. Frontend 연결 변경

- `ontutor/lib/agentGateway.js`에서 agent별 직접 URL 의존 제거
- frontend는 main server 단일 URL만 사용
- 가능하면 Next.js `app/api/*`는 main server proxy 역할로 단순화
- `RAG_AGENT_URL`, `TUTOR_AGENT_URL`, `DOCUMENT_AGENT_URL`, `PROBLEM_AGENT_URL`, `ROADMAP_AGENT_URL`은 frontend env에서 제거

예상 실행:

```bash
cd ontutor
npm run dev
```

### 5. 중복 파일 정리

정상 동작 확인 후 정리한다.

`ontutor`에서 제거 후보:

- `document_agent/`
- `rag_agent/`
- `problem_agent/`
- `tutor_agent/`

`study_agent` 또는 분리 후 backend 쪽에서 제거 후보:

- `app/`
- `lib/`
- `package.json`
- `package-lock.json`
- `next.config.js`

삭제 전에는 git 상태와 파일 사용 여부를 반드시 확인한다.

### 6. 검증

RAG server:

```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/api/rag/titles
```

Main server:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/agents/status
```

Frontend:

```bash
cd ontutor
npm run check
npm run build
```

수동 플로우:

```text
1. frontend 접속
2. 문서 업로드
3. main server가 RAG server로 ingest 요청
4. RAG job 완료 확인
5. 문서 기반 질문
6. main server가 RAG search 후 tutor/problem/roadmap 흐름 처리
```

## 예상 포트

```text
Frontend    : http://127.0.0.1:4173
Main server : http://127.0.0.1:8000
RAG server  : http://127.0.0.1:8001
Ollama      : http://127.0.0.1:11434
```

## 주의사항

- 바로 삭제하지 않는다. 먼저 분류표를 만들고 import/API 사용 여부를 확인한다.
- 사용자 변경사항을 되돌리지 않는다.
- frontend에서 RAG server를 직접 호출하지 않는다.
- main server와 RAG server 사이의 계약은 HTTP API와 schema로 고정한다.
- `RAG_SERVER_URL`은 main server의 private env로만 둔다.
- CORS는 frontend -> main server에만 필요하게 설계한다.
- RAG server는 내부 서비스로 두는 것을 기본으로 한다.

## 다음 작업

다음 단계에서는 실제 파일을 읽어 아래 산출물을 만든다.

```text
1. 파일 분류표
2. 이동/삭제 후보 목록
3. main server와 RAG server API 계약
4. frontend API 연결 변경 목록
5. 실행 및 검증 명령
```
