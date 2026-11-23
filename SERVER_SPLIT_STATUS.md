# Server Split Status

## 현재 적용된 구조

```text
ontutor_total/
  ontutor/       # Next.js frontend
  main_server/   # Frontend-facing FastAPI main server
  rag_server/    # Standalone RAG/vector search server
  study_agent/   # 기존 backend 원본 보존
```

## 연결 방향

```text
Browser
  -> ontutor
  -> main_server
  -> rag_server
```

frontend는 `MAIN_API_BASE_URL`만 사용한다. RAG server URL은 main server의 private 환경변수인 `RAG_SERVER_URL`에만 둔다.

## 포트

```text
ontutor     : http://127.0.0.1:4173
main_server : http://127.0.0.1:8000
rag_server  : http://127.0.0.1:8001
```

## 변경 사항

- `main_server/`를 새로 만들고 `document_agent`, `problem_agent`, `roadmap_agent`, `tutor_agent`를 복사했다.
- `main_server/server.py`를 추가했다.
  - `/health`
  - `/api/agents/status`
  - `/api/document`
  - `/api/problem`
  - `/api/roadmap`
  - `/api/tutor`
- `rag_server/`를 새로 만들고 기존 RAG agent를 복사했다.
- `rag_server/api/main.py`에 health endpoint와 `/api/rag` prefix를 추가했다.
  - `/health`
  - `/api/rag/health`
  - `/api/rag/search`
  - `/api/rag/fetch`
  - `/api/rag/add`
  - `/api/rag/jobs/{job_id}`
  - `/api/rag/titles`
- `rag_server/server.py` 기본 포트를 `8001`로 변경했다.
- `main_server/document_agent/core/rag_client.py`가 `RAG_SERVER_URL`을 우선 사용하게 바꿨다.
- `main_server/tutor_agent/app/modules/rag_client.py`가 `RAG_SERVER_URL`을 우선 사용하게 바꿨다.
- `ontutor/lib/agentGateway.js`가 `MAIN_API_BASE_URL` 기준으로 main server를 호출하게 바꿨다.
- `ontutor/app/api/documents/route.js`는 main server의 `/api/document/upload`를 먼저 호출하고 실패하면 기존 Gemini 임시 처리로 fallback한다.
- `ontutor/.env.example`, `main_server/.env.example`, `rag_server/.env.example`를 현재 구조에 맞췄다.

## 실행

권장 Python 버전:

```text
Python 3.11+
```

`problem_agent`가 `pyproject.toml`에서 Python 3.11 이상을 요구한다. 현재 macOS 기본 `/usr/bin/python3`가 3.9라면 별도 Python 3.11 환경을 준비해야 한다.

RAG server:

```bash
cd rag_server
python3 server.py
```

Main server:

```bash
cd main_server
python3 server.py
```

Frontend:

```bash
cd ontutor
npm run dev
```

## 검증

```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/api/rag/health
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/agents/status
curl http://127.0.0.1:4173/api/agents/status
```

## 현재 검증 결과

- JavaScript syntax check 통과:
  - `ontutor/lib/agentGateway.js`
  - `ontutor/app/api/documents/route.js`
- `ontutor`의 `npm run check` 통과
- `ontutor`의 `npm run build` 통과
- Python syntax compile 통과:
  - `main_server/server.py`
  - `rag_server/server.py`
  - `rag_server/api/main.py`
  - `main_server/document_agent/core/rag_client.py`
  - `main_server/tutor_agent/app/modules/rag_client.py`
- 현재 시스템 Python에는 `fastapi`, `httpx`가 설치되어 있지 않아 실제 서버 import/run 검증은 의존성 설치 후 진행해야 한다.
- 현재 시스템 기본 Python은 3.9이고, `problem_agent`는 Python 3.11+가 필요하다.

## 남은 작업

- Python 3.11+ 가상환경 생성 및 backend 의존성 설치
- `main_server`와 `rag_server` 실제 실행 테스트
- 기존 `ontutor` 안의 Python agent 코드 제거 여부 결정
- 기존 `study_agent` 안의 frontend 잔여 파일 제거 여부 결정
- frontend의 local fallback API를 main server 중심으로 더 얇게 정리
