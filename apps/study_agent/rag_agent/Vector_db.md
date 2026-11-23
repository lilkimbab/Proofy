# Vector DB 모듈 설계 문서

---

## 0. 전체 시스템에서의 위치

본 모듈은 study agent 프로젝트의 **DB_server** 계층이다.
LanceDB 가 임베디드 방식이라 "데이터만 있는 서버"라는 고전적 분리가 불가능하므로,
**벡터 데이터 + 검색·재정렬·개인화 모델**이 같은 노드에 함께 배치된 retrieval 전용 서비스 형태를 취한다.

```
Client (UI)
   ↓ HTTP
Main server      ← 사용자 세션, LLM 호출(generation), 학습 진단, 프롬프트 조립
   ↓ HTTP        (검색 요청 / 사용자 피드백 전달)
DB_server        ← 본 프로젝트
   ├── 파싱·청킹·임베딩 파이프라인
   ├── LanceDB (벡터 + 메타데이터)
   ├── Reranker (BAAI/bge-reranker-v2-m3)
   ├── Personalization (user_profiles JSON)
   └── FastAPI 인터페이스
```

### 책임 분리

| Main server | DB_server (이 프로젝트) |
|-------------|------------------------|
| 사용자 인증·세션 관리 | 문서 파싱·청킹·임베딩 |
| LLM 호출 (Claude/GPT) — generation | 벡터 저장 + 검색 |
| 프롬프트 조립 (retrieved chunks → LLM) | Reranker, Personalization 적용 |
| 학습 진단 / 퀴즈 생성 / 학습 이력 분석 | 검색 결과 + 메타데이터 반환 |
| 어떤 chunk 가 useful 인지 판단 → DB_server 에 신호 전달 | 신호 누적·boost 적용 |
| Client 에 최종 답변 응답 | retrieval 만 담당, **generation 하지 않음** |

---

## 3. 기술 스택 선정

### 3-1. Vector DB: LanceDB

**선택 이유**
- 임베디드(서버리스) 방식으로 별도 프로세스 없이 파일로 동작
- Lance 컬럼형 포맷으로 Parquet 대비 벡터 쿼리 ~100x 빠름
- table 단위 네이티브 분리 → 타이틀별 collection 구현에 적합
- 메타데이터 필터링 내장 지원 (파일명, 페이지 기반 필터)
- 제로카피 버저닝으로 에이전트의 빈번한 업데이트에 최적
- 1M+ 벡터까지 로컬에서 안정적으로 운용 가능

**비교 대상 및 탈락 이유**

| DB | 탈락 이유 |
|----|----------|
| ChromaDB | SQLite 기반으로 고빈도 업데이트 시 성능 저하. LanceDB보다 쿼리 속도 열세 |
| FAISS | 메타데이터 필터링 미지원, 별도 저장소 연동 필요, 운영 복잡도 높음 |
| Qdrant (로컬) | Docker 의존 또는 별도 바이너리 필요, 단일 노드 임베디드 방식 아님 |
| Pinecone | 클라우드 전용, 비용 발생, 오프라인 운용 불가 |

```bash
pip install lancedb
```

---

### 3-2. PDF 파싱: PyMuPDF + pymupdf4llm

**선택 이유**
- LLM 파이프라인 전용 래퍼(`pymupdf4llm`)로 마크다운 변환 출력 지원
- CJK(한국어 포함) 인식 내장, 한글 PDF에서 텍스트 추출 정확도 높음
- 처리 속도 0.12s/페이지로 주요 파서 중 최상위권
- C 바인딩 단일 의존으로 패키지 무게 최소
- 이미지 기반 PDF(스캔 PDF)는 OCR 파이프라인으로 처리 (섹션 21 참고)

**비교 대상 및 탈락 이유**

| 파서 | 탈락 이유 |
|------|----------|
| pypdf | 순수 Python이라 느림(0.024s이지만 레이아웃 보존 낮음), 표 추출 불가 |
| pdfplumber | pdfminer 의존으로 무거움, 복잡한 레이아웃에서 텍스트 순서 오류 |
| unstructured | ML 의존성 다수로 설치 무게 과다(1.29s/page), 에이전트 호출 지연 증가 |

```bash
pip install pymupdf pymupdf4llm python-docx
```

---

### 3-3. 청킹: LlamaIndex + mecab

**선택 이유**
- `SentenceSplitter`가 문장 단위로 분할 (문자 수 기반이 아님)
- mecab 한국어 형태소 분석기 연동으로 교착어 특성 처리
- LangChain RecursiveCharacterTextSplitter 대비 한국어 recall 2-3%p 우세
- 시맨틱 청킹(임베딩 기반)보다 10배 저렴하면서 성능 차이는 2%p 이내

**비교 대상 및 탈락 이유**

| 방식 | 탈락 이유 |
|------|----------|
| LangChain RecursiveCharacterTextSplitter | 한국어를 문자 단위로만 처리, 형태소 경계 무시 |
| Semantic Chunking (임베딩 기반) | 모든 문장을 임베딩하므로 비용 10배, 성능 차이 미미 |
| NLTK | 한국어 문장 분리 미지원 |
| spaCy | 한국어 파이프라인 설치 복잡, mecab 대비 정확도 열세 |

**영어 문서에 대한 tradeoff**

mecab은 한국어 교착어 형태소 분리를 위해 설계된 도구다. 영어 문서에 적용 시 아래 상충이 발생한다.

| 항목 | 영향 | 수준 |
|------|------|------|
| 분할 정확도 | 영어는 공백 기반 토크나이저로도 충분히 처리되므로 실질적 품질 저하 없음. LlamaIndex `SentenceSplitter`가 영어 문장부호(`.`, `?`, `!`)를 기본 처리하므로 mecab 미개입 구간에서 정상 동작 | 무시 가능 |
| 처리 속도 | mecab이 영어 단어를 단일 토큰으로 통과시키므로 분석 오버헤드 미미. 한국어 문서 대비 처리 시간 동등하거나 소폭 빠름 | 무시 가능 |
| 청킹 품질 | 영어는 어절 경계가 명확해 RecursiveCharacterTextSplitter와 실질 차이 없음. recall 기준 1%p 이내 | 무시 가능 |
| 설치 부담 | mecab 시스템 패키지 설치 필요 (apt). 영어 전용 환경이라면 불필요한 의존성 | 설치 시 1회만 |

**결론**: 한국어·영어 혼용 문서 기준으로 mecab 선택의 영어 성능 손실은 사실상 없다.  
영어 단독 문서만 처리한다면 mecab 없이 LlamaIndex `SentenceSplitter` 기본값으로도 충분하다.

```bash
pip install llama-index-core
# mecab (Linux)
sudo apt-get install mecab libmecab-dev mecab-ipadic-utf8
pip install mecab-python3 python-mecab-ko
```

---

### 3-4. 임베딩 모델: BAAI/bge-m3 (기본) / OpenAI (대체)

**선택 이유 — bge-m3**
- 한국어 Retrieval F1 0.71로 오픈소스 멀티링구얼 모델 중 1위
- 100개 이상 언어 지원, 한·영 혼용 문서에 강점
- 컨텍스트 윈도우 8192 tokens로 긴 chunk 처리 가능
- 완전 로컬 실행으로 추론 비용 없음
- 단일 모델로 retrieval + reranking 모두 지원

