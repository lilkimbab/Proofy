"""
_embed_and_store 파이프라인 테스트.
정상 동작 / DB 오류 전파 / embed 오류 전파 / 타이밍(병렬성) 검증.
"""

import sys, os, tempfile, shutil, threading, time, unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

tmp_db = tempfile.mkdtemp(prefix="pipeline_test_")
os.environ["LANCEDB_PATH"] = tmp_db
os.environ.setdefault("EMBED_MODEL", "local")

from vector_db import VectorDBManager


def _make_txt(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


def _ingest(db: VectorDBManager, file_path: str, title: str) -> dict:
    """parse → embed_and_store 전체 흐름을 실행하는 테스트용 헬퍼."""
    parsed = db.parse_document(file_path)
    return db._embed_and_store(title, parsed["chunks"], parsed["parents"])


class TestEmbedPipeline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db = VectorDBManager()

    # ------------------------------------------------------------------ #
    # 1. 정상 동작
    # ------------------------------------------------------------------ #
    def test_normal_operation(self):
        """add_document 후 검색이 정상 동작해야 한다."""
        path = _make_txt("파이프라인은 병렬성을 높인다. " * 40)
        try:
            result = _ingest(self.db, path, title="pipeline_test")
            self.assertEqual(result["status"], "ok")
            self.assertGreater(result["chunks_added"], 0)

            hits = self.db.search(query="파이프라인 병렬", title="pipeline_test", top_k=3)
            self.assertGreater(len(hits), 0)
            self.assertIn("parent_text", hits[0])
        finally:
            os.unlink(path)
            self.db.delete_title("pipeline_test")

    # ------------------------------------------------------------------ #
    # 2. embed 오류 전파
    # ------------------------------------------------------------------ #
    def test_embed_error_propagates(self):
        """embed()에서 예외 발생 시 호출자에게 전파되고 DB 스레드가 정상 종료되어야 한다."""
        path = _make_txt("embed 오류 테스트 내용. " * 30)
        try:
            with patch.object(
                self.db._embedder, "embed", side_effect=ValueError("embed 강제 실패")
            ):
                with self.assertRaises(ValueError, msg="embed 오류가 전파되지 않음"):
                    _ingest(self.db, path, title="err_embed_test")

            # 오류 후 DB 스레드가 정상 종료됐는지: 새 작업이 정상 동작하면 OK
            path2 = _make_txt("정상 복구 확인용 내용. " * 30)
            try:
                result = _ingest(self.db, path2, title="err_embed_test")
                self.assertEqual(result["status"], "ok")
            finally:
                os.unlink(path2)
        finally:
            os.unlink(path)
            self.db.delete_title("err_embed_test")

    # ------------------------------------------------------------------ #
    # 4. 병렬성 확인 (delete와 embed가 겹치는지)
    # ------------------------------------------------------------------ #
    def test_delete_and_embed_overlap(self):
        """delete가 실행되는 동안 embed도 실행되어야 한다 (타임라인 겹침 확인)."""
        path = _make_txt("병렬 실행 타이밍 확인용 내용. " * 40)
        timeline: list[tuple[str, float]] = []

        original_delete = self.db._store.delete_by_file
        original_embed = self.db._embedder.embed

        def slow_delete(title, file_name):
            timeline.append(("delete_start", time.monotonic()))
            time.sleep(0.3)  # delete를 의도적으로 느리게
            timeline.append(("delete_end", time.monotonic()))
            return original_delete(title, file_name)

        def tracked_embed(texts):
            timeline.append(("embed_start", time.monotonic()))
            result = original_embed(texts)
            timeline.append(("embed_end", time.monotonic()))
            return result

        try:
            with (
                patch.object(self.db._store, "delete_by_file", side_effect=slow_delete),
                patch.object(self.db._embedder, "embed", side_effect=tracked_embed),
            ):
                _ingest(self.db, path, title="timing_test")

            events = {name: t for name, t in timeline}
            # embed_start이 delete_end 이전이면 병렬로 실행된 것
            self.assertLess(
                events["embed_start"],
                events["delete_end"],
                "embed가 delete 완료 후에 시작됨 — 병렬 실행이 아님",
            )
            overlap = events["delete_end"] - events["embed_start"]
            print(f"\n  타임라인 겹침: {overlap*1000:.1f}ms (delete와 embed 병렬 실행 확인)")
        finally:
            os.unlink(path)
            self.db.delete_title("timing_test")


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2, exit=False)
    finally:
        shutil.rmtree(tmp_db, ignore_errors=True)
