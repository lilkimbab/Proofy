# Retrieval Service 설계 문서

---

## 1. 개요

Vector DB에 저장된 학습 자료를 외부 에이전트가 HTTP로 검색할 수 있게 노출하는 서비스다.
LLM 답변 생성은 이 서비스의 역할이 아니다. 각 에이전트가 검색 결과를 받아 자신의 맥락에 맞게 활용한다.

**핵심 추상화 원칙**: 에이전트는 query만 보내면 된다. 텍스트/이미지 판단은 서비스 내부에서 처리하며, 에이전트는 결과만 받아 사용한다.

```
외부 에이전트  →  POST /search (query)  →  Retrieval Service  →  VectorDB
              ←  chunk 목록 (text + image)  ←                  ←
```

---

## 2. 모듈 구조

```
rag_agent/
├── vector_db/          ✅ 문서 저장 및 유사도 검색
│   ├── parser.py       — PDF/DOCX/TXT 파싱, 이미지 포함 페이지 PNG 저장
│   ├── chunker.py      — 텍스트 청킹 (SentenceSplitter + mecab)
│   ├── embedder.py     — 임베딩 (bge-m3 local / openai)
│   ├── store.py        — LanceDB CRUD
│   ├── retriever.py    — 유사도 검색
│   └── manager.py      — 외부 진입점 (파이프라인 조합)
├── api/                ✅ HTTP 서비스 레이어
│   ├── main.py         — FastAPI 앱, VectorDBManager 초기화
│   ├── routes.py       — 엔드포인트 정의
│   └── schemas.py      — Pydantic 요청/응답 스키마
└── server.py           — uvicorn 실행 진입점
```

---

## 3. API 엔드포인트

### POST `/search` — 유사도 검색

**요청**
```json
{
  "query": "프로세스 스케줄링이란?",
  "title": "운영체제",
  "top_k": 5,
  "filter": {"file_name": "공룡책.pdf"}
}
```
- `top_k`: 생략 시 `.env`의 `TOP_K` 사용 (기본 5)
- `filter`: 생략 시 타이틀 전체에서 검색

**응답**
```json
{
  "results": [
    {
      "text": "CPU 스케줄러는 준비 큐에서 프로세스를 선택하여...",
      "source": "공룡책.pdf",
      "page": 158,
      "score": 0.91,
      "image": null
    },
    {
      "text": "스케줄링 알고리즘 비교표",
      "source": "공룡책.pdf",
      "page": 162,
      "score": 0.87,
      "image": "iVBORw0KGgoAAAANSUhEUgAA..."
    }
  ]
}
```

- `image`: 해당 페이지에 이미지/다이어그램이 있으면 base64 PNG, 없으면 `null`
- 에이전트는 `image != null`이면 멀티모달 LLM에 이미지를 직접 전달할 수 있음
- 추가 HTTP 요청 불필요 — 텍스트와 이미지가 한 응답에 포함됨

---

### POST `/add` — 문서 등록

파일을 파싱·청킹하여 parent 텍스트를 즉시 반환하고, 임베딩·저장은 백그라운드에서 진행한다.

**요청** (multipart/form-data)
```
file: <업로드 파일>
title: "운영체제"
```

**응답** (parse 완료 즉시 반환)
```json
{
  "status": "accepted",
  "job_id": "a1b2c3d4-...",
  "title": "운영체제",
  "file_name": "공룡책.pdf",
  "parents": [
    {
      "parent_id": "공룡책.pdf::0",
      "text": "## 프로세스 스케줄링\nCPU 스케줄러는 준비 큐에서...",
      "file_name": "공룡책.pdf",
      "page_start": 1,
      "page_end": 3,
      "heading_path": ["프로세스 스케줄링"],
      "source_type": "general"
    }
  ]
}
```

- `parents`: 헤딩 기준으로 묶인 의미 단위 텍스트. 에이전트가 문서 전체를 즉시 읽을 수 있음
- `job_id`: 백그라운드 임베딩 진행 상태는 `GET /jobs/{job_id}` 로 추적
- 빈 파일 업로드 시 `parents: []`, `job` 상태는 즉시 `done`

