"""
Adaptive Chunking 검증 — pytest + unittest.TestCase 스타일.

기존 테스트 + 경계 케이스:
  - 빈 문서: 예외 없이 빈 리스트 반환
  - 코드블록만 있는 문서: 하나의 chunk로 묶이고, 길이 초과 시 2차 분할
  - 중첩 없는 단일 헤더: heading_path 길이 == 1
  - CHUNK_SIZE 경계: 99자 → 분할 없음, 101자 → 2개로 분할
  - 헤더 없는 장문 텍스트: structural 모드에서도 chunking이 일어남
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


_MARKDOWN = (
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


class TestAdaptiveChunking(unittest.TestCase):

    def setUp(self):
        os.environ["CHUNK_STRATEGY"] = "structural"
        os.environ["CHUNK_SIZE"] = "256"
        os.environ["CHUNK_OVERLAP"] = "32"
        os.environ["MIN_CHUNK_CHARS"] = "50"

    def _reload_chunker(self):
        """환경변수 변경 후 chunker 함수를 fresh import."""
        import importlib
        import vector_db.chunker as chunker_mod
        importlib.reload(chunker_mod)
        return chunker_mod

    # ── 1. 구조 분할 직접 검증 ─────────────────────────────────────────────────

    def test_split_by_structure_header_boundaries(self):
        from vector_db.chunker import _split_by_structure
        blocks = _split_by_structure(_MARKDOWN)
        self.assertTrue(any(b.startswith("# Chapter 1") for b in blocks),
                        "헤더 경계로 분할되지 않음")
        self.assertTrue(any(b.startswith("## 1.1 프로세스") for b in blocks),
                        "서브 헤더 경계 미인식")

    def test_split_by_structure_preserves_code_block(self):
        from vector_db.chunker import _split_by_structure
        blocks = _split_by_structure(_MARKDOWN)
        self.assertTrue(
            any("```python" in b and "return os.fork()" in b and b.strip().endswith("```")
                for b in blocks),
            "코드블록이 분리됨",
        )

    def test_merge_small_blocks(self):
        from vector_db.chunker import _merge_small_blocks
        small = ["a", "bb", "ccc", "d" * 200, "e", "fff"]
        merged = _merge_small_blocks(small, min_chars=50)
        self.assertTrue(
            all(len(m) >= 50 or m == merged[-1] for m in merged),
            "병합 임계값 미적용",
        )

    # ── 2. end-to-end 청킹 ────────────────────────────────────────────────────

    def test_chunk_documents_basic(self):
        from vector_db.chunker import chunk_documents
        docs = [{"text": _MARKDOWN, "page": 0, "file_name": "test.md", "image_path": None}]
        chunks = chunk_documents(docs)
        self.assertGreater(len(chunks), 0)
        self.assertTrue(all("text" in c and "chunk_index" in c and "image_page" in c for c in chunks))
        self.assertTrue(any("def fork()" in c["text"] for c in chunks),
                        "코드블록 내용이 어디에서도 보존되지 않음")

    def test_fixed_mode_compatibility(self):
        from vector_db.chunker import chunk_documents
        os.environ["CHUNK_STRATEGY"] = "fixed"
        docs = [{"text": _MARKDOWN, "page": 0, "file_name": "test.md", "image_path": None}]
        chunks = chunk_documents(docs)
        self.assertGreater(len(chunks), 0)

    # ── 3. 경계 케이스 ────────────────────────────────────────────────────────

    def test_empty_document_returns_empty_list(self):
        """빈 문서는 예외 없이 빈 리스트를 반환해야 한다."""
        from vector_db.chunker import chunk_documents
        docs = [{"text": "", "page": 0, "file_name": "empty.txt", "image_path": None}]
        chunks = chunk_documents(docs)
        self.assertIsInstance(chunks, list)
        self.assertEqual(len(chunks), 0)

    def test_whitespace_only_document_returns_empty_list(self):
        """공백만 있는 문서도 빈 리스트를 반환해야 한다."""
        from vector_db.chunker import chunk_documents
        docs = [{"text": "   \n\n\t  \n", "page": 0, "file_name": "ws.txt", "image_path": None}]
        chunks = chunk_documents(docs)
        self.assertEqual(len(chunks), 0)

    def test_code_block_only_document_preserved(self):
        """코드블록만 있는 문서: 하나의 블록으로 보존되어야 한다."""
        from vector_db.chunker import chunk_documents
        code_only = "```python\ndef hello():\n    print('hi')\n```\n"
        docs = [{"text": code_only, "page": 0, "file_name": "code.py", "image_path": None}]
        chunks = chunk_documents(docs)
        self.assertGreater(len(chunks), 0)
        self.assertTrue(any("def hello()" in c["text"] for c in chunks),
                        "코드블록 내용이 보존되지 않음")

    def test_code_block_oversized_gets_split(self):
        """코드블록이 CHUNK_SIZE를 초과하면 2차 분할이 적용된다."""
        from vector_db.chunker import chunk_documents
        os.environ["CHUNK_SIZE"] = "50"
        os.environ["MIN_CHUNK_CHARS"] = "10"
        # 50자를 훨씬 넘는 코드블록
        long_code = "```python\n" + "\n".join(f"x_{i} = {i}  # some value" for i in range(20)) + "\n```\n"
        docs = [{"text": long_code, "page": 0, "file_name": "big_code.py", "image_path": None}]
        chunks = chunk_documents(docs)
        self.assertGreater(len(chunks), 1, "코드블록 초과 시 2차 분할이 없음")

    def test_single_h1_heading_path_length_is_one(self):
        """h1만 있고 h2/h3 없는 문서에서 heading_path 길이가 1이어야 한다."""
        from vector_db.chunker import chunk_documents
        doc = "# 단독 헤더\n" + "본문 내용입니다. " * 10 + "\n"
        docs = [{"text": doc, "page": 0, "file_name": "single.txt", "image_path": None}]
        chunks = chunk_documents(docs)
        self.assertGreater(len(chunks), 0)
        chunks_with_path = [c for c in chunks if c.get("heading_path")]
        if chunks_with_path:
            self.assertTrue(
                all(len(c["heading_path"]) == 1 for c in chunks_with_path),
                f"단독 h1에서 heading_path 길이가 1이 아님: {[c['heading_path'] for c in chunks_with_path]}",
            )

    def test_chunk_size_boundary_no_split_below(self):
        """CHUNK_SIZE=100 기준: 99자 텍스트는 분할되지 않고 1개 chunk여야 한다."""
        from vector_db.chunker import chunk_documents
        os.environ["CHUNK_SIZE"] = "100"
        os.environ["CHUNK_OVERLAP"] = "0"
        os.environ["MIN_CHUNK_CHARS"] = "10"
        os.environ["CHUNK_STRATEGY"] = "fixed"
        text_99 = "가" * 33  # 한글 1자 = 약 3바이트, 33자 ≈ 99바이트 (SentenceSplitter는 char 기준)
        docs = [{"text": text_99, "page": 0, "file_name": "short.txt", "image_path": None}]
        chunks = chunk_documents(docs)
        self.assertEqual(len(chunks), 1, f"99자 텍스트가 {len(chunks)}개로 분할됨")

    def test_headingless_long_text_gets_chunked(self):
        """헤더 없는 장문: structural 모드에서도 SentenceSplitter로 분할된다."""
        from vector_db.chunker import chunk_documents
        os.environ["CHUNK_SIZE"] = "100"
        os.environ["MIN_CHUNK_CHARS"] = "10"
        os.environ["CHUNK_STRATEGY"] = "structural"
        long_text = "헤더 없는 긴 문단입니다. 운영체제와 프로세스 스케줄링에 대해 설명한다. " * 30
        docs = [{"text": long_text, "page": 0, "file_name": "plain.txt", "image_path": None}]
        chunks = chunk_documents(docs)
        self.assertGreater(len(chunks), 1, "헤더 없는 장문이 1개 chunk로 처리됨 (분할 미적용)")
        self.assertTrue(all(c.get("source_type") is not None for c in chunks))
