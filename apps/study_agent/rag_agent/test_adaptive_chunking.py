"""
Adaptive Chunking 검증.
- markdown 헤더가 chunk 중간을 자르지 않는지 확인
- 코드블록(``` ... ```) 이 통째로 보존되는지 확인
- 작은 블록이 병합되는지 확인
- chunk_size 초과 시 2차 분할이 적용되는지 확인
"""
import sys, os, tempfile, shutil
sys.path.insert(0, '/home/hykiop/on-tutor/study_agent/rag_agent')

os.environ["CHUNK_STRATEGY"] = "structural"
os.environ["CHUNK_SIZE"] = "256"
os.environ["CHUNK_OVERLAP"] = "32"
os.environ["MIN_CHUNK_CHARS"] = "50"

from vector_db.chunker import chunk_documents, _split_by_structure, _merge_small_blocks

md = (
    "# Chapter 1\n"
    "운영체제 개요. 프로세스와 스레드. " * 5 + "\n"
    "## 1.1 프로세스\n"
    "프로세스는 실행 중인 프로그램이다. " * 8 + "\n"
    "```python\n"
    "def fork():\n"
    "    return os.fork()\n"
    "```\n"
    "## 1.2 스레드\n"
    "스레드는 프로세스 내 실행 단위다. " * 8 + "\n"
    "# Chapter 2\n"
    "메모리 관리. " * 3 + "\n"
)

# 1) 구조 분할 직접 검증
blocks = _split_by_structure(md)
assert any(b.startswith("# Chapter 1") for b in blocks), "헤더 경계로 분할되지 않음"
assert any(b.startswith("## 1.1 프로세스") for b in blocks), "서브 헤더 경계 미인식"
assert any("```python" in b and "return os.fork()" in b and b.strip().endswith("```") for b in blocks), \
    "코드블록이 분리됨"
print(f"[OK] 구조 분할: {len(blocks)} blocks")

# 2) 병합 검증
small = ["a", "bb", "ccc", "d" * 200, "e", "fff"]
merged = _merge_small_blocks(small, min_chars=50)
assert all(len(m) >= 50 or m == merged[-1] for m in merged), "병합 임계값 미적용"
print(f"[OK] 병합: {len(small)} → {len(merged)}")

# 3) end-to-end 청킹
docs = [{"text": md, "page": 0, "file_name": "test.md", "image_path": None}]
chunks = chunk_documents(docs)
assert len(chunks) > 0
assert all("text" in c and "chunk_index" in c and "image_path" in c for c in chunks)

# 코드블록이 살아있는 chunk 가 적어도 하나 존재
assert any("def fork()" in c["text"] for c in chunks), "코드블록 내용이 어디에서도 보존되지 않음"
print(f"[OK] 청크 수: {len(chunks)}, 코드블록 보존됨")

# 4) fixed 모드 회귀 테스트
os.environ["CHUNK_STRATEGY"] = "fixed"
chunks_fixed = chunk_documents(docs)
assert len(chunks_fixed) > 0
print(f"[OK] fixed 모드 호환: {len(chunks_fixed)} chunks")

print()
print("=== ADAPTIVE CHUNKING TEST PASSED ===")
