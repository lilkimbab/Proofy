"""
_embed_and_store 배치-parent 정합성 테스트.

1. 한 배치에 parent가 2개일 때 중복 없이 저장되는지
2. 각 배치가 자신의 parent만 upsert하는지 (cross-contamination 없음)
3. 예상치 못한 실패(embed/upsert/upsert_parents)에 올바르게 대응하는지
"""

import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

tmp_db = tempfile.mkdtemp(prefix="parent_batch_test_")
os.environ["LANCEDB_PATH"] = tmp_db
os.environ.setdefault("EMBED_MODEL", "local")
os.environ["INGEST_BATCH_SIZE"] = "32"

from vector_db import VectorDBManager
from vector_db.parent_builder import build_parents


# ──────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────────────────────

def _make_raw_chunk(
    file_name: str,
    chunk_index: int,
    heading_path: list[str],
    page: int = 1,
    text: str | None = None,
) -> dict:
    if text is None:
        # MIN_PARENT_CHARS(300) 이상이어야 build_parents 에서 별도 parent로 분리됨
        text = f"테스트 내용 청크{chunk_index} 헤딩{'_'.join(heading_path)} " * 20
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


def _mock_embed(dim: int):
    """일정한 차원의 랜덤 벡터를 반환하는 embed 패처."""
    rng = np.random.default_rng(42)

    def _embed(texts):
        return [rng.random(dim).tolist() for _ in texts]

    return _embed


def _count_parent_rows(db: VectorDBManager, title: str) -> int:
    table_name = db._store._parent_table_name(title)
    if table_name not in db._store._db.list_tables().tables:
        return 0
    return db._store._db.open_table(table_name).count_rows()


# ──────────────────────────────────────────────────────────────────────────────
# 테스트 클래스
# ──────────────────────────────────────────────────────────────────────────────

