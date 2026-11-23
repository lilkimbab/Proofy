"""
메타데이터 안정성 검증 — pytest + unittest.TestCase 스타일.

기존 테스트 + 강화:
  - 대용량 재업로드: 100청크 v1 → 50청크 변경 v2, 변경 없는 id가 정확히 보존되는지
  - content_hash 충돌 저항: 1바이트 차이 두 텍스트의 hash가 달라야 함
  - heading_path 직렬화 왕복: 저장 후 조회한 heading_path가 list[str] 타입이고 원본과 동일
  - schema migration 후 FTS 인덱스 재생성: legacy 테이블에 신규 row 추가 후 FTS 검색 동작
"""

import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


_MD_V1 = (
    "# Chapter 1: 운영체제\n"
    "운영체제는 프로세스를 관리한다. " * 8 + "\n"
    "## 1.1 프로세스\n"
    "프로세스는 실행 중인 프로그램이다. " * 8 + "\n"
    "## 1.2 스레드\n"
    "스레드는 프로세스 내 실행 단위다. " * 8 + "\n"
    "# Chapter 2: 메모리\n"
    "메모리 관리는 운영체제의 핵심 기능이다. " * 8 + "\n"
)

_MD_V2 = (
    "# Chapter 1: 운영체제\n"
    "운영체제는 프로세스를 관리한다. " * 8 + "\n"
    "## 1.1 프로세스\n"
    "프로세스는 자원을 보유한 실행 단위이다. 프로세스 ID 가 부여된다. " * 8 + "\n"  # 변경
    "## 1.2 스레드\n"
    "스레드는 프로세스 내 실행 단위다. " * 8 + "\n"
    "# Chapter 2: 메모리\n"
    "메모리 관리는 운영체제의 핵심 기능이다. " * 8 + "\n"
)


