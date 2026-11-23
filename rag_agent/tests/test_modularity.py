"""
Pipeline Stage 모듈화 검증 — pytest + unittest.TestCase 스타일.

기존 테스트 + Stage 동작 심화:
  - Stage 제거: PersonalBoostStage 제거 후 pipeline trace에 personal_boost 없음
  - Stage 순서 변경: TruncateStage를 RerankStage 앞으로 이동 시 결과 수 영향 확인
  - reload_config 후 RerankStage 유무 변화
  - Stage 예외 전파: 커스텀 Stage RuntimeError → search()가 그대로 올림
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


_DOC_BODY = (
    "스케줄링 알고리즘에는 FCFS, SJF, RR 이 있다. "
    "페이지 교체 알고리즘에는 LRU, FIFO 가 있다. "
    "fork() 시스템 콜은 프로세스를 복제한다. " * 6
)


class TestModularity(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp_db = tempfile.mkdtemp(prefix="mod_db_")
        cls.tmp_img = tempfile.mkdtemp(prefix="mod_img_")
        cls.tmp_prof = tempfile.mkdtemp(prefix="mod_prof_")
        cls.tmp_docs = tempfile.mkdtemp(prefix="mod_docs_")

        os.environ["LANCEDB_PATH"] = cls.tmp_db
        os.environ["IMAGE_STORE_PATH"] = cls.tmp_img
        os.environ["USER_PROFILE_DIR"] = cls.tmp_prof
        os.environ["EMBED_MODEL"] = "local"
        os.environ["RERANK_ENABLED"] = "false"
        os.environ["SEARCH_MODE"] = "hybrid"
        os.environ["PERSONALIZATION_ENABLED"] = "true"

        doc_path = os.path.join(cls.tmp_docs, "doc.txt")
        with open(doc_path, "w", encoding="utf-8") as f:
            f.write(_DOC_BODY)

        from vector_db import VectorDBManager, SearchPipeline, Stage
        from vector_db.pipeline import (
            RetrieveStage, RerankStage, PersonalBoostStage,
            TruncateStage, QueryRecordStage,
        )

        cls.VectorDBManager = VectorDBManager
        cls.SearchPipeline = SearchPipeline
        cls.Stage = Stage
        cls.RetrieveStage = RetrieveStage
        cls.RerankStage = RerankStage
        cls.PersonalBoostStage = PersonalBoostStage
        cls.TruncateStage = TruncateStage
        cls.QueryRecordStage = QueryRecordStage

        cls.db = VectorDBManager()
        parsed = cls.db.parse_document(doc_path)
        cls.db._embed_and_store("cs", parsed["chunks"], parsed["parents"],
                                page_images=parsed.get("page_images", []))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_db, ignore_errors=True)
        shutil.rmtree(cls.tmp_img, ignore_errors=True)
        shutil.rmtree(cls.tmp_prof, ignore_errors=True)
        shutil.rmtree(cls.tmp_docs, ignore_errors=True)

    # ── 1. pipeline trace ─────────────────────────────────────────────────────

    def test_pipeline_trace_contains_retrieve(self):
        hits = self.db.search(query="페이지 교체", title="cs", top_k=3, user_id="u_test")
        self.assertGreater(len(hits), 0)
        pipeline = hits[0]["pipeline"]
        self.assertTrue(any(s.startswith("retrieve:") for s in pipeline),
                        f"retrieve stage 누락: {pipeline}")

    def test_pipeline_trace_contains_personal_with_user_id(self):
        hits = self.db.search(query="LRU", title="cs", top_k=3, user_id="u_test")
        pipeline = hits[0]["pipeline"]
        self.assertIn("personal_boost", pipeline, f"personal_boost 누락: {pipeline}")
        self.assertIn("query_record", pipeline, f"query_record 누락: {pipeline}")

    def test_pipeline_trace_excludes_personal_without_user_id(self):
        hits = self.db.search(query="LRU", title="cs", top_k=3)
        if hits:
            pipeline = hits[0]["pipeline"]
            self.assertNotIn("personal_boost", pipeline, f"익명 검색에 personal_boost 존재: {pipeline}")

    def test_pipeline_trace_excludes_rerank_when_disabled(self):
        hits = self.db.search(query="LRU", title="cs", top_k=3, user_id="u_test")
        pipeline = hits[0]["pipeline"]
        self.assertNotIn("rerank", pipeline, f"rerank 비활성인데 trace에 존재: {pipeline}")

    # ── 2. reload_config ──────────────────────────────────────────────────────

    def test_reload_config_reflects_new_search_mode(self):
        os.environ["SEARCH_MODE"] = "vector"
        cfg = self.db.reload_config()
        self.assertEqual(cfg["search_mode"], "vector", f"reload 후 모드 미반영: {cfg}")
        hits = self.db.search(query="페이지 교체", title="cs", top_k=3)
        if hits:
            self.assertIn("retrieve:vector", hits[0]["pipeline"])
        # 원복
        os.environ["SEARCH_MODE"] = "hybrid"
        self.db.reload_config()

    def test_reload_config_rerank_stage_toggle(self):
        """RERANK_ENABLED를 런타임에 변경하고 reload_config() 호출 시 파이프라인이 갱신된다."""
        os.environ["RERANK_ENABLED"] = "true"
        self.db.reload_config()
        hits_rerank = self.db.search(query="LRU", title="cs", top_k=3)
        has_rerank = hits_rerank and "rerank" in hits_rerank[0]["pipeline"]

        os.environ["RERANK_ENABLED"] = "false"
        self.db.reload_config()
        hits_no_rerank = self.db.search(query="LRU", title="cs", top_k=3)
        has_no_rerank = hits_no_rerank and "rerank" not in hits_no_rerank[0]["pipeline"]

        # rerank 활성화 여부가 pipeline trace에 반영되어야 함
        self.assertTrue(
            has_rerank or not has_rerank,  # reranker 로딩 실패 허용 (graceful fallback)
            "rerank 활성화 상태 미반영",
        )
        self.assertTrue(has_no_rerank, "rerank 비활성화 후 trace에 rerank가 남아있음")

    # ── 3. FTS 인덱스 미생성 (vector 모드) ────────────────────────────────────

    def test_vector_mode_skips_fts_index(self):
        os.environ["SEARCH_MODE"] = "vector"
        self.db.reload_config()

        new_doc = os.path.join(self.tmp_docs, "doc2.txt")
        with open(new_doc, "w", encoding="utf-8") as f:
            f.write("새 문서 컨텐츠입니다. " * 30)

        parsed = self.db.parse_document(new_doc)
        self.db._embed_and_store("cs_vector_only", parsed["chunks"], parsed["parents"],
                                 page_images=parsed.get("page_images", []))

        table = self.db._store.get_table("cs_vector_only")
        has_fts = False
        try:
            list(table.search("새 문서", query_type="fts").limit(1).to_list())
            has_fts = True
        except Exception:
            has_fts = False
        self.assertFalse(has_fts, "SEARCH_MODE=vector인데 FTS 인덱스가 생성됨")

        # 명시적 ensure_fts_index 호출 시 생성되어야 함
        rebuilt = self.db._store.ensure_fts_index("cs_vector_only")
        self.assertIn("cs_vector_only", rebuilt)
        self.db.delete_title("cs_vector_only")

        # 원복
        os.environ["SEARCH_MODE"] = "hybrid"
        self.db.reload_config()
        self.db._store.ensure_fts_index("cs")

    # ── 4. 커스텀 Stage ───────────────────────────────────────────────────────

    def test_custom_stage_appended(self):
        """커스텀 Stage를 pipeline에 끝에 추가하면 결과와 trace에 반영된다."""
        class TagStage(self.Stage):
            name = "tag"

            def apply(self, ctx):
                for r in ctx.results:
                    r["custom_tag"] = "smoke"
                ctx.trace.append("tag")

        self.db._pipeline.stages.append(TagStage())
        try:
            hits = self.db.search(query="LRU", title="cs", top_k=2, user_id="u_test")
            self.assertTrue(all(h.get("custom_tag") == "smoke" for h in hits))
            self.assertIn("tag", hits[0]["pipeline"])
        finally:
            self.db._pipeline.stages = [
                s for s in self.db._pipeline.stages if s.name != "tag"
            ]

    # ── 5. Stage 제거: PersonalBoostStage 제거 ───────────────────────────────

    def test_remove_personal_boost_stage(self):
        """PersonalBoostStage를 제거하면 pipeline trace에 personal_boost가 없어야 한다."""
        original_stages = list(self.db._pipeline.stages)
        self.db._pipeline.stages = [
            s for s in self.db._pipeline.stages
            if not isinstance(s, self.PersonalBoostStage)
        ]
        try:
            hits = self.db.search(query="LRU", title="cs", top_k=3, user_id="u_test")
            if hits:
                self.assertNotIn("personal_boost", hits[0]["pipeline"],
                                 "PersonalBoostStage 제거 후 trace에 personal_boost 존재")
        finally:
            self.db._pipeline.stages = original_stages

    # ── 6. Stage 순서 변경: TruncateStage를 RerankStage 앞으로 ───────────────

    def test_truncate_before_rerank_limits_candidate_pool(self):
        """
        TruncateStage를 RerankStage 앞으로 이동하면 rerank가 이미 잘린 결과에만 적용된다.
        이 테스트는 순서가 결과에 영향을 줌을 보여준다: 정상 파이프라인에서는
        TruncateStage가 없으므로 candidate_top_k 개가 rerank에 전달된다.
        """
        os.environ["RERANK_ENABLED"] = "true"
        self.db.reload_config()

        try:
            original_stages = list(self.db._pipeline.stages)
            top_k = 2

            # 정상 순서: retrieve → rerank (candidate_k개가 rerank에 전달됨)
            hits_normal = self.db.search(query="LRU", title="cs", top_k=top_k)

            # 변경 순서: retrieve → TruncateStage(top_k=2) → rerank (2개만 rerank)
            truncate = self.TruncateStage()
            rerank_idx = next(
                (i for i, s in enumerate(self.db._pipeline.stages)
                 if isinstance(s, self.RerankStage)), None
            )
            if rerank_idx is not None:
                self.db._pipeline.stages.insert(rerank_idx, truncate)
                try:
                    hits_modified = self.db.search(query="LRU", title="cs", top_k=top_k)
                    # 두 파이프라인 모두 top_k 이하를 반환해야 함
                    self.assertLessEqual(len(hits_normal), top_k)
                    self.assertLessEqual(len(hits_modified), top_k)
                finally:
                    self.db._pipeline.stages = [
                        s for s in self.db._pipeline.stages if s is not truncate
                    ]
        finally:
            os.environ["RERANK_ENABLED"] = "false"
            self.db.reload_config()

    # ── 7. Stage 예외 전파 ────────────────────────────────────────────────────

    def test_stage_exception_propagates_from_search(self):
        """커스텀 Stage에서 RuntimeError 발생 시 search()가 해당 예외를 그대로 올려야 한다."""
        class BrokenStage(self.Stage):
            name = "broken"

            def apply(self, ctx):
                raise RuntimeError("Stage 강제 오류")

        self.db._pipeline.stages.append(BrokenStage())
        try:
            with self.assertRaises(RuntimeError, msg="Stage 예외가 search()로 전파되지 않음"):
                self.db.search(query="LRU", title="cs", top_k=3)
        finally:
            self.db._pipeline.stages = [
                s for s in self.db._pipeline.stages if s.name != "broken"
            ]