**대체 — OpenAI text-embedding-3-small**
- API 키 있을 경우 선택 가능 ($0.020/1M tokens)
- 컨텍스트 무제한, 설치 불필요
- 한국어 F1 ~0.60으로 bge-m3 대비 열세지만 범용성 높음
- text-embedding-3-large는 6.5배 비싸고 한국어 개선 폭 미미 → 비추천

**비교 표**

| 모델 | 한국어 F1 | 비용 | 컨텍스트 | 방식 |
|------|----------|------|---------|------|
| BAAI/bge-m3 | **0.71** | 무료 | 8192 tokens | 로컬 |
| OpenAI text-embedding-3-small | 0.60 | $0.02/1M | 무제한 | API |
| OpenAI text-embedding-3-large | 0.65 | $0.13/1M | 무제한 | API |
| jhgan/ko-sroberta-multitask | 0.61 | 무료 | 512 tokens | 로컬 |
| all-MiniLM-L6-v2 | ~0.55 | 무료 | 512 tokens | 로컬 |

```bash
pip install sentence-transformers   # bge-m3 로컬 실행
pip install openai                  # OpenAI 대체 사용 시
```

---

## 4. 환경 설정

### 4-1. 전체 의존성 설치
```bash
pip install lancedb pymupdf pymupdf4llm python-docx \
            llama-index-core sentence-transformers \
            openai python-dotenv mecab-python3 python-mecab-ko
```

### 4-2. .env 파일
```
# ── DB / 임베딩 ──────────────────────────────────────────
LANCEDB_PATH=./lancedb_store         # LanceDB 파일 저장 경로
EMBED_MODEL=local                    # "local"(bge-m3, d=1024) | "openai"(d=1536)
OPENAI_API_KEY=sk-...                # EMBED_MODEL=openai 시 필요
DB_VERSION=1                         # 수동 버전 올림 → 전체 재임베딩 트리거

# ── 검색 ─────────────────────────────────────────────────
TOP_K=5                              # 기본 반환 결과 수
SEARCH_MODE=hybrid                   # "hybrid" | "vector" | "fts"
RRF_K=60                             # Hybrid RRF 상수
CANDIDATE_MULTIPLIER=4               # Hybrid 1차 후보 배수 (retriever 내부)

# ── Reranker ──────────────────────────────────────────────
RERANK_ENABLED=true                  # Reranker 활성화 여부
RERANK_CANDIDATE_MULTIPLIER=4        # Reranker용 후보 배수 (manager 레벨)

# ── 청킹 ─────────────────────────────────────────────────
CHUNK_SIZE=512
CHUNK_OVERLAP=64
CHUNK_STRATEGY=structural            # "structural" | "fixed"
MIN_CHUNK_CHARS=200
INGEST_BATCH_SIZE=32                 # 헤딩 그룹 최대 크기 (heading 없는 문서 폴백)

# ── Parent-Child ──────────────────────────────────────────
MIN_PARENT_CHARS=300
MAX_PARENT_CHARS=3000

# ── ANN 인덱스 (IVF-PQ) ───────────────────────────────────
ANN_MIN_ROWS=256                     # 이 값 미만 테이블은 인덱스 생성 skip

# ── Personalization ───────────────────────────────────────
PERSONALIZATION_ENABLED=true
USER_PROFILE_DIR=./user_profiles
USER_QUERY_HISTORY_MAX=200
PERSONAL_VIEW_WEIGHT=0.05
PERSONAL_USEFUL_WEIGHT=0.15
PERSONAL_MAX_BOOST=1.5

# ── Webhook (선택) ────────────────────────────────────────
AUGMENT_WEBHOOK_URL=                 # 배치 완료 알림 수신 URL (빈 값이면 비활성)
WEBHOOK_CONTEXT_CHUNKS=2             # 웹훅 페이로드에 포함할 이전 컨텍스트 청크 수
```

---

## 5. 모듈 구조

```
vector_db/
├── __init__.py
├── parser.py           # 파일 파싱 및 텍스트·메타데이터 추출 (PDF/DOCX), 스캔 PDF OCR 포함
├── ocr.py              # OCR provider 추상화 (NullOcrProvider / EasyOcrProvider)
├── chunker.py          # 한국어 인식 청킹 (LlamaIndex SentenceSplitter + mecab)
├── parent_builder.py   # Parent-Child 청크 경계 감지 및 parent 레코드 생성
├── embedder.py         # 임베딩 생성 (bge-m3 d=1024 / OpenAI d=1536 전환)
├── embed_meta.py       # DB 버전 해시 계산 (EMBED_MODEL + DB_VERSION → 8자리 hex)
├── store.py            # LanceDB table CRUD, FTS/ANN 인덱스 관리
├── retriever.py        # 유사도·FTS·Hybrid 검색 및 필터링
├── reranker.py         # Cross-encoder Reranker (BAAI/bge-reranker-v2-m3)
├── personalization.py  # 사용자 프로파일 저장·조회·boost 계산
├── pipeline.py         # SearchPipeline / Stage 추상화 (Retrieve→Rerank→Boost→Record)
└── manager.py          # 외부 에이전트용 통합 인터페이스 (유일한 진입점)
```

`api/` 는 FastAPI 라우터 레이어이며 `VectorDBManager` 만 호출한다.
```
api/
├── main.py     # FastAPI app 생성 및 라우터 등록
├── routes.py   # HTTP 엔드포인트 정의
└── schemas.py  # Pydantic 요청·응답 스키마
```

---

## 6. 에이전트 인터페이스 (manager.py)

모든 외부 에이전트는 `VectorDBManager` 클래스만 호출한다.  
내부 파싱·청킹·임베딩은 자동으로 처리된다.

### 6-1. 초기화
```python
from vector_db.manager import VectorDBManager

db = VectorDBManager()
# .env에서 설정 자동 로드
```

### 6-2. 문서 파싱 (동기)
```python
parsed = db.parse_document("./자료/운영체제_공룡책.pdf")
# 반환값:
# {
#   "chunks": [...],     # child chunk 리스트 (text, page, image_page, heading_path, ...)
#   "parents": [...],    # parent 레코드 리스트
#   "page_images": [...] # [{file_name, page, image_path}, ...] — 이미지 페이지만
# }
```

### 6-3. 임베딩·저장 (동기 또는 BackgroundTask로 비동기 실행)
```python
result = db._embed_and_store(
    title="운영체제",
    chunks=parsed["chunks"],
    parents=parsed["parents"],
    page_images=parsed.get("page_images", []),
)
# 반환값:
# {"status": "ok", "chunks_added": 342, "table": "title_운영체제"}
```
- `parse_document()`와 분리된 이유: API의 `/add` 엔드포인트가 parse를 동기로 실행해 parent 텍스트를 즉시 반환하고, embed·store는 `BackgroundTasks`로 비동기 실행하기 위함.
- 동일 파일 재등록 시 기존 chunk 삭제 후 upsert (전체 교체 방식)

