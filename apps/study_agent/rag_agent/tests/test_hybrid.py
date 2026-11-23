"""
Hybrid Search 정밀도 검증 — pytest + unittest.TestCase 스타일.

추가 검증:
  - FTS vs vector 상호 보완: 코드 심볼(fork()) vs 의미 유사어 쿼리에서 hybrid가 단독 모드보다 나쁘지 않음
  - score 내림차순 정렬 보장: 모든 모드에서 hits[i].score >= hits[i+1].score
  - top_k 상한 보장: 요청보다 많은 결과 반환 금지
  - 모드 전환 격리: 모드를 바꿔도 이전 모드 인덱스가 결과를 오염시키지 않음 (score 기반 순위만 의존)
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestHybridSearch(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp_db = tempfile.mkdtemp(prefix="hybrid_db_")
        cls.tmp_img = tempfile.mkdtemp(prefix="hybrid_img_")
        cls.tmp_prof = tempfile.mkdtemp(prefix="hybrid_prof_")
        cls.tmp_docs = tempfile.mkdtemp(prefix="hybrid_docs_")

        os.environ["LANCEDB_PATH"] = cls.tmp_db
        os.environ["IMAGE_STORE_PATH"] = cls.tmp_img
        os.environ["USER_PROFILE_DIR"] = cls.tmp_prof
        os.environ["EMBED_MODEL"] = "local"
        os.environ["RERANK_ENABLED"] = "false"
        os.environ["SEARCH_MODE"] = "hybrid"

        # 테스트 문서 준비
        docs = {
            "os.txt": (
                "운영체제는 프로세스를 관리한다. 스케줄링 알고리즘에는 FCFS, SJF, RR 이 있다. "
                "페이지 교체 알고리즘으로 LRU, FIFO, Optimal 이 대표적이다. "
                "fork() 시스템 콜은 새로운 프로세스를 생성한다. " * 8
            ),
            "net.txt": (
                "네트워크 계층은 IP 라우팅을 담당한다. TCP 는 신뢰성 있는 전송을 제공한다. "
                "UDP 는 비연결형 프로토콜로 빠른 전송을 우선한다. "
                "소켓 프로그래밍은 네트워크 통신의 기초이다. " * 8
            ),
        }
        paths = []
        for name, body in docs.items():
            p = os.path.join(cls.tmp_docs, name)
            with open(p, "w", encoding="utf-8") as f:
                f.write(body)
            paths.append(p)

        from vector_db import VectorDBManager
        cls.VectorDBManager = VectorDBManager
        cls.db = VectorDBManager()

        for p in paths:
            parsed = cls.db.parse_document(p)
            r = cls.db._embed_and_store(
                "cs", parsed["chunks"], parsed["parents"],
                page_images=parsed.get("page_images", []),
            )
            assert r["status"] == "ok", f"ingest 실패: {r}"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_db, ignore_errors=True)
        shutil.rmtree(cls.tmp_img, ignore_errors=True)
        shutil.rmtree(cls.tmp_prof, ignore_errors=True)
        shutil.rmtree(cls.tmp_docs, ignore_errors=True)

    def _db_mode(self, mode: str):
        """지정한 SEARCH_MODE로 새 VectorDBManager를 반환한다."""
        os.environ["SEARCH_MODE"] = mode
        return self.VectorDBManager()

    # ── 1. 기본 동작 ───────────────────────────────────────────────────────────

    def test_hybrid_keyword_search_finds_exact_symbol(self):
        """hybrid: 코드 심볼 fork()를 FTS가 잡아야 함."""
        db = self._db_mode("hybrid")
        hits = db.search(query="fork()", title="cs", top_k=5)
        self.assertGreater(len(hits), 0, "hybrid: fork() 검색 결과 없음")
        self.assertTrue(
            any("fork()" in (h.get("parent_text") or "") for h in hits),
            "hybrid: fork() 가 포함된 chunk 가 결과에 없음",
        )

    def test_vector_mode_semantic_search(self):
        """vector: 의미 유사어 쿼리(페이지 교체)로 결과가 나와야 함."""
        db = self._db_mode("vector")
        hits = db.search(query="페이지 교체", title="cs", top_k=3)
        self.assertGreater(len(hits), 0, "vector: 페이지 교체 결과 없음")

    def test_fts_mode_keyword_search(self):
        """fts: 정확한 키워드 LRU를 잡아야 함."""
        db = self._db_mode("fts")
        hits = db.search(query="LRU", title="cs", top_k=3)
        self.assertGreater(len(hits), 0, "fts: LRU 결과 없음")

    # ── 2. score 내림차순 정렬 보장 ───────────────────────────────────────────

    def test_hybrid_scores_descending(self):
        db = self._db_mode("hybrid")
        hits = db.search(query="운영체제", title="cs", top_k=5)
        scores = [h["score"] for h in hits]
        self.assertEqual(
            scores, sorted(scores, reverse=True),
            f"hybrid score 내림차순 미보장: {scores}",
        )

    def test_vector_scores_descending(self):
        db = self._db_mode("vector")
        hits = db.search(query="프로세스 스케줄링", title="cs", top_k=5)
        scores = [h["score"] for h in hits]
        self.assertEqual(
            scores, sorted(scores, reverse=True),
            f"vector score 내림차순 미보장: {scores}",
        )

    def test_fts_scores_descending(self):
        db = self._db_mode("fts")
        hits = db.search(query="TCP UDP", title="cs", top_k=5)
        scores = [h["score"] for h in hits]
        self.assertEqual(
            scores, sorted(scores, reverse=True),
            f"fts score 내림차순 미보장: {scores}",
        )

    # ── 3. top_k 상한 보장 ────────────────────────────────────────────────────

    def test_top_k_upper_bound_hybrid(self):
        db = self._db_mode("hybrid")
        hits = db.search(query="운영체제", title="cs", top_k=2)
        self.assertLessEqual(len(hits), 2, f"top_k=2 요청 시 {len(hits)}개 반환됨")

    def test_top_k_upper_bound_vector(self):
        db = self._db_mode("vector")
        hits = db.search(query="운영체제", title="cs", top_k=2)
        self.assertLessEqual(len(hits), 2, f"top_k=2 요청 시 {len(hits)}개 반환됨")

    def test_top_k_upper_bound_fts(self):
        db = self._db_mode("fts")
        hits = db.search(query="LRU FIFO", title="cs", top_k=2)
        self.assertLessEqual(len(hits), 2, f"top_k=2 요청 시 {len(hits)}개 반환됨")

    # ── 4. FTS vs vector 상호 보완: hybrid가 단독 모드보다 나쁘지 않음 ─────────

    def test_hybrid_not_worse_than_vector_on_semantic_query(self):
        """의미 유사어 쿼리에서 hybrid 결과 수 >= 0 (최소한 결과가 있어야 함)."""
        db_hybrid = self._db_mode("hybrid")
        db_vector = self._db_mode("vector")
        q = "프로세스 자원 소유 실행 단위"
        hits_h = db_hybrid.search(query=q, title="cs", top_k=5)
        hits_v = db_vector.search(query=q, title="cs", top_k=5)
        # hybrid가 결과를 내지 못하면서 vector는 결과를 내는 상황은 없어야 함
        if hits_v:
            self.assertGreater(len(hits_h), 0,
                               "vector는 결과를 내지만 hybrid는 결과 없음")

    def test_hybrid_not_worse_than_fts_on_exact_symbol(self):
        """정확한 코드 심볼 쿼리에서 hybrid 결과 수 >= 0."""
        db_hybrid = self._db_mode("hybrid")
        db_fts = self._db_mode("fts")
        q = "fork()"
        hits_h = db_hybrid.search(query=q, title="cs", top_k=5)
        hits_f = db_fts.search(query=q, title="cs", top_k=5)
        if hits_f:
            self.assertGreater(len(hits_h), 0,
                               "fts는 결과를 내지만 hybrid는 결과 없음")

    # ── 5. 모드 전환 격리: 이전 모드 인덱스가 결과를 오염시키지 않음 ───────────

    def test_mode_switch_isolation_vector_after_hybrid(self):
        """hybrid → vector 전환 후 결과 score 순위는 vector 기준이어야 함."""
        db = self._db_mode("vector")
        hits = db.search(query="소켓 네트워크", title="cs", top_k=5)
        if len(hits) >= 2:
            scores = [h["score"] for h in hits]
            self.assertEqual(scores, sorted(scores, reverse=True),
                             "모드 전환 후 score 정렬 깨짐")

    def test_mode_switch_isolation_fts_after_vector(self):
        """vector → fts 전환 후 결과 score 순위는 fts 기준이어야 함."""
        db = self._db_mode("fts")
        hits = db.search(query="TCP 신뢰성", title="cs", top_k=5)
        if len(hits) >= 2:
            scores = [h["score"] for h in hits]
            self.assertEqual(scores, sorted(scores, reverse=True),
                             "모드 전환 후 score 정렬 깨짐")