---

### GET `/jobs/{job_id}` — 인제스트 진행 상태

```json
{
  "job_id": "a1b2c3d4-...",
  "status": "done",
  "title": "운영체제",
  "file_name": "공룡책.pdf",
  "chunks_added": 342,
  "batch": 4,
  "total_batches": 4,
  "error": null
}
```
- `status`: `pending` → `running` → `done` | `failed`

---

### GET `/titles` — 타이틀 목록
```json
{"titles": ["운영체제", "자료구조", "네트워크"]}
```

### GET `/files/{title}` — 파일 목록
```json
{"title": "운영체제", "files": ["공룡책.pdf", "반효경_강의노트.pdf"]}
```

### DELETE `/files/{title}/{file_name}` — 파일 삭제
```json
{"status": "ok"}
```

### DELETE `/titles/{title}` — 타이틀 전체 삭제
```json
{"status": "ok"}
```

---

## 4. 멀티모달 파이프라인

### 이미지 감지 기준
PDF 파싱 시 `page.get_images()` (PyMuPDF)로 페이지에 실제 이미지 객체가 있는지 감지한다.
텍스트 길이 기반 휴리스틱을 사용하지 않으므로, 텍스트와 그림이 함께 있는 페이지도 정확히 처리된다.

### 저장 구조
```
image_store/
└── {file_stem}/
    ├── page_0.png
    └── page_7.png
```
이미지 파일은 서버 로컬에 저장되고, 검색 시 base64로 인코딩되어 응답에 포함된다.

### 에이전트 사용 예시
```python
import requests, base64

resp = requests.post("http://localhost:8000/search", json={
    "query": "스케줄링 알고리즘 비교",
    "title": "운영체제",
    "top_k": 5
})

for chunk in resp.json()["results"]:
    if chunk["image"]:
        # 멀티모달 LLM에 이미지 직접 전달
        image_bytes = base64.b64decode(chunk["image"])
        # anthropic_client.messages.create(..., content=[{"type": "image", ...}])
    else:
        # 텍스트만 사용
        print(chunk["text"])
```

---

## 5. 환경 변수 (.env)

```
# Vector DB
EMBED_MODEL=local          # "local"(bge-m3) | "openai"(text-embedding-3-small)
OPENAI_API_KEY=sk-...      # EMBED_MODEL=openai 시 필요
LANCEDB_PATH=./lancedb_data
CHUNK_SIZE=512
CHUNK_OVERLAP=64

# 이미지 저장
IMAGE_STORE_PATH=./image_store

# 서버
API_HOST=0.0.0.0
API_PORT=8000
TOP_K=5
```

---

## 6. 서버 실행

```bash
source .venv/bin/activate
python server.py

# API 문서 (Swagger UI)
# http://localhost:8000/docs
```

---

## 7. 외부 에이전트 호출 예시

```python
import requests

BASE = "http://localhost:8000"

# 문서 등록 — parse 결과(parents) 즉시 반환, embed는 백그라운드 진행
with open("공룡책.pdf", "rb") as f:
    resp = requests.post(f"{BASE}/add", files={"file": f}, data={"title": "운영체제"})

result = resp.json()
job_id = result["job_id"]
parents = result["parents"]   # 에이전트가 문서 내용을 즉시 읽을 수 있음

# 백그라운드 임베딩 완료 여부 확인 (필요 시)
status = requests.get(f"{BASE}/jobs/{job_id}").json()["status"]  # "done" | "running" | ...

# 임베딩 완료 후 검색 — query만 보내면 텍스트+이미지 모두 포함된 결과 반환
resp = requests.post(f"{BASE}/search", json={
    "query": "LRU 알고리즘이란?",
    "title": "운영체제",
    "top_k": 5
})
chunks = resp.json()["results"]
# 이후 각 에이전트가 chunks를 자신의 프롬프트에 맞게 조합
```