### 6-4. 유사도 검색
```python
results = db.search(
    query="페이지 교체 알고리즘의 종류를 설명해줘",
    title="운영체제",
    top_k=5             # 생략 시 .env의 TOP_K 사용
)
# 반환값:
# [
#   {
#     "text": "LRU 알고리즘은 가장 오랫동안 참조되지 않은 페이지를 교체한다...",
#     "source": "운영체제_공룡책.pdf",
#     "page": 312,
#     "score": 0.91
#   },
#   ...
# ]
```

### 6-5. 특정 파일 내에서만 검색 (메타데이터 필터)
```python
results = db.search(
    query="스케줄링 알고리즘",
    title="운영체제",
    filter={"file_name": "운영체제_공룡책.pdf"}
)
```

### 6-6. 등록된 타이틀 목록 조회
```python
titles = db.list_titles()
# ["운영체제", "자료구조", "네트워크"]
```

### 6-7. 타이틀 내 파일 목록 조회
```python
files = db.list_files(title="운영체제")
# ["운영체제_공룡책.pdf", "반효경_강의노트.pdf"]
```

### 6-8. 특정 파일 삭제
```python
db.delete_file(
    title="운영체제",
    file_name="운영체제_공룡책.pdf"
)
```

### 6-9. 타이틀 전체 삭제
```python
db.delete_title(title="운영체제")
```

---

## 6-10. /add 엔드포인트 비동기 패턴

```
POST /add  (multipart/form-data: file + title)
    │
    ├─ parse_document(tmp_path)          ← 동기 실행, 즉시 완료
    │       └─ returns {chunks, parents, page_images}
    │
    ├─ AddAcceptedResponse 반환          ← parent 텍스트 포함, 즉시 응답
    │       (status=accepted, parent_chunks=[...])
    │
    └─ BackgroundTasks.add_task(...)     ← HTTP 응답 후 비동기 실행
            └─ _embed_and_store(title, chunks, parents, page_images)
                    └─ 임베딩 + LanceDB 저장 + ANN 인덱스 재구축
```

`parse_document` / `_embed_and_store` 가 분리된 이유: parse는 빠르게 끝나므로 parent 텍스트를 클라이언트에 즉시 돌려줄 수 있고, 느린 임베딩은 백그라운드에서 처리한다. `add_document()` 래퍼는 이 비동기 패턴을 지원할 수 없어 삭제됐다.

---

## 7. 다중 주체 확장 (2단계)

현재 table 네이밍: `title_{name}`  
확장 후 table 네이밍: `{subject_id}_{title}`

`VectorDBManager`에 `subject_id` 파라미터만 추가하면 되며,  
파싱·청킹·임베딩·검색 로직은 변경 없이 재사용된다.

```python
# 2단계 확장 후 초기화 예시
db = VectorDBManager(subject_id="agent_42")
db.add_document(file_path="...", title="운영체제")
# → table 이름: "agent_42_운영체제"
```

---

## 9. Multimodal RAG ✅ 구현 완료

### 구현 내용

`page.get_images()` (PyMuPDF)로 이미지 포함 페이지를 감지하고, 해당 페이지를 1x 해상도(72dpi) PNG로 저장한다.
검색 시 `image_page → page_images table → image_path → base64` 순으로 해석하여 응답에 인라인 포함.
에이전트는 별도 HTTP 요청 없이 텍스트+이미지를 한 번에 받는다.

```
파싱 단계 (parser.py)
    ↓
페이지별 처리
    ├─ page.get_images() == []  →  image_path = None
    └─ page.get_images() != []  →  PNG 저장, image_path = "/path/to/page.png"

청킹 단계 (chunker.py)
    ↓  각 chunk에 image_page(int) 부여
    ├─ 이미지 없는 페이지  →  image_page = -1
    └─ 이미지 있는 페이지  →  image_page = <page_number>

인제스트 단계 (_embed_and_store)
    ├─ child chunk → LanceDB child table (image_page 컬럼)
    └─ page_images → LanceDB pageimg_{title} table
         {file_name, page, image_path}  ← FK 테이블

검색 응답 (_search)
    └─ image_page → pageimg 테이블 조회 → image_path → base64 인코딩
         {"image": "iVBORw0K..."} 또는 {"image": null}
```

### 스키마 분리 이유

| 방식 | 설명 | 선택 여부 |
|------|------|----------|
| chunk에 image_path 직접 저장 | 단순하지만 file 삭제·이동 시 모든 chunk 업데이트 필요 | 구버전 |
| chunk에 image_page(int) + 별도 pageimg 테이블 | FK 참조로 파일 단위 삭제·교체 효율적 | **현재** |

chunk 테이블 컬럼: `image_page` (int, -1 = 이미지 없음)  
pageimg 테이블: `{file_name, page, image_path}` — `pageimg_{hex(title)}` 네이밍

### 이미지 결과 캐시

같은 검색 호출 내에서 동일 PNG 파일을 두 번 base64 인코딩하지 않도록 `encoded_cache: dict[str, str|None]` 사용.

### 핵심 결정 사항

| 결정 | 선택 | 이유 |
|------|------|------|
| 이미지 감지 | `page.get_images()` | 텍스트 길이 휴리스틱 대비 정확도 높음 |
| 렌더링 해상도 | 1x (72dpi) | 2x 대비 파일 크기 ~63% 감소, 강의 슬라이드 가독성 충분 |
| 반환 방식 | base64 inline | 에이전트가 추가 HTTP 요청 불필요, 추상화 완성 |
| chunk↔이미지 연결 | image_page FK + pageimg 테이블 | 파일 삭제/교체 시 pageimg 행만 갱신하면 됨 |

### 스키마 마이그레이션 (구버전 호환)

`image_path` 컬럼만 있고 `image_page` 가 없는 구버전 테이블을 감지해 자동 재구축한다.
기존 row는 `image_page=-1`로 백필된다. 재인제스트 시 pageimg 테이블이 정상 채워진다.

---

## 10. Hybrid Search ✅ 구현 완료

BM25(키워드 검색)와 벡터 검색을 병행하여 결과를 통합(Reciprocal Rank Fusion)한다.

```
query
  ├─ 벡터 임베딩  →  LanceDB vector search  →  [rank_v1, rank_v2, ...]
  └─ BM25 토크나이징  →  LanceDB FTS index  →  [rank_b1, rank_b2, ...]
                                    ↓
                        RRF(k=60): score = 1/(k+rank_v) + 1/(k+rank_b)
                                    ↓
                            통합 정렬 결과 반환

```

**`manager.py` 투명 전환**: 기존 `search()` 시그니처 유지, 내부에서 hybrid로 전환

### 예상 효과

| 쿼리 유형 | 현재 (순수 벡터) | 개선 후 (Hybrid) |
|----------|----------------|----------------|
| 개념 설명 ("스케줄링이란?") | 우수 | 동등 |
| 키워드 직접 검색 ("FCFS 알고리즘") | 보통 | 우수 |
| 고유명사·코드 ("fork() 시스템 콜") | 불안정 | 안정 |


---

## 11. Reranker ✅ 구현 완료

**retrieve-then-rerank** 패턴: 초기 검색에서 top-N(예: 20)을 뽑고, Reranker가 top-k(예: 5)로 압축.

```
query + top-20 chunks
        ↓
  bge-m3 Reranker (cross-encoder)
        ↓
  relevance score 재계산 → top-5 반환
```

### 트레이드오프

