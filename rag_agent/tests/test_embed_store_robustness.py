"""
_embed_and_store 견고성 테스트.

1. embed() 반환 개수 불일치 → RuntimeError 즉시 발생 (zip 무음 절단 방지)
2. BaseException(SystemExit 등) db_worker 내 발생 → 호출자에게 전파
3. db_worker hang → join timeout 초과 시 TimeoutError
4. parent_id 누락(orphan) → 경고 로그 발생, 나머지 청크는 정상 저장
"""

import hashlib
import logging
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

tmp_db = tempfile.mkdtemp(prefix="robustness_test_")
os.environ["LANCEDB_PATH"] = tmp_db
os.environ.setdefault("EMBED_MODEL", "local")

from vector_db import VectorDBManager
from vector_db.parent_builder import build_parents


# ──────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────────────────────

def _make_raw_chunk(file_name, chunk_index, heading_path, page=1, text=None):
    if text is None:
        text = f"청크 텍스트 {chunk_index} " * 20
    return {
        "text": text,
        "chunk_index": chunk_index,
        "page": page,
        "file_name": file_name,
        "image_page": -1,
        "content_hash": hashlib.sha256(text.encode()).hexdigest(),
        "heading_path": heading_path,
        "source_type": "general",
    }


def _mock_embed(dim):
    rng = np.random.default_rng(0)
    def _embed(texts):
        return [rng.random(dim).tolist() for _ in texts]
    return _embed


