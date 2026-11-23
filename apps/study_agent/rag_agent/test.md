# VectorDB 테스트 가이드

## 환경 확인

```bash
# 프로젝트 디렉토리
cd /home/hykiop/on-tutor/study_agent/rag_agent

# 가상환경 활성화 (선택)
source .venv/bin/activate
# 또는 직접 경로 사용: .venv/bin/python
```

---

## 1. 자동 통합 테스트 (7개 시나리오 전체 검증)

임시 파일과 임시 DB를 생성하고 삭제까지 자동으로 처리한다.

```bash
.venv/bin/python test_integration.py
```

### 테스트 항목
| 번호 | 내용 |
|------|------|
| TEST 1 | `add_document` + `search` — 문서 추가 및 검색 |
| TEST 2 | `list_titles` — 타이틀 목록 조회 |
| TEST 3 | `list_files` — 특정 타이틀 파일 목록 조회 |
| TEST 4 | `search` with `file_name` 필터 |
| TEST 5 | `delete_file` — 파일 단위 삭제 |
| TEST 6 | `delete_title` — 타이틀 전체 삭제 |
| TEST 7 | 존재하지 않는 타이틀 검색 (빈 리스트 반환) |

### 성공 기준
```
=== ALL TESTS PASSED ===
```

---

## 2. 인터랙티브 수동 테스트

실제 파일을 넣고 검색 품질을 직접 확인할 수 있다.

```bash
.venv/bin/python demo_vectordb.py
```

### 명령어

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `add <파일경로> <타이틀>` | 파일 추가 (PDF/DOCX/TXT 지원) | `add ~/자료/운영체제.pdf 운영체제` |
| `search <타이틀> <질의>` | 유사도 검색 | `search 운영체제 프로세스 스케줄링이란` |
| `list` | 저장된 타이틀 및 파일 목록 | `list` |
| `delete_file <타이틀> <파일명>` | 파일 단위 삭제 | `delete_file 운영체제 운영체제.pdf` |
| `delete_title <타이틀>` | 타이틀 전체 삭제 | `delete_title 운영체제` |
| `quit` | 종료 | `quit` |

---

## 3. 코드에서 직접 사용 (에이전트 연동용)

```python
import sys, os
sys.path.insert(0, '/home/hykiop/on-tutor/study_agent/rag_agent')
os.environ.setdefault("EMBED_MODEL", "local")   # 로컬 bge-m3 (기본값)
# os.environ["EMBED_MODEL"] = "openai"          # OpenAI 사용 시

from vector_db import VectorDBManager

db = VectorDBManager()

# 문서 추가
result = db.add_document(file_path="강의자료.pdf", title="운영체제")
# → {"status": "ok", "chunks_added": 42, "table": "title_운영체제"}

# 검색 (top_k 기본값은 embedder 설정 따름)
hits = db.search(query="프로세스와 스레드의 차이", title="운영체제", top_k=5)
# → [{"text": "...", "source": "강의자료.pdf", "page": 3, "score": 0.87}, ...]

# 특정 파일만 검색
hits = db.search(query="...", title="운영체제", filter={"file_name": "강의자료.pdf"})

# 목록 조회
db.list_titles()            # → ["운영체제", "자료구조"]
db.list_files("운영체제")   # → ["강의자료.pdf", "ch1.pdf"]

# 삭제
db.delete_file(title="운영체제", file_name="강의자료.pdf")
db.delete_title("운영체제")
```

---

## 4. 임베딩 모델 설정

| 환경변수 | 모델 | 특징 |
|----------|------|------|
| `EMBED_MODEL=local` (기본값) | BAAI/bge-m3 (1024-dim) | 무료, 한국어 강점, 첫 실행 후 캐시 |
| `EMBED_MODEL=openai` | text-embedding-3-small (1536-dim) | 유료, `OPENAI_API_KEY` 필요 |

`.env` 파일에서 설정:
```
EMBED_MODEL=local
LANCEDB_PATH=./lancedb_data
CHUNK_SIZE=512
CHUNK_OVERLAP=64
```

### 모델 캐시 상태

bge-m3 모델이 이미 로컬에 캐시되어 있다. 추가 다운로드 불필요.

```
~/.cache/huggingface/hub/models--BAAI--bge-m3/   (4.3GB)
  ├── pytorch_model.bin     (2.2GB)
  └── model.safetensors     (2.2GB)
```

> 두 버전(pytorch/safetensors)이 공존하는 것은 정상이다. `sentence-transformers`는 `safetensors`를 우선 사용한다.

---

## 5. 지원 파일 형식

| 확장자 | 파서 | 비고 |
|--------|------|------|
| `.pdf` | PyMuPDF + pymupdf4llm | 페이지별 마크다운 추출, CJK 지원 |
| `.docx` | python-docx | 단락 단위 추출 |
| `.txt` | 내장 | UTF-8 읽기, 단일 페이지로 처리 |

---

## 6. DB 저장 위치

기본값: `./lancedb_data/` (`.env`의 `LANCEDB_PATH`로 변경 가능)

```
lancedb_data/
└── title_운영체제/      ← 타이틀별 테이블 (Lance 포맷)
    ├── _latest.manifest
    └── *.lance
```