| 항목 | 영향 |
|------|------|
| 검색 정밀도 | NDCG@10 기준 +5~10%p 예상 |
| 지연 시간 | top-20 reranking 기준 +100~300ms (로컬 CPU) |
| 메모리 | bge-reranker-v2-m3 약 1.1GB 추가 |
| 설치 | `pip install FlagEmbedding` |

**권장 적용 순서**: Hybrid Search 먼저 → 실측 품질 확인 → 필요 시 Reranker 추가.

---

## 12. Adaptive Chunking ✅ 구현 완료

markdown 구조를 1차 경계로 사용하고, chunk_size 초과 블록만 SentenceSplitter로 2차 분할한다.

**chunker.py 흐름**
```
parsed text (markdown)
    ↓
1) _split_by_structure  → 헤더/코드블록 단위 1차 분할
    ↓
2) _merge_small_blocks(MIN_CHUNK_CHARS) → 자투리 병합
    ↓
3) SentenceSplitter (chunk_size 초과한 블록만) → 2차 분할
    ↓
chunk[] (image_page, heading_path 등 메타데이터 보존)
```

**환경변수**
```
CHUNK_STRATEGY=structural   # "structural" | "fixed"
MIN_CHUNK_CHARS=200
```

### 트레이드오프

| 항목 | 영향 |
|------|------|
| 검색 정확도 | 표/코드/수식 포함 자료에서 +5%p 이상 예상 |
| 청크 수 | 통상 -10~20% (큰 블록 보존) |
| 호환성 | `CHUNK_STRATEGY=fixed` 로 두면 기존 동작 그대로 |
| 재인덱싱 | 청킹 변경 시 기존 LanceDB 테이블은 한 번 재구축 필요 |

---

## 13. Personalization ✅ 구현 완료

### 데이터 모델

`USER_PROFILE_DIR/{user_id}.json`
```json
{
  "user_id": "u_123",
  "queries": [{"query": "...", "title": "...", "ts": "..."}],
  "chunk_signals": {
    "운영체제": {
      "운영체제_공룡책.pdf_312": {"views": 4, "useful": 2}
    }
  }
}
```

### Boost 공식

```
boost = min(
    1 + VIEW_WEIGHT * log(1 + views) + USEFUL_WEIGHT * log(1 + useful),
    MAX_BOOST
)
score_personalized = score_base * boost
```

- `log` 스케일로 한 사용자가 한 chunk 를 반복적으로 클릭해 점수를 무한히 끌어올리는 것 방지
- `MAX_BOOST` 상한으로 base ranking 의 신호를 완전히 덮어쓰지 못하게 함

### API 변경

| 변경 | 내용 |
|------|------|
| `POST /search` | body 에 선택적 `user_id` 추가 — 없으면 기존 동작과 완전히 동일 |
| `POST /feedback` (신규) | `{user_id, title, chunk_id, kind: "view"|"useful"}` 신호 누적 |
| `manager.search(user_id=...)` | 검색 점수에 boost 적용 + 쿼리 자동 기록 |
| `manager.record_feedback(...)` | agent 가 사용자가 도움 됐다고 판단한 chunk 신호 전송 |

### 환경변수

```
PERSONALIZATION_ENABLED=true
USER_PROFILE_DIR=./user_profiles
USER_QUERY_HISTORY_MAX=200
PERSONAL_VIEW_WEIGHT=0.05
PERSONAL_USEFUL_WEIGHT=0.15
PERSONAL_MAX_BOOST=1.5
```

### 한계 / 향후

- 단일 노드 JSON 파일 기반 — 동시성은 쓰기 시 단일 락. 다중 워커로 확장 시 SQLite 또는 Redis 권장.
- 코사인 유사도가 아닌 사용자 토픽 모델링(예: 최근 쿼리 임베딩 평균과의 유사도) 으로 확장 가능.
- "useful" 신호 정의는 호출 agent 의 책임 — 본 모듈은 신호 자체를 해석하지 않는다.

---

---

## 15. 모듈화 / 운영 개선

step12~15 적용 후 발견된 모듈화 한계를 보완하는 4 가지 변경사항.

### 15-1. 검색 결과 trace (`pipeline` 필드)

`/search` 응답의 각 result 에 어떤 단계가 적용됐는지 `pipeline: list[str]` 으로 노출.

```json
{
  "text": "...", "score": 0.84,
  "pipeline": ["retrieve:hybrid", "rerank", "personal_boost", "query_record"]
}
```

토글 ON/OFF 효과를 실측할 때 호출 측에서 즉시 확인 가능.

### 15-2. `reload_config()` — 프로세스 재시작 없는 토글

`POST /reload` 또는 `VectorDBManager.reload_config()` 호출 시:
1. `.env` 재로드 (`load_dotenv(override=True)`)
2. Retriever / Reranker / PersonalizationStore / SearchPipeline 재구성
3. 임베딩 모델·LanceDB 연결은 보존 (메모리 절약)

응답 예:
```json
{"status": "ok", "config": {
  "search_mode": "vector", "rerank_enabled": false,
  "personalization_enabled": true, "chunk_strategy": "structural"
}}
```

### 15-3. `SEARCH_MODE=vector` 일 때 FTS 인덱스 생략

`store.upsert` 내부에서 `SEARCH_MODE` 가 `vector` 면 FTS 인덱스 생성을 건너뛴다.
이후 hybrid/fts 로 전환할 때는 `VectorStore.ensure_fts_index(title=None)` 로 일괄 재인덱싱.

```python
db._store.ensure_fts_index()         # 모든 title
db._store.ensure_fts_index("운영체제")  # 특정 title만
```

### 15-4. SearchPipeline 패턴

`vector_db/pipeline.py` 에 `SearchContext` 와 `Stage` 추상화 도입.
`manager.search()` 는 stage 리스트를 순회 실행하므로 단계 추가/제거가 평이.

```python
from vector_db import VectorDBManager, Stage

class MyStage(Stage):
    name = "tag"
    def apply(self, ctx):
        for r in ctx.results:
            r["custom"] = "x"
        ctx.trace.append("tag")

db = VectorDBManager()
db._pipeline.stages.append(MyStage())   # 새 단계 끼워넣기
```

기본 stage 순서:
```
RetrieveStage → RerankStage → PersonalBoostStage → QueryRecordStage
```

### 검증

`.venv/bin/python test_modularity.py` 가 4 가지 항목을 모두 검증한다.

---

## 16. 메타데이터 확장 (재업로드 안정성)

### 16-1. 재업로드 정책 — 전체 교체 + content_hash 기반 chunk_id

사용자가 "비슷한 자료 약간 수정본"을 다시 올리는 시나리오 처리.

**선택**: 옛 파일 chunk 를 모두 삭제하고 새 버전을 삽입한다(전체 교체).
**핵심**: chunk_id 를 `{file_name}_{chunk_index}` 가 아니라 **`{file_name}_{content_hash[:12]}`** 로 만든다.

```
chunk_id = file_name + sha256(text)[:12]
```

- 내용이 안 바뀐 chunk 는 재업로드 후에도 같은 chunk_id 유지
- 개인화 신호(`PersonalizationStore.chunk_signals`)는 chunk_id 문자열로 매핑되므로 자동 보존
- 변경된 chunk 만 새 id 부여 → 깔끔한 의미 (`v2_ids - v1_ids` = 실제 변경된 부분)
- 구현 복잡도는 "delete + add" 그대로 (diff 로직 없음)