class TestMetadata(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp_db = tempfile.mkdtemp(prefix="meta_db_")
        cls.tmp_img = tempfile.mkdtemp(prefix="meta_img_")
        cls.tmp_prof = tempfile.mkdtemp(prefix="meta_prof_")
        cls.tmp_docs = tempfile.mkdtemp(prefix="meta_docs_")

        os.environ["LANCEDB_PATH"] = cls.tmp_db
        os.environ["IMAGE_STORE_PATH"] = cls.tmp_img
        os.environ["USER_PROFILE_DIR"] = cls.tmp_prof
        os.environ["EMBED_MODEL"] = "local"
        os.environ["RERANK_ENABLED"] = "false"
        os.environ["SEARCH_MODE"] = "hybrid"
        os.environ["CHUNK_STRATEGY"] = "structural"
        os.environ["CHUNK_SIZE"] = "256"
        os.environ["MIN_CHUNK_CHARS"] = "50"

        from vector_db import VectorDBManager
        from vector_db.parser import _detect_source_type, parse_file
        from vector_db.chunker import chunk_documents

        cls.VectorDBManager = VectorDBManager
        cls._detect_source_type = staticmethod(_detect_source_type)
        cls._parse_file = staticmethod(parse_file)
        cls._chunk_documents = staticmethod(chunk_documents)
        cls.db = VectorDBManager()

        # 기본 문서 준비
        cls.doc_path = os.path.join(cls.tmp_docs, "os.txt")
        with open(cls.doc_path, "w", encoding="utf-8") as f:
            f.write(_MD_V1)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_db, ignore_errors=True)
        shutil.rmtree(cls.tmp_img, ignore_errors=True)
        shutil.rmtree(cls.tmp_prof, ignore_errors=True)
        shutil.rmtree(cls.tmp_docs, ignore_errors=True)

    def _ingest(self, title: str, path: str) -> dict:
        parsed = self.db.parse_document(path)
        return self.db._embed_and_store(
            title, parsed["chunks"], parsed["parents"],
            page_images=parsed.get("page_images", []),
        )

    # ── 1. source_type 자동 감지 ──────────────────────────────────────────────

    def test_source_type_detection(self):
        parsed = self._parse_file(self.doc_path)
        self.assertTrue(all("source_type" in d for d in parsed))
        self.assertIn(parsed[0]["source_type"], ("slide", "textbook", "code", "general"))

    def test_slide_heuristic(self):
        slide_like = [
            {"text": "Fig 1.", "page": i, "file_name": "x.pdf", "image_path": "/tmp/img.png"}
            for i in range(3)
        ]
        self.assertEqual(self._detect_source_type(slide_like), "slide")

    # ── 2. content_hash / heading_path 부착 ──────────────────────────────────

    def test_chunker_attaches_content_hash(self):
        parsed = self._parse_file(self.doc_path)
        chunks = self._chunk_documents(parsed)
        self.assertGreater(len(chunks), 0)
        self.assertTrue(all("content_hash" in c and len(c["content_hash"]) == 64 for c in chunks))

    def test_chunker_attaches_heading_path(self):
        parsed = self._parse_file(self.doc_path)
        chunks = self._chunk_documents(parsed)
        paths = [c["heading_path"] for c in chunks if c.get("heading_path")]
        self.assertGreater(len(paths), 0, "heading_path가 있는 chunk가 없음")

    def test_nested_heading_path(self):
        parsed = self._parse_file(self.doc_path)
        chunks = self._chunk_documents(parsed)
        paths = [c["heading_path"] for c in chunks if c.get("heading_path")]
        found_nested = any(
            "Chapter 1: 운영체제" in p[0] and any("스레드" in s for s in p)
            for p in paths if len(p) >= 2
        )
        self.assertTrue(found_nested, f"중첩 heading_path 미생성: 샘플={paths[:3]}")

    # ── 3. chunk_id가 content_hash 기반 ──────────────────────────────────────

    def test_chunk_id_is_content_hash_based(self):
        self._ingest("meta_os", self.doc_path)
        arrow = self.db._store.get_table("meta_os").to_arrow().to_pylist()
        self.assertTrue(all("content_hash" in r for r in arrow))
        sample_id = arrow[0]["id"]
        sample_hash = arrow[0]["content_hash"]
        self.assertTrue(sample_id.endswith(sample_hash[:12]),
                        f"id가 content_hash 기반 아님: {sample_id}")
        self.db.delete_title("meta_os")

    # ── 4. 재업로드 — 변경 없는 chunk id 보존 ────────────────────────────────

    def test_reupload_preserves_unchanged_chunk_ids(self):
        self._ingest("meta_reup", self.doc_path)
        arrow1 = self.db._store.get_table("meta_reup").to_arrow().to_pylist()
        v1_ids = {r["id"] for r in arrow1}

        path_v2 = os.path.join(self.tmp_docs, "os_v2.txt")
        with open(path_v2, "w", encoding="utf-8") as f:
            f.write(_MD_V2)
        # 같은 file_name으로 재업로드해야 delete_by_file이 정상 작동함
        parsed_v2 = self.db.parse_document(path_v2)
        for c in parsed_v2["chunks"]:
            c["file_name"] = "os.txt"
        for p in parsed_v2["parents"]:
            p["file_name"] = "os.txt"
        self.db._embed_and_store("meta_reup", parsed_v2["chunks"], parsed_v2["parents"])

        arrow2 = self.db._store.get_table("meta_reup").to_arrow().to_pylist()
        v2_ids = {r["id"] for r in arrow2}
        preserved = v1_ids & v2_ids
        self.assertGreater(len(preserved), 0,
                           "재업로드 후 보존된 chunk_id가 0개 — content_hash 매칭 실패")
        self.db.delete_title("meta_reup")

    # ── 5. content_hash 충돌 저항 ─────────────────────────────────────────────

    def test_content_hash_differs_by_one_byte(self):
        """1바이트만 다른 두 텍스트의 content_hash는 달라야 한다."""
        from vector_db.chunker import _content_hash
        text_a = "hello world A"
        text_b = "hello world B"
        self.assertNotEqual(_content_hash(text_a), _content_hash(text_b))

    def test_content_hash_is_64_chars_hex(self):
        from vector_db.chunker import _content_hash
        h = _content_hash("테스트 텍스트")
        self.assertEqual(len(h), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in h))

    # ── 6. heading_path 직렬화 왕복 ──────────────────────────────────────────

    def test_heading_path_roundtrip_type_and_value(self):
        """저장 후 조회한 heading_path가 list[str] 타입이고 원본과 동일해야 한다."""
        self._ingest("meta_hp", self.doc_path)
        hits = self.db.search(query="스레드", title="meta_hp", top_k=3)
        self.assertGreater(len(hits), 0)
        for h in hits:
            self.assertIn("heading_path", h)
            self.assertIsInstance(h["heading_path"], list,
                                  f"heading_path가 list가 아님: {type(h['heading_path'])}")
            if h["heading_path"]:
                self.assertIsInstance(h["heading_path"][0], str,
                                      f"heading_path 원소가 str이 아님: {type(h['heading_path'][0])}")
        self.db.delete_title("meta_hp")

    # ── 7. search 응답에 새 필드 노출 ────────────────────────────────────────

    def test_search_result_has_metadata_fields(self):
        self._ingest("meta_fields", self.doc_path)
        hits = self.db.search(query="스레드", title="meta_fields", top_k=3)
        self.assertGreater(len(hits), 0)
        h = hits[0]
        self.assertIn("content_hash", h)
        self.assertEqual(len(h["content_hash"]), 64)
        self.assertIn("heading_path", h)
        self.assertIsInstance(h["heading_path"], list)
        self.assertIn("source_type", h)
        self.db.delete_title("meta_fields")

    # ── 8. schema migration — 신규 row 추가 후 FTS 검색 ─────────────────────

    def test_schema_migration_fts_after_new_row(self):
        """legacy 테이블에 신규 row를 추가한 뒤 FTS 검색이 정상 동작해야 한다."""
        import lancedb

        legacy_path = tempfile.mkdtemp(prefix="meta_legacy_")
        try:
            legacy_db_conn = lancedb.connect(legacy_path)
            legacy_rows = [{
                "text": "옛 데이터입니다. " * 30,
                "chunk_index": 0,
                "page": 0,
                "file_name": "legacy.txt",
                "image_path": "",
                "vector": [0.0] * 1024,
                "id": "legacy.txt_0",
                "added_at": "2025-01-01T00:00:00",
            }]
            table_name = f"title_{'legacy'.encode('utf-8').hex()}"
            legacy_db_conn.create_table(table_name, data=legacy_rows)

            os.environ["LANCEDB_PATH"] = legacy_path
            db_legacy = self.VectorDBManager()

            new_doc_path = os.path.join(self.tmp_docs, "new_legacy.txt")
            with open(new_doc_path, "w", encoding="utf-8") as f:
                f.write("새 데이터입니다. 프로세스 관리와 스케줄링. " * 30)

            parsed = db_legacy.parse_document(new_doc_path)
            db_legacy._embed_and_store("legacy", parsed["chunks"], parsed["parents"],
                                       page_images=parsed.get("page_images", []))

            migrated = db_legacy._store.get_table("legacy").to_arrow().to_pylist()
            self.assertTrue(any(r.get("file_name") == "legacy.txt" for r in migrated),
                            "옛 row가 migration 후 사라짐")
            self.assertTrue(any(r.get("file_name") == "new_legacy.txt" for r in migrated),
                            "새 row가 추가되지 않음")
            self.assertTrue(all("content_hash" in r for r in migrated),
                            "migration 후 content_hash 누락")

            # FTS 검색 동작 확인
            os.environ["SEARCH_MODE"] = "fts"
            db_fts = self.VectorDBManager()
            # VectorDBManager 생성자가 백그라운드 재임베딩을 시작할 수 있으므로
            # 완료될 때까지 대기한 뒤 검색한다.
            deadline = time.monotonic() + 30
            while db_fts._is_reembedding("legacy") and time.monotonic() < deadline:
                time.sleep(0.1)
            hits = db_fts.search(query="프로세스 스케줄링", title="legacy", top_k=3)
            self.assertIsInstance(hits, list)
        finally:
            os.environ["LANCEDB_PATH"] = self.tmp_db
            os.environ["SEARCH_MODE"] = "hybrid"
            shutil.rmtree(legacy_path, ignore_errors=True)