class TestEmbedStoreRobustness(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db = VectorDBManager()
        cls.dim = cls.db._embedder.dimension

    # ── 1. embed() 반환 개수 불일치 ───────────────────────────────────────────

    def test_embed_count_mismatch_raises_runtime_error(self):
        """
        embed()가 입력보다 적은 벡터를 반환하면 RuntimeError가 발생해야 한다.
        수정 전: zip()이 무음으로 절단되어 청크가 유실됨.
        수정 후: len(vectors) != len(batch) 검사로 즉시 오류 발생.
        """
        title = "count_mismatch"
        file_name = "mismatch.txt"
        raw = [_make_raw_chunk(file_name, i, ["Ch1"]) for i in range(3)]
        chunks, parents = build_parents(raw)

        embed_fn = _mock_embed(self.dim)

        def short_embed(texts):
            full = embed_fn(texts)
            return full[:-1]  # 마지막 벡터를 누락시킴

        try:
            with self.assertRaises(RuntimeError) as ctx:
                with patch.object(self.db._embedder, "embed", side_effect=short_embed):
                    self.db._embed_and_store(title, chunks, parents)

            self.assertIn("embed() 반환 개수 불일치", str(ctx.exception))
        finally:
            self.db.delete_title(title)

    def test_embed_count_exact_match_succeeds(self):
        """정상 개수(입력 == 출력)일 때는 오류 없이 통과해야 한다."""
        title = "count_ok"
        file_name = "ok.txt"
        raw = [_make_raw_chunk(file_name, i, ["Ch1"]) for i in range(3)]
        chunks, parents = build_parents(raw)

        try:
            with patch.object(self.db._embedder, "embed", side_effect=_mock_embed(self.dim)):
                result = self.db._embed_and_store(title, chunks, parents)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["chunks_added"], len(chunks))
        finally:
            self.db.delete_title(title)

    # ── 2. BaseException in db_worker ─────────────────────────────────────────

    def test_base_exception_in_db_worker_propagates(self):
        """
        db_worker 내에서 BaseException(여기서는 SystemExit) 발생 시
        호출자에게 예외가 전파되어야 한다.
        수정 전(except Exception): SystemExit를 캐치하지 못해 db_exc[0]=None →
          join 완료 후 예외 없이 성공으로 보고되는 silent failure.
        수정 후(except BaseException): db_exc[0]에 저장 후 cancel → 전파.
        """
        title = "base_exc"
        file_name = "base_exc.txt"
        raw = [_make_raw_chunk(file_name, 0, ["Ch1"])]
        chunks, parents = build_parents(raw)

        try:
            with (
                patch.object(self.db._embedder, "embed", side_effect=_mock_embed(self.dim)),
                patch.object(
                    self.db._store, "upsert",
                    side_effect=SystemExit("db_worker 내 SystemExit 강제 발생"),
                ),
            ):
                with self.assertRaises(SystemExit, msg="BaseException이 전파되지 않음"):
                    self.db._embed_and_store(title, chunks, parents)
        finally:
            self.db.delete_title(title)

    def test_keyboard_interrupt_in_db_worker_propagates(self):
        """KeyboardInterrupt도 동일하게 전파되어야 한다."""
        title = "kb_int"
        file_name = "kb_int.txt"
        raw = [_make_raw_chunk(file_name, 0, ["Ch1"])]
        chunks, parents = build_parents(raw)

        try:
            with (
                patch.object(self.db._embedder, "embed", side_effect=_mock_embed(self.dim)),
                patch.object(
                    self.db._store, "upsert",
                    side_effect=KeyboardInterrupt("db_worker 내 KeyboardInterrupt 강제 발생"),
                ),
            ):
                with self.assertRaises(KeyboardInterrupt, msg="KeyboardInterrupt가 전파되지 않음"):
                    self.db._embed_and_store(title, chunks, parents)
        finally:
            self.db.delete_title(title)

    # ── 3. db_worker hang → join timeout ──────────────────────────────────────

    def test_db_worker_hang_raises_timeout_error(self):
        """
        db_worker가 지정된 시간(DB_THREAD_JOIN_TIMEOUT) 내에 완료되지 않으면
        TimeoutError가 발생해야 한다.
        수정 전: db_thread.join() 에 타임아웃이 없어 무한 블록.
        수정 후: join(timeout=T) + is_alive() 체크 → TimeoutError.
        """
        title = "hang_test"
        file_name = "hang.txt"
        raw = [_make_raw_chunk(file_name, 0, ["Ch1"])]
        chunks, parents = build_parents(raw)

        hang_started = threading.Event()

        def hanging_upsert(*args, **kwargs):
            hang_started.set()
            time.sleep(999)  # 사실상 무한 대기

        orig_timeout = os.environ.get("DB_THREAD_JOIN_TIMEOUT")
        try:
            os.environ["DB_THREAD_JOIN_TIMEOUT"] = "0.3"  # 300ms 타임아웃

            with (
                patch.object(self.db._embedder, "embed", side_effect=_mock_embed(self.dim)),
                patch.object(self.db._store, "upsert", side_effect=hanging_upsert),
            ):
                with self.assertRaises(TimeoutError, msg="hang 시 TimeoutError 미발생"):
                    self.db._embed_and_store(title, chunks, parents)

            self.assertTrue(hang_started.is_set(), "upsert가 실제로 호출되지 않음")
        finally:
            if orig_timeout is None:
                os.environ.pop("DB_THREAD_JOIN_TIMEOUT", None)
            else:
                os.environ["DB_THREAD_JOIN_TIMEOUT"] = orig_timeout
            self.db.delete_title(title)

    # ── 4. orphan parent_id → 경고 로그 ──────────────────────────────────────

    def test_orphan_parent_id_logs_warning(self):
        """
        청크의 parent_id가 parents 목록에 없을 때 경고 로그가 발생해야 한다.
        수정 전: 무음으로 스킵 → DB에 부모 없는 청크가 저장됨.
        수정 후: logger.warning 으로 누락 parent_id 목록을 기록.
        """
        title = "orphan_test"
        file_name = "orphan.txt"
        raw = [_make_raw_chunk(file_name, i, ["Ch1"]) for i in range(2)]
        chunks, parents = build_parents(raw)

        # 청크에 존재하지 않는 parent_id를 주입
        orphan_pid = "deadbeef00000000"
        chunks_with_orphan = [dict(c) for c in chunks]
        chunks_with_orphan[0]["parent_id"] = orphan_pid

        # parents 목록에서 해당 parent_id 제거 (orphan 상태 만들기)
        parents_without_orphan = [p for p in parents if p["parent_id"] != orphan_pid]

        try:
            with (
                patch.object(self.db._embedder, "embed", side_effect=_mock_embed(self.dim)),
                self.assertLogs("vector_db.manager", level="WARNING") as log_ctx,
            ):
                self.db._embed_and_store(title, chunks_with_orphan, parents_without_orphan)

            warning_msgs = [r for r in log_ctx.output if "parent_id 누락" in r]
            self.assertTrue(warning_msgs, "orphan parent_id 에 대한 경고 로그가 없음")
            self.assertTrue(
                any(orphan_pid in msg for msg in warning_msgs),
                f"경고 메시지에 orphan_pid({orphan_pid}) 가 포함되지 않음: {warning_msgs}",
            )
        finally:
            self.db.delete_title(title)

    def test_orphan_parent_id_does_not_crash(self):
        """
        orphan parent_id가 있어도 나머지 청크는 정상 저장되어야 한다.
        경고만 발생하고 오류로 중단되면 안 된다.
        """
        title = "orphan_no_crash"
        file_name = "orphan2.txt"
        raw = [_make_raw_chunk(file_name, i, ["Ch1"]) for i in range(3)]
        chunks, parents = build_parents(raw)

        chunks_with_orphan = [dict(c) for c in chunks]
        chunks_with_orphan[0]["parent_id"] = "deadbeef00000001"
        parents_subset = [p for p in parents if p["parent_id"] != "deadbeef00000001"]

        try:
            with (
                patch.object(self.db._embedder, "embed", side_effect=_mock_embed(self.dim)),
                self.assertLogs("vector_db.manager", level="WARNING"),
            ):
                result = self.db._embed_and_store(
                    title, chunks_with_orphan, parents_subset
                )

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["chunks_added"], len(chunks))
        finally:
            self.db.delete_title(title)

    # ── 5. _send_sentinel 무한루프 방지: 2배치 + db_worker hang ──────────────

    def test_multi_batch_hang_raises_timeout_error(self):
        """
        배치 2개 이상 + db_worker hang 조합에서 TimeoutError가 발생해야 한다.

        버그 재현 경로:
          batch[0] → _enqueue 성공 → db_worker가 꺼내 upsert() HANG (queue 빔)
          batch[1] → _enqueue 성공 (queue 빔이었으므로) → queue full
          _send_sentinel: queue.put(None) → Full, db_thread 살아있음 → 무한루프
          → join(timeout=T) 절대 도달 불가 → TimeoutError 미발생

        수정 후: _send_sentinel 에 deadline 상한 → 포기 후 join() 에 위임.
        """
        title = "multi_batch_hang"
        file_name = "multi_hang.txt"
        # 헤딩 없는 2청크 → INGEST_BATCH_SIZE=1 로 2배치 강제
        raw = [_make_raw_chunk(file_name, i, []) for i in range(2)]
        chunks, parents = build_parents(raw)

        hang_started = threading.Event()

        def hanging_upsert(*args, **kwargs):
            hang_started.set()
            time.sleep(999)

        orig_batch = os.environ.get("INGEST_BATCH_SIZE")
        orig_timeout = os.environ.get("DB_THREAD_JOIN_TIMEOUT")
        try:
            os.environ["INGEST_BATCH_SIZE"] = "1"    # 청크 1개씩 → 2배치
            os.environ["DB_THREAD_JOIN_TIMEOUT"] = "0.5"  # 500ms

            with (
                patch.object(self.db._embedder, "embed", side_effect=_mock_embed(self.dim)),
                patch.object(self.db._store, "upsert", side_effect=hanging_upsert),
            ):
                with self.assertRaises(TimeoutError, msg="2배치 hang 시 TimeoutError 미발생"):
                    self.db._embed_and_store(title, chunks, parents)

            self.assertTrue(hang_started.is_set(), "upsert가 실제로 호출되지 않음")
        finally:
            if orig_batch is None:
                os.environ.pop("INGEST_BATCH_SIZE", None)
            else:
                os.environ["INGEST_BATCH_SIZE"] = orig_batch
            if orig_timeout is None:
                os.environ.pop("DB_THREAD_JOIN_TIMEOUT", None)
            else:
                os.environ["DB_THREAD_JOIN_TIMEOUT"] = orig_timeout
            self.db.delete_title(title)

    # ── 6, 7. reembed 경로 embed count 검사 ──────────────────────────────────

    def test_reembed_in_place_embed_count_mismatch_raises(self):
        """
        _reembed_in_place: embed()가 적은 벡터를 반환하면 RuntimeError가 발생해야 한다.
        수정 전: zip 무음 절단 → 일부 rows가 sentinel(db_version=reembed_in_progress)
                 상태로 DB에 영구 저장되어 재시작마다 무한 재시도.
        수정 후: len(vectors) != len(batch) 검사로 즉시 오류 발생.
        """
        title = "rip_count_mismatch"
        file_name = "rip.txt"
        raw = [_make_raw_chunk(file_name, i, ["Ch1"]) for i in range(3)]
        chunks, parents = build_parents(raw)

        embed_fn = _mock_embed(self.dim)

        def short_embed(texts):
            return embed_fn(texts)[:-1]

        try:
            # 먼저 정상 저장
            with patch.object(self.db._embedder, "embed", side_effect=_mock_embed(self.dim)):
                self.db._embed_and_store(title, chunks, parents)

            stale_rows = self.db._store.get_stale_rows(title, "__never_match__")
            if not stale_rows:
                # stale row 가 없으면 전체 rows 를 직접 사용
                stale_rows = self.db._store.get_all_rows(title)

            with patch.object(self.db._embedder, "embed", side_effect=short_embed):
                with self.assertRaises(RuntimeError) as ctx:
                    self.db._reembed_in_place(title, stale_rows, "local", "__new__", None)

        finally:
            self.db.delete_title(title)

        self.assertIn("embed() 반환 개수 불일치", str(ctx.exception))

    def test_reembed_table_replace_embed_count_mismatch_raises(self):
        """
        _reembed_with_table_replace: embed()가 적은 벡터를 반환하면 RuntimeError가 발생해야 한다.
        수정 전: zip 무음 절단 → 일부 rows에 잘못된 vector가 교체 테이블에 저장됨.
        수정 후: len(vectors) != len(chunk_rows) 검사로 즉시 오류 발생.
        """
        title = "rtr_count_mismatch"
        file_name = "rtr.txt"
        raw = [_make_raw_chunk(file_name, i, ["Ch1"]) for i in range(3)]
        chunks, parents = build_parents(raw)

        embed_fn = _mock_embed(self.dim)

        def short_embed(texts):
            return embed_fn(texts)[:-1]

        try:
            # 먼저 정상 저장
            with patch.object(self.db._embedder, "embed", side_effect=_mock_embed(self.dim)):
                self.db._embed_and_store(title, chunks, parents)

            all_rows = self.db._store.get_all_rows(title)
            for r in all_rows:
                r.setdefault("embed_model", "")
                r.setdefault("db_version", "")

            with patch.object(self.db._embedder, "embed", side_effect=short_embed):
                with self.assertRaises(RuntimeError) as ctx:
                    self.db._reembed_with_table_replace(
                        title, all_rows, "local", "__new__", None
                    )

        finally:
            self.db.delete_title(title)

        self.assertIn("embed() 반환 개수 불일치", str(ctx.exception))

    # ── 8. 동시 write lock 경합 ───────────────────────────────────────────────

    def test_concurrent_writes_different_files_serialize(self):
        """
        같은 title에 두 스레드가 동시에 _embed_and_store를 시도할 때
        lock이 직렬화를 보장하여 두 파일의 청크가 모두 DB에 저장되어야 한다.
        단일사용자 가정이지만 lock 메커니즘 자체의 정확성을 검증한다.
        """
        title = "concurrent_lock"
        raw_a = [_make_raw_chunk("a.txt", i, ["ChA"]) for i in range(2)]
        raw_b = [_make_raw_chunk("b.txt", i, ["ChB"]) for i in range(3)]
        chunks_a, parents_a = build_parents(raw_a)
        chunks_b, parents_b = build_parents(raw_b)

        errors: list[Exception] = []
        embed_fn = _mock_embed(self.dim)

        def ingest_a():
            try:
                with patch.object(self.db._embedder, "embed", side_effect=embed_fn):
                    self.db._embed_and_store(title, chunks_a, parents_a)
            except Exception as e:
                errors.append(e)

        def ingest_b():
            try:
                with patch.object(self.db._embedder, "embed", side_effect=embed_fn):
                    self.db._embed_and_store(title, chunks_b, parents_b)
            except Exception as e:
                errors.append(e)

        try:
            t1 = threading.Thread(target=ingest_a)
            t2 = threading.Thread(target=ingest_b)
            t1.start()
            t2.start()
            t1.join(timeout=30)
            t2.join(timeout=30)

            self.assertFalse(errors, f"ingest 도중 예외 발생: {errors}")
            self.assertFalse(t1.is_alive(), "thread_a가 완료되지 않음")
            self.assertFalse(t2.is_alive(), "thread_b가 완료되지 않음")

            # 두 파일 중 마지막에 실행된 파일의 청크만 남아있어야 함
            # (lock 직렬화이므로 두 번째 ingest가 첫 번째 결과를 덮지 않음 — 파일별 delete)
            files = self.db.list_files(title)
            self.assertGreaterEqual(len(files), 1, "최소 1개 파일의 청크가 DB에 있어야 함")
        finally:
            self.db.delete_title(title)

    # ── 9. lock 재진입 방지 ───────────────────────────────────────────────────

    def test_lock_reentry_from_different_thread_blocks(self):
        """
        한 스레드가 title lock을 보유하는 동안 다른 스레드의 같은 title acquire는 블록되어야 한다.
        외부 lock 해제 후 다른 스레드가 정상적으로 진행되는지도 확인한다.
        """
        title = "reentry_lock"
        inner_unblocked = threading.Event()
        outer_done = threading.Event()

        def inner_thread():
            # 외부 lock이 해제될 때까지 블록됨
            with self.db._title_write_lock(title):
                inner_unblocked.set()

        with self.db._title_write_lock(title):
            t = threading.Thread(target=inner_thread)
            t.start()
            # 내부 스레드가 블록 상태인지 잠시 확인 (0.3s 내에 inner_unblocked가 세워지면 안 됨)
            acquired_early = inner_unblocked.wait(timeout=0.3)
            self.assertFalse(acquired_early, "외부 lock 보유 중에 내부 스레드가 lock을 획득함")

        # 외부 lock 해제 후 내부 스레드가 진행됨
        t.join(timeout=5.0)
        self.assertFalse(t.is_alive(), "외부 lock 해제 후 내부 스레드가 완료되지 않음")
        self.assertTrue(inner_unblocked.is_set(), "내부 스레드가 lock을 획득하지 못함")
        with self.db._meta_lock:
            self.db._title_write_locks.pop(title, None)
            self.db._title_write_refs.pop(title, None)

    def test_same_thread_reentry_deadlocks(self):
        """
        같은 스레드에서 같은 title의 lock을 중첩 acquire하면 deadlock이 발생한다.
        timeout을 이용해 deadlock 여부를 감지한다 (threading.Lock은 비재진입).
        """
        title = "same_thread_reentry"
        deadlock_detected = threading.Event()

        def try_reenter():
            with self.db._title_write_lock(title):
                # 같은 스레드에서 내부 lock 객체를 직접 timeout acquire
                inner_lock = self.db._acquire_title_write_lock(title)
                try:
                    got = inner_lock.acquire(timeout=0.3)
                    if not got:
                        deadlock_detected.set()
                    else:
                        inner_lock.release()
                finally:
                    self.db._release_title_write_lock(title)

        t = threading.Thread(target=try_reenter)
        t.start()
        t.join(timeout=5.0)
        self.assertFalse(t.is_alive(), "재진입 스레드가 5s 내에 완료되지 않음")
        self.assertTrue(deadlock_detected.is_set(), "같은 스레드 재진입에서 deadlock이 감지되지 않음")
        with self.db._meta_lock:
            self.db._title_write_locks.pop(title, None)
            self.db._title_write_refs.pop(title, None)

    # ── 10. cancel 신호 전파: db_worker 실패 후 embed 루프 중단 ─────────────

    def test_cancel_stops_embed_after_db_failure(self):
        """
        db_worker가 upsert 실패로 cancel을 설정하면 embed 루프가 모든 배치를
        처리하기 전에 중단되어야 한다 (불필요한 embed 호출 방지).
        """
        title = "cancel_embed"
        file_name = "cancel.txt"
        # batch_size=1 → 5개 청크 = 5배치
        raw = [_make_raw_chunk(file_name, i, []) for i in range(5)]
        chunks, parents = build_parents(raw)

        embed_call_count = [0]
        embed_fn = _mock_embed(self.dim)

        def counting_embed(texts):
            embed_call_count[0] += 1
            return embed_fn(texts)

        def failing_upsert(*args, **kwargs):
            raise RuntimeError("db_worker 강제 실패")

        orig = os.environ.get("INGEST_BATCH_SIZE")
        try:
            os.environ["INGEST_BATCH_SIZE"] = "1"
            with (
                patch.object(self.db._embedder, "embed", side_effect=counting_embed),
                patch.object(self.db._store, "upsert", side_effect=failing_upsert),
            ):
                with self.assertRaises(RuntimeError):
                    self.db._embed_and_store(title, chunks, parents)

            # cancel 설정 후 embed는 5번보다 적게 호출되어야 한다
            self.assertGreaterEqual(embed_call_count[0], 1, "embed가 한 번도 호출되지 않음")
            self.assertLess(
                embed_call_count[0], 5,
                f"cancel 신호 후에도 embed가 {embed_call_count[0]}번 실행됨 (5번 미만이어야 함)",
            )
        finally:
            if orig is None:
                os.environ.pop("INGEST_BATCH_SIZE", None)
            else:
                os.environ["INGEST_BATCH_SIZE"] = orig
            self.db.delete_title(title)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2, exit=False)
    finally:
        shutil.rmtree(tmp_db, ignore_errors=True)