**대안과 비교**

| 방식 | 장점 | 단점 |
|------|------|------|
| 전체 교체 + chunk_index id | 단순 | 문서 중간 삽입 시 모든 신호 무효화 |
| 전체 교체 + content_hash id ← 선택 | 단순 + 신호 보존 | 변경 없는 chunk 도 재임베딩 |
| 부분 diff 업데이트 | 재임베딩 절감 | 코드 복잡, 작은 차이로 미스 가능, 로컬 임베딩 환경에선 효용 작음 |

로컬 bge-m3 기준 50페이지 PDF 재임베딩 ~10초. 재업로드는 빈번하지 않으므로 감수.
유료 임베딩 API 로 전환할 경우 부분 diff 로 업그레이드 검토.

### 16-2. 추가된 메타데이터

| 필드 | 타입 | 의미 |
|------|------|------|
| `content_hash` | string (SHA-256, 64 hex) | chunk text 의 해시. chunk_id 의 안정성 기반. 공백 정규화 후 해싱 |
| `heading_path` | list[string] | markdown 헤더 체인 (예: `["Chapter 1","1.2 스레드"]`). step14 structural chunking 의 부산물 |
| `source_type` | string | `slide` / `textbook` / `code` / `general` 자동 분류. 페이지 평균 길이·코드블록 비율·이미지 비율 휴리스틱 |

`doc_id` 는 추가하지 않음. `file_name` 이 동일 역할을 수행하며, 사용자가 같은 자료를 다른 파일명으로 올리는 경우 시스템이 자동 동일성 판정할 방법이 없어 추가 컬럼은 중복일 뿐.

### 16-3. 자동 source_type 감지 휴리스틱

[parser.py `_detect_source_type`](vector_db/parser.py)

```
페이지 평균 텍스트 길이 (avg_text_len)
이미지 페이지 비율 (image_ratio)
코드블록 포함 여부 (has_code)

if has_code and avg_text_len < 1000:        → "code"
elif image_ratio >= 0.5 or avg_text_len < 400: → "slide"
elif avg_text_len > 1500:                    → "textbook"
else:                                        → "general"
```

향후 chunker 가 source_type 별로 chunk_size 를 조정하는 로직을 얹기 좋은 기반.

### 16-4. 스키마 마이그레이션

기존(메타데이터 없는) 테이블에 새 컬럼 포함 row 를 upsert 하면 [store.py](vector_db/store.py) 가 감지해 자동 재구축한다.

```
[INFO] schema migration: 'os' 재구축 (212 보존 + 38 신규)
```

기존 row 는 `content_hash=""`, `heading_path=[]`, `source_type="general"` 로 백필. 본인 자료를 `/add` 엔드포인트로 한 번 다시 업로드하면 정상 메타로 채워진다.

### 16-5. 검증

`.venv/bin/python test_metadata.py` 가 다음을 확인한다:

- source_type 자동 감지
- chunker 가 content_hash / heading_path / source_type 부착
- chunk_id 가 content_hash 기반
- **재업로드 시 변경 없는 chunk 의 id 보존** (개인화 신호 안정성의 근거)
- /search 응답에 새 필드 노출
- 옛 스키마 테이블의 자동 마이그레이션

---

## 17. Parent-Child Chunking ✅ 구현 완료

### 배경 문제

검색 단위(child chunk, ~512 tokens)와 LLM 컨텍스트 단위가 같다.
증명·코드·표처럼 연속성이 중요한 내용이 chunk 경계에서 잘리면 LLM이 불완전한 컨텍스트를 받는다.

### 구조

```
인제스트:
  chunk_documents() → child chunks (기존 그대로)
      ↓
  build_parents()   → child에 parent_id 부여 + parent 레코드 생성
      ↓
  LanceDB child table  ← 벡터 검색 대상
  LanceDB parent table ← parent_id로 조회, 벡터 없음

검색:
  child로 유사도 검색 → top-k hits
      ↓
  hits의 parent_id로 parent table 일괄 조회 (추가 쿼리 1회)
      ↓
  결과에 parent_text 필드 추가 → main_server가 LLM 컨텍스트로 사용
```

### parent 경계 감지 (`parent_builder.py`)

chunk를 순서대로 순회하며 **로컬 신호**로 경계를 판단한다. 문서 전체에 전략을 고정하지 않으므로 혼재 문서도 자동 대응된다.

