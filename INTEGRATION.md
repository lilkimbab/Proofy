# 에이전트 통합 서버

## 개요

4개의 독립적인 학습 에이전트를 단일 FastAPI 서버에 통합합니다.  
각 에이전트는 고유한 URL 접두사(prefix)로 분리됩니다.

```
mysite.com/api/document  → Document Agent
mysite.com/api/rag       → RAG Agent
mysite.com/api/roadmap   → Roadmap Agent
mysite.com/api/problem   → Problem Agent
mysite.com/api/tutor     → Tutor Agent
```

## 엔드포인트 목록

### Document Agent — `/api/document`

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/document/upload` | 문서 업로드 및 학습 자료 생성 |
| GET | `/api/document/study/{doc_id}` | 생성된 학습 자료 조회 |
| GET | `/api/document/tasks/{task_id}` | 작업 상태 확인 |
| GET | `/api/document/view/{doc_id}` | 비교 학습 뷰어 (HTML) |
| POST | `/api/document/feedback` | 피드백 전송 |

### RAG Agent — `/api/rag`

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/rag/search` | 벡터 DB 의미 검색 |
| POST | `/api/rag/fetch` | 필터 기반 청크 조회 |
| POST | `/api/rag/add` | 문서 인제스트 (백그라운드) |
| GET | `/api/rag/jobs/{job_id}` | 인제스트 작업 상태 |
| GET | `/api/rag/titles` | 등록된 문서 목록 |
| POST | `/api/rag/feedback` | 검색 피드백 기록 |

### Roadmap Agent — `/api/roadmap`

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/roadmap/roadmap/generate` | 학습 로드맵 생성 |
| GET | `/api/roadmap/roadmap/{user_id}` | 로드맵 조회 |
| POST | `/api/roadmap/roadmap/{user_id}/progress` | 진도 업데이트 |

### Problem Agent — `/api/problem`

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/problem/problems` | 문제 생성 |
| GET | `/api/problem/problems/{id}` | 문제 조회 |
| POST | `/api/problem/feedback` | 풀이 피드백 |
| GET | `/api/problem/learning-contents` | 학습 콘텐츠 추천 |

### Tutor Agent — `/api/tutor`

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/tutor/health` | 헬스 체크 |
| POST | `/api/tutor/agents/run` | 에이전트 실행 (agent_type 지정) |
| POST | `/api/tutor/agents/tutor` | 튜터 에이전트 직접 호출 |

## 실행

```bash
# 통합 서버 실행 (기본 포트: 8000)
python server.py

# 포트 변경
API_PORT=9000 python server.py
```

## 기술 구조

### 통합 방식: `app.mount()`

각 에이전트의 FastAPI 앱을 서브 앱으로 마운트합니다.

```
server.py (FastAPI)
├── /api/document  → document_agent/api/main.py:app
├── /api/rag       → rag_agent/api/main.py:app
├── /api/roadmap   → roadmap_agent/api/main.py:app
├── /api/problem   → problem_agent/app/main.py:app
└── /api/tutor     → tutor_agent/app/main.py:app
```

### 모듈 충돌 해결

각 에이전트가 동일한 패키지 이름(`api`, `core`, `app`)을 사용하기 때문에,  
로딩 순서와 `sys.modules` 관리가 중요합니다.

**해결책**: `request.app.state`를 통한 상태 전달

기존에는 라우터 함수 내부에서 `from api.main import manager` 같은 lazy import를 사용했습니다.  
이 방식은 단일 에이전트 서버에서는 동작하지만, 통합 서버에서는 `sys.modules`의 모듈이 덮어씌워져 충돌이 발생합니다.

**수정 전**:
```python
def get_manager():
    from api.main import manager  # sys.modules['api.main'] 에 의존
    return manager
```

**수정 후**:
```python
def get_manager(request: Request):
    return request.app.state.manager  # 앱 인스턴스에 바인딩
```

각 에이전트의 `lifespan`에서 `app.state`에 상태를 저장합니다:
```python
async def lifespan(app: FastAPI):
    app.state.manager = StudyManager()  # 이 앱 인스턴스에만 귀속
    yield
    app.state.manager = None
```

이 방식으로 여러 에이전트가 동일한 프로세스에서 실행되어도 상태가 섞이지 않습니다.

### 로딩 순서

```
1. roadmap_agent  → api.*, core.*  로드
2. rag_agent      → api.*, vector_db.* 로드 (core.* 없음)
3. problem_agent  → app.* 로드
4. tutor_agent    → app.* 로드
5. document_agent → api.*, core.* 로드 (마지막)
```

각 에이전트 로딩 전에 충돌하는 모듈 이름을 `sys.modules`에서 제거합니다.  
라우터 함수는 임포트 시점에 필요한 객체를 이미 바인딩하므로, 로딩 이후 `sys.modules`가 변경되어도 동작에 영향이 없습니다.

## 개별 서버 실행 (기존 방식)

각 에이전트를 독립적으로 실행하는 기존 방식도 유지됩니다.

```bash
python document_agent/server.py   # :8001
python rag_agent/server.py        # :8000
python roadmap_agent/server.py    # :8002
```

```
http://localhost:8002/api/tutor/docs
http://localhost:8002/api/rag/docs
http://localhost:8002/api/document/docs
http://localhost:8002/api/roadmap/docs
http://localhost:8002/api/problem/docs
```
lsof -ti :8000 | xargs kill -9

lsof -ti :8000 → 8000 포트를 쓰는 PID 출력
xargs kill -9 → 그 PID 강제 종료