class TestParentBatch(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db = VectorDBManager()
        cls.dim = cls.db._embedder.dimension

    # ── 1a. 한 배치에 parent 2개 → 중복 없이 저장 ─────────────────────────────

    def test_no_duplicate_parents_within_single_batch(self):
        """
        동일 heading_path[0] → 한 배치, 다른 sub-heading → 두 parent.
        DB에 각 parent_id가 정확히 1번만 존재해야 한다.
        """
        title = "dup_test"
        file_name = "dup.txt"

        # 두 청크: heading_path[0] 같음(한 배치), sub-heading 달라 parent 2개
        raw = [
            _make_raw_chunk(file_name, 0, ["Chapter 1", "Section 1"]),
            _make_raw_chunk(file_name, 1, ["Chapter 1", "Section 2"]),
        ]
        chunks, parents = build_parents(raw)

        # 전제 검증
        batch_keys = {
            (c.get("heading_path") or ["__no_heading__"])[0] for c in chunks
        }
        self.assertEqual(len(batch_keys), 1, "전제 실패: 청크가 한 배치여야 함")
        self.assertEqual(len(parents), 2, "전제 실패: parent가 2개여야 함")

        try:
            with patch.object(self.db._embedder, "embed", side_effect=_mock_embed(self.dim)):
                self.db._embed_and_store(title, chunks, parents)

            # 각 parent_id 가 DB 에 존재하는지
            parent_ids = [p["parent_id"] for p in parents]
            parent_map = self.db._store.get_parents_by_ids(title, parent_ids)
            self.assertEqual(
                len(parent_map), 2,
                f"조회된 parent 수 {len(parent_map)} (기대 2): {list(parent_map.keys())}",
            )

            # DB 총 행 수 = 2 (중복 없음)
            total = _count_parent_rows(self.db, title)
            self.assertEqual(total, 2, f"DB parent 행 수 {total} (기대 2) — 중복 의심")
        finally:
            self.db.delete_title(title)

    # ── 1b. 한 배치에 parent 2개 + 다음 배치 → 이전 배치 parent 보존 & 중복 없음 ──

    def test_no_duplicate_parents_multi_batch_with_two_parents_in_first(self):
        """
        배치 1(Ch1)에 parent P1·P2, 배치 2(Ch2)에 parent P3인 경우:
        - 배치 2의 upsert_parents 호출이 P1·P2를 삭제하지 않아야 한다.
        - 최종 DB parent 수 = 3 (중복 없음).
        - 배치 간 upsert 호출의 parent_id 집합이 서로 겹치지 않아야 한다.

        이 테스트가 노리는 버그:
          upsert_parents 가 append=False 이면 매 배치마다 file_name 전체를 DELETE →
          배치 2 실행 후 P1·P2 가 사라지고 P3 만 남는다.
        """
        title = "multi_batch_dup"
        file_name = "multi.txt"

        # 배치 1(Ch1): sub-heading 분기 → P1, P2
        # 배치 2(Ch2): P3
        raw = [
            _make_raw_chunk(file_name, 0, ["Chapter 1", "Section 1"]),
            _make_raw_chunk(file_name, 1, ["Chapter 1", "Section 2"]),
            _make_raw_chunk(file_name, 2, ["Chapter 2"]),
        ]
        chunks, parents = build_parents(raw)

        # 전제: 배치가 2개, 첫 배치에 parent 2개
        batch1_chunks = [c for c in chunks if (c.get("heading_path") or [""])[0] == "Chapter 1"]
        batch2_chunks = [c for c in chunks if (c.get("heading_path") or [""])[0] == "Chapter 2"]
        batch1_pids = {c["parent_id"] for c in batch1_chunks}
        batch2_pids = {c["parent_id"] for c in batch2_chunks}

        self.assertEqual(len(batch1_pids), 2, "전제 실패: 배치1에 parent 2개여야 함")
        self.assertEqual(len(batch2_pids), 1, "전제 실패: 배치2에 parent 1개여야 함")
        self.assertFalse(batch1_pids & batch2_pids, "전제 실패: 두 배치의 parent_id가 겹침")

        upsert_calls: list[set[str]] = []
        orig = self.db._store.upsert_parents

        def tracking_upsert(t, bp, fn, append=False):
            upsert_calls.append({p["parent_id"] for p in bp})
            return orig(t, bp, fn, append=append)

        try:
            with (
                patch.object(self.db._embedder, "embed", side_effect=_mock_embed(self.dim)),
                patch.object(self.db._store, "upsert_parents", side_effect=tracking_upsert),
            ):
                self.db._embed_and_store(title, chunks, parents)

            # ① 배치 간 upsert 호출의 parent_id 집합이 겹치지 않아야 함
            self.assertEqual(len(upsert_calls), 2, f"upsert 호출 횟수 {len(upsert_calls)} (기대 2)")
            self.assertFalse(
                upsert_calls[0] & upsert_calls[1],
                f"배치1 upsert {upsert_calls[0]} 와 배치2 upsert {upsert_calls[1]} 에 겹치는 parent_id 존재",
            )

            # ② 배치 1의 parent 집합이 첫 번째 upsert에 정확히 포함되는지
            self.assertEqual(
                upsert_calls[0], batch1_pids,
                f"배치1 upsert에 잘못된 parent 포함: {upsert_calls[0]} (기대 {batch1_pids})",
            )

            # ③ 최종 DB parent 수 = 3 (중복 없음, 이전 배치 parent 보존)
            total = _count_parent_rows(self.db, title)
            self.assertEqual(total, 3, f"DB parent 행 수 {total} (기대 3) — 중복 또는 누락 의심")

            # ④ 세 parent 모두 조회 가능해야 함
            all_pids = list(batch1_pids | batch2_pids)
            parent_map = self.db._store.get_parents_by_ids(title, all_pids)
            self.assertEqual(
                set(parent_map.keys()), batch1_pids | batch2_pids,
                f"일부 parent 가 DB 에 없음: {batch1_pids | batch2_pids - set(parent_map.keys())}",
            )
        finally:
            self.db.delete_title(title)

    # ── 1c. no-heading 문서에서 cross-batch parent 공유 → DB 중복 없음 ──────────

    def test_no_duplicate_parents_when_parent_spans_two_fixed_size_batches(self):
        """
        헤딩이 없는 문서는 INGEST_BATCH_SIZE 고정 크기로 배치가 나뉜다.
        이때 build_parents 의 크기 기반 경계(MAX_PARENT_CHARS)와 배치 경계가
        어긋나면 한 parent 가 두 배치에 걸쳐 참조된다.

        재현 시나리오 (BATCH_SIZE=2, MAX_PARENT_CHARS=200):
          build_parents:     [chunk0]=P1  |  [chunk1, chunk2]=P2
          _group_by_heading: [chunk0, chunk1]  |  [chunk2]

          → 배치1 seen: {P1, P2}
          → 배치2 seen: {P2}  ← P2 가 두 배치에 걸침

        기대 동작: P2 는 최초 발견된 배치1에서만 upsert, DB parent 총 수 = 2.
        수정 전 버그: P2 가 두 번 upsert → DB parent 총 수 = 3.
        """
        title = "cross_batch_parent"
        file_name = "cross.txt"

        orig_batch_size = os.environ.get("INGEST_BATCH_SIZE")
        orig_max_chars  = os.environ.get("MAX_PARENT_CHARS")
        orig_min_chars  = os.environ.get("MIN_PARENT_CHARS")
        try:
            os.environ["INGEST_BATCH_SIZE"] = "2"
            os.environ["MAX_PARENT_CHARS"]  = "200"
            os.environ["MIN_PARENT_CHARS"]  = "0"

            # chunk0: 210자 → P1 (크기 초과로 다음 청크에서 경계 발생)
            # chunk1: 50자  → P2 시작
            # chunk2: 50자  → P2 계속 (누적 100 < 200)
            text0 = "노헤딩_청크0 " * 30          # ~210자
            text1 = "노헤딩_청크1 " * 6           # ~50자
            text2 = "노헤딩_청크2 " * 6           # ~50자

            raw = [
                _make_raw_chunk(file_name, 0, [], page=1, text=text0),
                _make_raw_chunk(file_name, 1, [], page=1, text=text1),
                _make_raw_chunk(file_name, 2, [], page=1, text=text2),
            ]
            chunks, parents = build_parents(raw)

            # 전제 검증: P2 가 chunk1 과 chunk2 에 걸쳐야 함
            pid_by_idx = {c["chunk_index"]: c["parent_id"] for c in chunks}
            self.assertEqual(
                pid_by_idx[1], pid_by_idx[2],
                "전제 실패: chunk1 과 chunk2 가 같은 parent 여야 함"
            )
            self.assertNotEqual(
                pid_by_idx[0], pid_by_idx[1],
                "전제 실패: chunk0 과 chunk1 은 다른 parent 여야 함"
            )
            self.assertEqual(len(parents), 2, "전제 실패: parent 는 P1, P2 두 개여야 함")

            p2_id = pid_by_idx[1]

            with patch.object(self.db._embedder, "embed", side_effect=_mock_embed(self.dim)):
                self.db._embed_and_store(title, chunks, parents)

            # DB parent 총 행 수 = 2 (P2 중복 없음)
            total = _count_parent_rows(self.db, title)
            self.assertEqual(
                total, 2,
                f"DB parent 행 수 {total} (기대 2) — P2 가 두 배치에서 중복 삽입된 것으로 의심",
            )

            # P1, P2 모두 정상 조회
            all_pids = [p["parent_id"] for p in parents]
            parent_map = self.db._store.get_parents_by_ids(title, all_pids)
            self.assertEqual(
                set(parent_map.keys()), set(all_pids),
                "P1 또는 P2 가 DB 에서 조회되지 않음",
            )

            # cross-batch parent(P2) 가 중복 없이 저장됐는지 직접 확인
            table_name = self.db._store._parent_table_name(title)
            tbl = self.db._store._db.open_table(table_name)
            p2_rows = (
                tbl.search()
                .where(f"parent_id = '{p2_id}'")
                .limit(10)
                .to_list()
            )
            self.assertEqual(
                len(p2_rows), 1,
                f"P2(parent_id={p2_id}) 가 DB 에 {len(p2_rows)}번 저장됨 (기대 1)",
            )
        finally:
            if orig_batch_size is None:
                os.environ.pop("INGEST_BATCH_SIZE", None)
            else:
                os.environ["INGEST_BATCH_SIZE"] = orig_batch_size
            if orig_max_chars is None:
                os.environ.pop("MAX_PARENT_CHARS", None)
            else:
                os.environ["MAX_PARENT_CHARS"] = orig_max_chars
            if orig_min_chars is None:
                os.environ.pop("MIN_PARENT_CHARS", None)
            else:
                os.environ["MIN_PARENT_CHARS"] = orig_min_chars
            self.db.delete_title(title)

    # ── 2. 배치별 parent 정확 매칭 ─────────────────────────────────────────────

    def test_correct_parent_matching_per_batch(self):
        """
        배치 A(Chapter 1 청크)는 Chapter 1 parent만, 배치 B(Chapter 2 청크)는
        Chapter 2 parent만 upsert해야 한다.
        """
        title = "match_test"
        file_name = "match.txt"

        raw = [
            _make_raw_chunk(file_name, 0, ["Chapter 1"]),
            _make_raw_chunk(file_name, 1, ["Chapter 1"]),
            _make_raw_chunk(file_name, 2, ["Chapter 2"]),
            _make_raw_chunk(file_name, 3, ["Chapter 2"]),
        ]
        chunks, parents = build_parents(raw)

        ch1_parent_ids = {
            c["parent_id"] for c in chunks
            if (c.get("heading_path") or [""])[0] == "Chapter 1"
        }
        ch2_parent_ids = {
            c["parent_id"] for c in chunks
            if (c.get("heading_path") or [""])[0] == "Chapter 2"
        }
        # 전제: 두 heading 의 parent 집합은 겹치지 않아야 함
        self.assertFalse(ch1_parent_ids & ch2_parent_ids, "전제 실패: parent 집합이 겹침")

        upsert_calls: list[set[str]] = []
        orig = self.db._store.upsert_parents

        def tracking_upsert(t, bp, fn, append=False):
            upsert_calls.append({p["parent_id"] for p in bp})
            return orig(t, bp, fn, append=append)

        try:
            with (
                patch.object(self.db._embedder, "embed", side_effect=_mock_embed(self.dim)),
                patch.object(self.db._store, "upsert_parents", side_effect=tracking_upsert),
            ):
                self.db._embed_and_store(title, chunks, parents)

            all_upserted = set().union(*upsert_calls)
            all_expected = {p["parent_id"] for p in parents}
            self.assertEqual(all_upserted, all_expected, "일부 parent 가 upsert 되지 않음")

            for call_ids in upsert_calls:
                has_ch1 = bool(call_ids & ch1_parent_ids)
                has_ch2 = bool(call_ids & ch2_parent_ids)
                self.assertFalse(
                    has_ch1 and has_ch2,
                    f"한 upsert 호출에 Chapter 1 과 Chapter 2 parent 가 섞임: {call_ids}",
                )
        finally:
            self.db.delete_title(title)

    # ── 3a. embed 실패 → 예외 전파 ────────────────────────────────────────────

    def test_embed_failure_propagates(self):
        """두 번째 배치 embed 실패 시 RuntimeError 가 호출자에게 전파되어야 한다."""
        title = "fail_embed"
        file_name = "fail_embed.txt"

        raw = [
            _make_raw_chunk(file_name, 0, ["Chapter 1"]),
            _make_raw_chunk(file_name, 1, ["Chapter 2"]),  # 두 번째 배치
        ]
        chunks, parents = build_parents(raw)

        call_count = [0]
        embed_fn = _mock_embed(self.dim)

        def flaky_embed(texts):
            call_count[0] += 1
            if call_count[0] >= 2:
                raise RuntimeError("두 번째 배치 embed 강제 실패")
            return embed_fn(texts)

        try:
            with self.assertRaises(RuntimeError, msg="embed 실패가 전파되지 않음"):
                with patch.object(self.db._embedder, "embed", side_effect=flaky_embed):
                    self.db._embed_and_store(title, chunks, parents)
        finally:
            self.db.delete_title(title)

    # ── 3b. upsert(청크) 실패 → 예외 전파 ────────────────────────────────────

    def test_upsert_chunks_failure_propagates(self):
        """db_worker 내 upsert(청크) 실패 시 호출자에게 예외가 전파되어야 한다."""
        title = "fail_upsert"
        file_name = "fail_upsert.txt"

        raw = [_make_raw_chunk(file_name, 0, ["Chapter 1"])]
        chunks, parents = build_parents(raw)

        try:
            with (
                patch.object(self.db._embedder, "embed", side_effect=_mock_embed(self.dim)),
                patch.object(
                    self.db._store, "upsert", side_effect=RuntimeError("upsert 강제 실패")
                ),
            ):
                with self.assertRaises(RuntimeError, msg="upsert 실패가 전파되지 않음"):
                    self.db._embed_and_store(title, chunks, parents)
        finally:
            self.db.delete_title(title)

    # ── 3c. upsert_parents 실패 → 예외 전파 ──────────────────────────────────

    def test_upsert_parents_failure_propagates(self):
        """db_worker 내 upsert_parents 실패 시 호출자에게 예외가 전파되어야 한다."""
        title = "fail_parents"
        file_name = "fail_parents.txt"

        raw = [_make_raw_chunk(file_name, 0, ["Chapter 1"])]
        chunks, parents = build_parents(raw)

        try:
            with (
                patch.object(self.db._embedder, "embed", side_effect=_mock_embed(self.dim)),
                patch.object(
                    self.db._store,
                    "upsert_parents",
                    side_effect=RuntimeError("upsert_parents 강제 실패"),
                ),
            ):
                with self.assertRaises(RuntimeError, msg="upsert_parents 실패가 전파되지 않음"):
                    self.db._embed_and_store(title, chunks, parents)
        finally:
            self.db.delete_title(title)

    # ── 3d. 두 번째 배치 upsert_parents 실패 → 첫 배치 parents는 DB에 보존 ──

    def test_partial_failure_first_batch_parents_preserved(self):
        """
        두 번째 배치 upsert_parents 실패 시 첫 번째 배치 parents는 DB에 남아 있어야 한다.
        (실패 후 재시도 흐름에서 delete_parents_by_file 이 정리하므로 중간 상태 보존이 맞음)
        """
        title = "partial_fail"
        file_name = "partial.txt"

        raw = [
            _make_raw_chunk(file_name, 0, ["Chapter 1"]),
            _make_raw_chunk(file_name, 1, ["Chapter 2"]),
        ]
        chunks, parents = build_parents(raw)

        ch1_parent_ids = {
            c["parent_id"] for c in chunks
            if (c.get("heading_path") or [""])[0] == "Chapter 1"
        }

        call_count = [0]
        orig = self.db._store.upsert_parents

        def flaky_upsert_parents(t, bp, fn, append=False):
            call_count[0] += 1
            if call_count[0] >= 2:
                raise RuntimeError("두 번째 배치 upsert_parents 강제 실패")
            return orig(t, bp, fn, append=append)

        try:
            with (
                patch.object(self.db._embedder, "embed", side_effect=_mock_embed(self.dim)),
                patch.object(self.db._store, "upsert_parents", side_effect=flaky_upsert_parents),
            ):
                with self.assertRaises(RuntimeError):
                    self.db._embed_and_store(title, chunks, parents)

            # 첫 번째 배치(Chapter 1) parent 는 DB 에 저장되어 있어야 함
            saved = self.db._store.get_parents_by_ids(title, list(ch1_parent_ids))
            self.assertEqual(
                set(saved.keys()),
                ch1_parent_ids,
                "실패 전 첫 배치 parents 가 DB 에 없음",
            )
        finally:
            self.db.delete_title(title)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2, exit=False)
    finally:
        shutil.rmtree(tmp_db, ignore_errors=True)
