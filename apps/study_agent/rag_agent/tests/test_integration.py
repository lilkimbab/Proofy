"""
Vector DB 통합 테스트 — pytest + unittest.TestCase 스타일.

기존 CRUD 스모크 테스트 + 까다로운 케이스 추가:
  - 중복 ingest: content_hash upsert로 chunk 수가 2배가 되면 안 됨
  - 대용량 문서: 1000 문장 txt → top_k=10 정확히 10개
  - 상태 전이: 빈 결과 → ingest → 결과 있음
  - 다중 파일 filter 정확도: 파일 A/B 동일 title → file_name=A 필터 시 A만 반환
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp_db = tempfile.mkdtemp(prefix="int_db_")
        cls.tmp_img = tempfile.mkdtemp(prefix="int_img_")
        cls.tmp_prof = tempfile.mkdtemp(prefix="int_prof_")
        cls.tmp_docs = tempfile.mkdtemp(prefix="int_docs_")

        os.environ["LANCEDB_PATH"] = cls.tmp_db
        os.environ["IMAGE_STORE_PATH"] = cls.tmp_img
        os.environ["USER_PROFILE_DIR"] = cls.tmp_prof
        os.environ["EMBED_MODEL"] = "local"
        os.environ["RERANK_ENABLED"] = "false"
        os.environ["SEARCH_MODE"] = "hybrid"

        from vector_db import VectorDBManager
        cls.VectorDBManager = VectorDBManager
        cls.db = VectorDBManager()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_db, ignore_errors=True)
        shutil.rmtree(cls.tmp_img, ignore_errors=True)
        shutil.rmtree(cls.tmp_prof, ignore_errors=True)
        shutil.rmtree(cls.tmp_docs, ignore_errors=True)

    # ── 헬퍼 ──────────────────────────────────────────────────────────────────

    def _make_txt(self, content: str, name: str = "doc.txt") -> str:
        path = os.path.join(self.tmp_docs, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def _ingest(self, title: str, content: str, name: str = "doc.txt") -> dict:
        path = self._make_txt(content, name)
        parsed = self.db.parse_document(path)
        return self.db._embed_and_store(
            title, parsed["chunks"], parsed["parents"],
            page_images=parsed.get("page_images", []),
        )

    # ── 1. 기본 CRUD ──────────────────────────────────────────────────────────

    def test_01_ingest_and_search(self):
        result = self._ingest("OS", "운영체제는 프로세스를 관리한다. " * 40)
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(result["chunks_added"], 1)

        hits = self.db.search(query="프로세스 관리", title="OS", top_k=3)
        self.assertIsInstance(hits, list)
        self.assertGreater(len(hits), 0)
        self.assertTrue(all(
            "parent_text" in h and "source" in h and "page" in h and "score" in h
            for h in hits
        ))

    def test_02_list_titles(self):
        self.assertIn("OS", self.db.list_titles())

    def test_03_list_files(self):
        files = self.db.list_files("OS")
        self.assertGreaterEqual(len(files), 1)

    def test_04_search_with_filter(self):
        files = self.db.list_files("OS")
        file_name = files[0]
        hits = self.db.search(
            query="운영체제", title="OS", top_k=5,
            filter={"file_name": file_name},
        )
        self.assertIsInstance(hits, list)
        self.assertTrue(all(h["source"] == file_name for h in hits),
                        f"필터가 동작하지 않음: {set(h['source'] for h in hits)}")

    def test_05_delete_file(self):
        self._ingest("OS", "자료구조는 데이터를 효율적으로 저장하는 방법이다. " * 40, name="doc2.txt")
        files_before = self.db.list_files("OS")
        self.assertEqual(len(files_before), 2, f"파일이 2개여야 함: {files_before}")
        self.db.delete_file(title="OS", file_name=files_before[0])
        files_after = self.db.list_files("OS")
        self.assertEqual(len(files_after), 1, f"삭제 후 파일이 1개여야 함: {files_after}")

    def test_06_delete_title(self):
        self.db.delete_title("OS")
        self.assertNotIn("OS", self.db.list_titles())

    def test_07_empty_search_nonexistent_title(self):
        hits = self.db.search(query="아무말", title="없는타이틀")
        self.assertEqual(hits, [])

    # ── 2. 까다로운 케이스 ─────────────────────────────────────────────────────

    def test_08_duplicate_ingest_no_double_chunks(self):
        """동일 파일을 2번 ingest해도 DB row 수가 2배가 되면 안 됨 (content_hash upsert)."""
        title = "dup_test"
        content = "중복 ingest 테스트 문서입니다. 스케줄링 알고리즘과 메모리 관리. " * 30
        r1 = self._ingest(title, content, name="dup.txt")
        count1 = r1["chunks_added"]
        self._ingest(title, content, name="dup.txt")
        rows = self.db._store.get_all_rows(title)
        self.assertEqual(
            len(rows), count1,
            f"2번째 ingest 후 rows={len(rows)}개, 1번째={count1}개 — upsert이므로 같아야 함",
        )
        self.db.delete_title(title)

    def test_09_large_document_top_k_exact(self):
        """1000 문장 이상 txt를 ingest하고 top_k=10이 정확히 10개를 반환하는지 확인."""
        title = "large_doc"
        content = " ".join(
            f"문장 {i}: 운영체제와 메모리 관리, 프로세스 스케줄링, 페이지 교체 알고리즘."
            for i in range(1000)
        )
        self._ingest(title, content, name="large.txt")
        hits = self.db.search(query="운영체제 메모리 프로세스", title=title, top_k=10)
        self.assertEqual(len(hits), 10, f"top_k=10 요청 시 {len(hits)}개 반환됨")
        self.db.delete_title(title)

    def test_10_state_transition_empty_to_populated(self):
        """존재하지 않는 title 검색 → [] → ingest → 결과 있음 상태 전이 테스트."""
        title = "state_trans"
        hits_before = self.db.search(query="테스트 쿼리", title=title)
        self.assertEqual(hits_before, [], "ingest 전 빈 리스트여야 함")

        self._ingest(title, "상태 전이 테스트 문서입니다. 검색 가능한 의미 있는 내용. " * 20)
        hits_after = self.db.search(query="상태 전이 테스트", title=title)
        self.assertGreater(len(hits_after), 0, "ingest 후 결과가 있어야 함")
        self.db.delete_title(title)

    def test_11_filter_accuracy_two_files_same_title(self):
        """파일 A, B를 같은 title에 ingest → file_name=A 필터 시 결과가 모두 A에서만."""
        title = "filter_acc"
        self._ingest(title, "파일A: 알고리즘과 자료구조, 정렬, 탐색. " * 30, name="fileA.txt")
        self._ingest(title, "파일B: 네트워크와 프로토콜, TCP, UDP. " * 30, name="fileB.txt")

        hits = self.db.search(
            query="알고리즘 자료구조", title=title, top_k=5,
            filter={"file_name": "fileA.txt"},
        )
        self.assertTrue(
            all(h["source"] == "fileA.txt" for h in hits),
            f"fileA.txt 필터 결과에 다른 파일 포함됨: {set(h['source'] for h in hits)}",
        )
        self.db.delete_title(title)