| 우선순위 | 조건 | 동작 |
|---------|------|------|
| 1 | `heading_path` 변경 | 항상 새 parent |
| 2 | `page` 변경 + (heading 없음 OR 누적 ≥ MIN_PARENT_CHARS) | 새 parent |
| 3 | 누적 ≥ MAX_PARENT_CHARS + 코드블록 아님 | 강제 분할 |
| 예외 | 코드블록(` ``` `로 시작) | MAX 초과 허용 |

크기 초과 시 `\n\n` 경계(단락)로 분할. 단락 하나가 MAX를 넘으면 그대로 허용.

### 환경변수

```
MIN_PARENT_CHARS=300    # 이 크기 미만에서는 page 변경을 경계로 보지 않음
MAX_PARENT_CHARS=3000   # 이 크기 초과 시 강제 분할 (코드블록 예외)
```

### parent 레코드 스키마

| 필드 | 타입 | 의미 |
|------|------|------|
| `parent_id` | string (SHA-256[:16]) | `{file_name}__parent_{idx}` 해시 |
| `text` | string | 섹션 전체 텍스트 |
| `file_name` | string | 원본 파일명 |
| `page_start` | int | 포함된 첫 페이지 |
| `page_end` | int | 포함된 마지막 페이지 |
| `heading_path` | list[string] | 섹션 heading 체인 |
| `source_type` | string | slide / textbook / code / general |

### 기존 데이터 호환성

`parent_id` 컬럼이 없는 기존 child chunk는 `row.get("parent_id", "")` → `parent_text = None`으로 처리된다. 검색 결과가 반환되며, parent_text만 null이다. 재인제스트 시 정상 부여된다.

### parent 레코드의 heading_path / source_type 중복 분석

parent 레코드와 child chunk 양쪽에 `heading_path`, `source_type`이 저장된다. 검토한 결과 **의도적으로 유지**하는 중복이다.

**왜 항상 동일한 값인가**

`_is_boundary()` 1순위 조건:
```python
if prev_hp != curr_hp:
    return True  # heading_path가 바뀌면 무조건 새 parent
```
heading_path가 변경되는 순간 parent 경계가 생기므로, 하나의 parent 안에 속한 모든 child는 구조적으로 동일한 heading_path를 가진다. `_make_parent_record()`가 `anchor[0].get("heading_path")`를 복사하지만, 나머지 child들과도 항상 동일한 값이다.

`source_type`은 `parser.py`의 `_annotate_source_type()`이 파일 전체를 한 번 분석한 뒤 모든 페이지에 동일 값을 부여하므로, 같은 파일에서 나온 모든 child와 parent의 source_type은 항상 같다.

**제거 시 트레이드오프**

| 항목 | 제거 시 | 유지 시 |
|------|---------|---------|
| DB 저장량 | parent N개 × 2필드 절감 | 현 상태 (parent는 child보다 수 적음, 영향 미미) |
| search 응답 | 변화 없음 (`manager.py`가 `parent["text"]`만 추출, heading_path·source_type은 버림) | 변화 없음 |
| add 응답 (`ParseParent`) | `heading_path`, `source_type` 필드 제거됨 | 클라이언트가 섹션 위치·타입 즉시 확인 가능 |
| parent 테이블 단독 TOC 구성 | child 테이블 추가 조회 필요 | parent 테이블 스캔만으로 섹션 목차 재구성 가능 |
| source_type 필터 | child 테이블에는 그대로 있음, 영향 없음 | 동일 |

**결론: 유지**

add 응답(`ParseParent.heading_path`, `ParseParent.source_type`)이 클라이언트에게 섹션 메타데이터를 제공하는 유일한 창구이며, 이를 child에서 재구성하려면 `parent_id → child[0]` 역방향 조회 로직이 추가로 필요하다. 저장량 절감 효과는 미미하고 코드 복잡도만 증가하므로 현 구조를 유지한다.

---

## 18. Fetch 모드 ✅ 구현 완료

### 목적

`POST /fetch` — 의미 검색 없이 filter 조건만으로 chunks를 전부 조회한다.
"315페이지의 모든 내용을 알려줘" 같은 구조적 쿼리를 처리한다.

```
POST /fetch
{
  "title": "알고리즘",
  "filter": {"page": 315},
  "limit": 1000
}
```

### 의미 검색과의 차이

| | `/search` | `/fetch` |
|--|-----------|----------|
| 검색 방식 | 벡터 유사도 + BM25 | filter 조건만 |
| top_k 제한 | 있음 | 없음 (limit까지) |
| Reranker | 적용 | 미적용 |
| Personalization | 적용 | 미적용 |
| 용도 | 의미적 질문 | 페이지·파일 기반 구조적 조회 |

### 지원 filter 조건

`page`, `file_name`, `source_type`, `chunk_index`, `content_hash`, `id` — retriever의 `_SCALAR_FIELDS`와 동일.

---

## 19. ANN Index Lazy Propagation ✅ 구현 완료

### 배경: LanceDB delta file과 flat scan 문제

LanceDB는 모든 write를 delta file로 쌓는다. 명시적 ANN 인덱스 없이 `table.search(query_vector)`를 호출하면, LanceDB는 delta file 전체를 대상으로 **brute-force(flat scan)** 를 수행한다. 데이터가 쌓일수록 검색 지연이 선형 증가하며, 인덱스 없이는 병렬화 이득도 없다.

### 수학적 성능 분석

**기호 정의**

| 기호 | 의미 | 값 (bge-m3 기준) |
|------|------|----------------|
| N | 테이블 내 벡터 수 | 500 ~ 100K |
| d | 임베딩 차원 | 1024 (bge-m3) / 1536 (OpenAI) |
| L | IVF num_partitions | ≈ √N, max 256 |
| p | 쿼리 시 탐색 partition 수 | ≈ L / 13 |
| M | PQ num_sub_vectors | 64 (1024의 약수) |
| K | PQ 코드북 크기 | 256 (= 2⁸) |

**Flat Search (인덱스 없음)**
```
T_flat = N × d
```

**IVF-PQ Search (인덱스 있음)**
```
T_IVFPQ = L·d                   ① 모든 centroid까지 거리 계산
        + p·(N/L)·M              ② 선택된 partition 내 PQ 테이블 lookup
        + d·K                    ③ PQ distance table 사전 계산
```

**스피드업 공식**

$$S(N) = \frac{N \cdot d}{L \cdot d + p \cdot \frac{N}{L} \cdot M + d \cdot K}$$

점근 한계 (N → ∞, L=256 고정, d=1024, M=64, p=20):

$$S_\infty = \frac{d \cdot L}{p \cdot M} = \frac{1024 \times 256}{20 \times 64} = \mathbf{205\times}$$

**수치 계산 (d=1024, L=min(256,√N), M=64, p=⌊L/13⌋)**

| N | T_flat | T_IVFPQ | S(N) |
|---|--------|---------|------|
| 256 | 262K | ≈268K | ~0.98× (비효율) |
| 515 | 527K | ≈276K | **~1.9×** |
| 1,000 | 1.02M | ≈285K | **~3.6×** |
| 5,000 | 5.12M | ≈399K | **~12.8×** |
| 10,000 | 10.2M | ≈530K | **~19.3×** |
| 50,000 | 51.2M | ≈1.46M | **~35.1×** |
| 100,000 | 102M | ≈2.51M | **~40.6×** |

**Break-even N**

S(N) = 1 이 되는 N:
```
N_break = d(L + K) / (d - pM/L)
        = 1024 × 512 / (1024 - 5)
        ≈ 515 rows
```

→ **N ≥ 515 부터 ANN index가 flat scan보다 빠름.**

**Recall 분석**

IVF에서 p개 partition만 탐색 시 NN이 포함될 확률:

- p/L = 20/256 ≈ 7.8% 탐색 → **Recall@10 ≈ 94~96%**
- 현재 `RerankStage`가 파이프라인에 존재하므로 실질적 품질 손실 없음

### 구현

인덱스 생성 시점을 **배치 완료 후 lazy하게 defer** 한다. 매 insert마다 rebuild하면 인덱스 관리 오버헤드가 ingestion 비용을 초과한다.

**`store.py:rebuild_ann(title)`** — 배치·재임베딩 완료 후 호출 ([store.py:94](vector_db/store.py#L94))

```
1. SEARCH_MODE=fts → no-op
2. count_rows() < ANN_MIN_ROWS → no-op
3. num_partitions = min(256, max(8, √N))  — IVF
4. dim 스키마에서 자동 추론 → num_sub_vectors = dim의 최대 약수 ∈ [96,64,48,32,16,8,4]  — PQ
5. table.create_index("vector", IvfPq(...), metric="cosine", replace=True)
```

**호출 위치 2곳**

| 위치 | 파일 | 이유 |
|------|------|------|
| `_embed_and_store()` 내 `rebuild_fts()` 직후 | [manager.py:172](vector_db/manager.py#L172) | 신규 문서 인제스트 완료 |
| `reembed_title()` 반환 직전 | [manager.py:447](vector_db/manager.py#L447) | 벡터 교체 후 인덱스 무효화 |

`reembed_title`에서 FTS는 텍스트가 바뀌지 않아 skip이지만, ANN은 벡터가 교체됐으므로 반드시 재구성한다.

### 환경변수

```
ANN_MIN_ROWS=256   # 인덱스 생성 최소 행 수 (break-even ≈ 515, 256은 IVF 구성 최소치)
```

### LanceDB 버전 호환성

현재 설치 버전 **0.30.2** 기준 API:

```python
import lancedb
table.create_index(
    "vector",
    config=lancedb.index.IvfPq(num_partitions=L, num_sub_vectors=M),
    metric="cosine",
    replace=True,
)
```

0.6-0.7 스타일의 kwargs 기반 `create_index(num_partitions=..., num_sub_vectors=...)` 는 **0.30에서 동작하지 않음.**

---

## 20. 이미지 처리 고도화 로드맵 (미구현)

### 20-0. 현재 구현의 한계

현재(섹션 9) 구현은 `_has_significant_visuals()`가 True인 페이지를 **페이지 전체 PNG**로 저장한다.
두 가지 문제가 있다:

| 문제 | 영향 |
|------|------|
| 혼합 페이지(텍스트 80% + 그래프 하나) → 전체 페이지가 이미지로 저장 | LLM이 불필요한 텍스트가 가득한 페이지 이미지를 받음 |
| PPT·슬라이드 자료 → 다이어그램이 벡터 path로 이루어져 있으면 감지 누락 | 핵심 시각 자료가 이미지 없이 텍스트만 전달됨 |

---

### 20-1. 1단계: 래스터 이미지 크롭

#### 기작

PDF에 임베드된 래스터 이미지(JPEG, PNG 등)는 PyMuPDF가 좌표 메타데이터를 이미 들고 있다.
`_has_significant_visuals()`에서 감지용으로만 쓰던 정보를 크롭에도 활용한다.

```python
# 페이지 내 각 래스터 이미지의 페이지 좌표 반환
for img in page.get_images():
    rects = page.get_image_rects(img[0])   # xref → [Rect(x0,y0,x1,y1), ...]
    for rect in rects:
        pix = page.get_pixmap(clip=rect)   # 해당 영역만 렌더링
        pix.save(f"page_{i}_crop_{j}.png")
```

`get_pixmap(clip=rect)`은 clip 영역 바깥 요소 렌더링을 건너뛰므로
전체 페이지 렌더링보다 총 픽셀 수가 줄어든다.

#### 필터링 정책

| 조건 | 처리 |
|------|------|
| 크롭 면적 < 페이지 면적의 2% | 스킵 (로고·아이콘 등 장식 요소) |
| `page.find_tables()` bbox와 70% 이상 겹침 | 스킵 (표 안에 삽입된 래스터) |
| 크롭 실패 | 전체 페이지 PNG로 폴백 (현재 동작 유지) |

#### 스키마 변경

현재: `page_images` 테이블 — `(file_name, page)` → 단일 `image_path` (1:1)

변경 후: 같은 `(file_name, page)`에 여러 행 가능 (1:N)

```
pageimg 테이블
  file_name | page | image_path
  ────────────────────────────────────────────
  ch1.pdf   |  12  | image_store/ch1_abc/page_12_crop_0.png
  ch1.pdf   |  12  | image_store/ch1_abc/page_12_crop_1.png
  ch1.pdf   |  15  | image_store/ch1_abc/page_15_crop_0.png
```

`store.get_page_images()`의 반환 타입을 `dict[tuple[str,int], str]` →
`dict[tuple[str,int], list[str]]`로 변경하고, 검색 응답에서 `image` 필드를
단일 base64가 아닌 리스트로 변경한다.

#### 청크-이미지 매핑 전략: 공간 근접성 (옵션 A)

페이지 텍스트 블록 좌표와 이미지 크롭 bbox의 수직 거리를 계산해
가장 가까운 텍스트 블록이 속한 청크에 해당 이미지를 배정한다.

```python
blocks = page.get_text("blocks")
# blocks: [(x0, y0, x1, y1, text, block_no, block_type), ...]

for crop_rect in crop_rects:
    img_center_y = (crop_rect.y0 + crop_rect.y1) / 2
    nearest = min(blocks, key=lambda b: abs((b[1]+b[3])/2 - img_center_y))
    # nearest 텍스트가 속한 청크 → 이 이미지 배정
```

같은 페이지의 여러 청크 중 공간적으로 가장 가까운 청크 하나만 참조한다.
"Figure N" 명시 참조(`_has_explicit_figure_ref()`)가 있으면 공간 매핑보다 우선한다.

---

### 20-2. 2단계: 벡터 드로잉 클러스터링

#### 기작

PPT 다이어그램·플로우차트·트리는 PDF에 벡터 path 명령어로 저장된다.
`get_drawings()`가 반환하는 개별 path element를 **논리적 그림 단위**로 묶어야 한다.

```
get_drawings() →
  path_0: Rect(10, 20, 80, 60)   ← 박스
  path_1: Rect(78, 38, 120, 42)  ← 화살표 선
  path_2: Rect(118, 20, 180, 60) ← 박스
  ...
```

**Gap 기반 클러스터링**: 두 path의 bbox 사이 거리가 `DRAWING_CLUSTER_GAP_PX` 미만이면 같은 클러스터로 병합.
클러스터 bbox를 최종 크롭 영역으로 사용한다.

#### 필터링 정책

| 조건 | 처리 |
|------|------|
| 클러스터 bbox가 `page.find_tables()` bbox와 70% 이상 겹침 | 스킵 (표 테두리 오염 방지) |
| 클러스터 면적 < 페이지 면적의 3% | 스킵 (구분선·bullet 잡음) |
| 클러스터 내 path가 모두 수평·수직 직선만인 경우 | 스킵 (격자·눈금선) |

#### 환경변수

```
DRAWING_CLUSTER_GAP_PX=15      # 클러스터 병합 gap 임계값 (픽셀)
DRAWING_MIN_AREA_RATIO=0.03    # 클러스터 최소 면적 (페이지 대비)
```

---

### 20-3. 오류 원인 및 정책 요약

| 오류 원인 | 정책 |
|----------|------|
| 표 테두리가 드로잉 클러스터로 오인 | `page.find_tables()` bbox 겹침 70% 이상 → 스킵 |
| 로고·아이콘 같은 소형 래스터 | 면적 < 페이지 2% → 스킵 |
| 한 다이어그램이 여러 클러스터로 쪼개짐 | `DRAWING_CLUSTER_GAP_PX` 조정 (기본 15px) |
| 두 그림이 붙어서 하나로 합쳐짐 | 클러스터 최대 면적 상한 설정 (페이지 면적 60%) |
| 크롭 영역 렌더링 실패 | 전체 페이지 PNG 폴백 |
| 멀티컬럼 레이아웃 공간 매핑 오류 | "Figure N" 명시 참조가 있으면 공간 매핑 무시 |

---

### 20-4. 향후: Multimodal Embedding 기반 매핑

#### 현재 아키텍처의 한계

현재 임베딩 모델(bge-m3, text-embedding-3-small)은 **텍스트 전용**이다.
이미지와 텍스트를 같은 벡터 공간에 매핑하지 못하므로, 이미지-청크 간 의미 유사도를 직접 계산할 수 없다.

#### Cross-Modal Embedding(CLIP) 작동 원리

CLIP(Contrastive Language-Image Pretraining)은 **(이미지, 캡션) 쌍**을 대조 학습해
두 모달리티를 동일한 잠재 공간에 배치한다.

```
"binary tree diagram"  ──[텍스트 인코더]──→  v_text  ─┐
                                                       ├→ cosine similarity
[트리 그림 PNG]         ──[이미지 인코더]──→  v_img   ─┘
```

같은 개념을 나타내는 텍스트와 이미지는 높은 cosine similarity를 가진다.
이를 활용하면 공간 근접성 없이도 "이 청크에 어떤 이미지가 연관되는가"를 의미 기반으로 판단할 수 있다.

#### 왜 지금 당장 도입하기 어려운가

| 문제 | 설명 |
|------|------|
| 벡터 공간 불일치 | bge-m3(1024차원)와 CLIP(512차원)은 다른 공간. 두 모델의 벡터는 직접 비교 불가 |
| 이중 임베딩 비용 | 청크를 bge-m3 + CLIP 두 번 임베딩해야 하거나, 전체를 CLIP으로 교체해야 함 |
| 한국어 성능 | CLIP은 영어 중심 학습. 한국어 학술 텍스트-다이어그램 쌍에서 유사도 신뢰도 낮음 |
| 도메인 미스매치 | CLIP은 자연 이미지 + 캡션으로 학습. 알고리즘 트리·수식 다이어그램은 분포 외 |

#### 전환 조건 및 후보 모델

아래 조건이 충족될 때 전환을 검토한다:

1. 임베딩 모델 교체 결정이 내려졌을 때 (bge-m3 → multimodal 모델)
2. 공간 근접성 매핑의 오류율이 실측에서 유의미하게 높을 때

| 모델 | 특징 | 한국어 |
|------|------|--------|
| `nomic-ai/nomic-embed-multimodal-7b` | 텍스트+이미지 동일 공간, 로컬 실행 가능 | 보통 |
| OpenAI `text-embedding-3-*` (향후 multimodal) | API 기반, 현재 텍스트 전용이지만 multimodal 확장 예정 | 양호 |
| `BAAI/bge-visualized` | bge-m3 계열 multimodal 확장판, 한국어 지원 | 양호 |

**`BAAI/bge-visualized`** 가 현재 아키텍처(bge-m3 텍스트 임베딩 계열)와
가장 연속적으로 전환 가능한 경로다. 같은 벡터 공간을 공유하도록 설계됐으며,
기존 텍스트 chunk 벡터를 재사용하면서 이미지만 추가 임베딩할 수 있다.

#### 전환 시 아키텍처 변화

```
현재:
  chunk text ──[bge-m3]──→ 1024차원 벡터  (LanceDB 저장, 검색용)
  이미지 → 공간 근접성으로 chunk에 배정

전환 후 (bge-visualized):
  chunk text ──[bge-visualized text encoder]──→ 1024차원 벡터  (기존과 동일)
  crop image ──[bge-visualized image encoder]──→ 1024차원 벡터  (같은 공간)
  → cosine similarity로 이미지-청크 최적 매핑 계산
  → 공간 근접성 휴리스틱 불필요
```

`embedder.py`에 `embed_image(image_path) → list[float]` 메서드를 추가하고,
`parser.py`의 크롭 단계 직후 이미지 벡터를 계산해 매핑에 활용한다.

---

## 21. 스캔 PDF OCR ✅ 구현 완료

### 배경 문제

`pymupdf4llm.to_markdown(use_ocr=False)`는 PDF에 텍스트 레이어가 없는 스캔 페이지에서 빈 문자열을 반환한다.
스캔 교재·강의자료를 인제스트하면 chunk가 생성되지 않아 검색 결과가 전혀 나오지 않는다.

### 스캔 페이지 감지 조건

두 조건을 모두 만족하면 스캔 페이지로 판단한다.

```
1. pymupdf4llm 추출 텍스트 길이 < OCR_SCANNED_TEXT_THRESHOLD (기본 50자)
2. 페이지 내 래스터 이미지 중 하나가 페이지 면적의 OCR_SCANNED_COVERAGE_RATIO 이상 차지 (기본 50%)
```

조건 2가 없으면 표지·빈 페이지도 스캔으로 오인하여 불필요한 OCR이 실행된다.

### 페이지 처리 흐름

```
parse_pdf() - 페이지별 처리
    │
    ├─ _is_scanned_page() == True
    │       ↓
    │   _render_page_for_ocr()    ← 2x 해상도(144dpi) 전체 페이지 PNG 렌더링
    │       ↓
    │   get_ocr_provider().ocr()  ← OCR 텍스트 추출
    │       ↓
    │   text = OCR 결과, image_paths = [ocr_path]
    │
    ├─ _has_significant_visuals() == True  ← 기존 래스터/벡터 크롭 경로
    │       ↓
    │   text = pymupdf4llm 결과, image_paths = [crops...]
    │
    └─ 텍스트 전용 페이지
            ↓
        text = pymupdf4llm 결과, image_paths = []
```

스캔 페이지는 OCR PNG가 `image_paths`에 포함되므로 멀티모달 RAG 파이프라인에서 시각 자료로도 활용된다.

### OCR Provider 추상화 (`ocr.py`)

향후 외부 API(Claude Vision, Google Vision 등)로 교체를 고려해 provider 패턴으로 구현한다.
환경변수 `OCR_PROVIDER` 하나만 바꾸면 구현체를 교체할 수 있다.

```
OcrProvider (ABC)
    ├─ NullOcrProvider    ← OCR_PROVIDER=none (기본값, 빈 문자열 반환)
    └─ EasyOcrProvider    ← OCR_PROVIDER=easyocr

# 향후 추가 예시
    └─ ClaudeVisionProvider   ← OCR_PROVIDER=claude
    └─ GoogleVisionProvider   ← OCR_PROVIDER=google
```

`get_ocr_provider()`는 lazy singleton으로, 첫 스캔 페이지가 감지될 때 모델을 초기화한다.
스캔 페이지가 없는 문서에서는 EasyOCR 모델이 메모리에 올라오지 않는다.

### EasyOCR 선택 이유

| 항목 | 내용 |
|------|------|
| 프레임워크 | PyTorch 재사용 — 이미 설치된 `torch 2.11.0+cu130` 위에서 동작 |
| 추가 DL 프레임워크 | 없음 (PaddleOCR은 PaddlePaddle 별도 설치 필요, CUDA 13.0 미지원 위험) |
| 한국어 지원 | `['ko', 'en']` 언어 모델 — 한영 혼재 문서 처리 가능 |
| 설치 | `pip install easyocr` |

### 환경변수

```
OCR_PROVIDER=none                # "none" | "easyocr"
OCR_LANGUAGES=ko,en              # OCR_PROVIDER=easyocr 시 인식 언어
OCR_SCANNED_TEXT_THRESHOLD=50    # 이 글자 수 미만이면 스캔 후보
OCR_SCANNED_COVERAGE_RATIO=0.5   # 래스터가 페이지 면적의 이 비율 이상 → 스캔 확정
OCR_RENDER_SCALE=2.0             # OCR 렌더링 해상도 배율 (2.0 = 144dpi)
```

### 설치

```bash
pip install easyocr
```

### 트레이드오프

| 항목 | 영향 |
|------|------|
| 스캔 페이지 텍스트 추출 | NullOcrProvider 대비 품질 향상 |
| 초기화 지연 | 첫 스캔 페이지에서 EasyOCR 모델 로드 (~수 초) |
| 메모리 | EasyOCR 모델 ~300MB (GPU 사용 시 VRAM) |
| 처리 속도 | GPU 기준 ~0.5–1s/페이지, CPU는 ~3–5s/페이지 |
| 일반 PDF | 변화 없음 — 스캔 감지 실패 시 기존 pymupdf4llm 경로 그대로 |
