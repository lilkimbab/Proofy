import os
import pyarrow as pa
from dotenv import load_dotenv

load_dotenv()

_PREFIX = "title_"
_PARENT_PREFIX = "parent_"
_PAGEIMG_PREFIX = "pageimg_"

# create_table 시 lance 가 List(Null) 로 추론하지 않도록 List(Utf8) 로 강제할 컬럼.
# 모든 row 의 heading_path 가 빈 리스트일 때(첫 batch 가 헤더 등장 전이면 흔함) 발생하던
# "cannot cast field 'heading_path' from List(Utf8) to List(Null)" 차단용.
_LIST_STR_COLS = ("heading_path",)


def _to_arrow_safe(rows: list[dict]) -> pa.Table:
    """rows → pa.Table 변환 시 list-of-string 컬럼이 List(Null) 로 추론되면 List(Utf8) 로 캐스팅."""
    table = pa.Table.from_pylist(rows)
    for col_name in _LIST_STR_COLS:
        if col_name not in table.column_names:
            continue
        col = table.column(col_name)
        if pa.types.is_list(col.type) and pa.types.is_null(col.type.value_type):
            new_col = pa.array(
                [r.get(col_name) or [] for r in rows],
                type=pa.list_(pa.string()),
            )
            idx = table.schema.get_field_index(col_name)
            table = table.set_column(
                idx, pa.field(col_name, pa.list_(pa.string())), new_col
            )
    return table


def _encode_title(title: str) -> str:
    """title → hex-encoded string (LanceDB only allows alphanumeric/underscore/hyphen/period)"""
    return title.encode("utf-8").hex()


def _decode_title(hex_str: str) -> str:
    return bytes.fromhex(hex_str).decode("utf-8")


class VectorStore:
    def __init__(self):
        import lancedb
        db_path = os.getenv("LANCEDB_PATH", "./lancedb_store")
        self._db = lancedb.connect(db_path)

    def _table_name(self, title: str) -> str:
        return f"{_PREFIX}{_encode_title(title)}"

    def _parent_table_name(self, title: str) -> str:
        return f"{_PARENT_PREFIX}{_encode_title(title)}"

    def _page_images_table_name(self, title: str) -> str:
        return f"{_PAGEIMG_PREFIX}{_encode_title(title)}"

    def upsert(self, title: str, rows: list[dict], append: bool = False) -> int:
        """
        append=False (기본): 테이블 생성 또는 기존 file_name 교체. 첫 배치 또는 단건 호출에 사용.
        append=True: 테이블에 row 를 순수 추가. 배치 2번째 이후에 사용.
        FTS 재구성은 호출자(manager)가 모든 배치 완료 후 rebuild_fts() 로 수행한다.
        """
        table_name = self._table_name(title)

        for row in rows:
            row.setdefault("image_page", -1)
            row.setdefault("content_hash", "")
            row.setdefault("heading_path", [])
            row.setdefault("source_type", "general")
            row.setdefault("embed_model", "")
            row.setdefault("db_version", "")

        if append:
            table = self._db.open_table(table_name)
            table.add(rows)
            return len(rows)

        existing = self._db.list_tables().tables
        if table_name not in existing:
            self._db.create_table(table_name, data=_to_arrow_safe(rows))
        else:
            table = self._db.open_table(table_name)
            existing_cols = set(table.schema.names)
            new_cols = set(rows[0].keys())

            # 구버전 호환: image_path 컬럼 있고 image_page 없으면 스키마 마이그레이션 대상
            needs_migration = (
                not new_cols.issubset(existing_cols)
                or ("image_path" in existing_cols and "image_page" not in existing_cols)
            )

            if needs_migration:
                # 스키마 진화: 새 컬럼 추가 시 기존 데이터 백필 후 mode="overwrite" 로 원자적 swap.
                # to_batches() RecordBatchReader 로 스트리밍 → arrow 풀 머터리얼라이즈 회피로 피크 메모리 절감.
                file_name = rows[0]["file_name"]
                safe_file = file_name.replace("'", "''")
                stream_batch_size = int(os.getenv("MIGRATION_STREAM_BATCH", "1024"))
                old_rows: list[dict] = []
                reader = (
                    table.search()
                    .where(f"file_name != '{safe_file}'")
                    .to_batches(batch_size=stream_batch_size)
                )
                for batch in reader:
                    for r in batch.to_pylist():
                        r.setdefault("content_hash", "")
                        r.setdefault("heading_path", [])
                        r.setdefault("source_type", "general")
                        # image_path → image_page 마이그레이션: 기존 값은 버리고 -1 로 백필
                        r.pop("image_path", None)
                        r.setdefault("image_page", -1)
                        r.setdefault("embed_model", "")
                        r.setdefault("db_version", "")
                        old_rows.append(r)
                print(f"[INFO] schema migration: '{title}' 재구축 ({len(old_rows)} 보존 + {len(rows)} 신규)")
                self._db.create_table(
                    table_name, data=_to_arrow_safe(old_rows + rows), mode="overwrite"
                )
            else:
                file_name = rows[0]["file_name"]
                safe_file = file_name.replace("'", "''")
                table.delete(f"file_name = '{safe_file}'")
                table.add(rows)

        return len(rows)

    def rebuild_fts(self, title: str) -> None:
        """모든 배치 완료 후 FTS 인덱스를 재구성한다. vector 전용 모드에서는 no-op."""
        if os.getenv("SEARCH_MODE", "hybrid").lower() == "vector":
            return
        table = self.get_table(title)
        if table is None:
            return
        try:
            table.create_fts_index("text", replace=True)
        except Exception as e:
            print(f"[WARN] FTS index 생성 실패 (title={title}): {e}")

    def rebuild_ann(self, title: str) -> bool:
        """배치·재임베딩 완료 후 ANN(IVF-PQ) 인덱스를 재구성한다.
        fts 전용 모드거나 행 수가 ANN_MIN_ROWS 미만이면 no-op.
        반환: 인덱스를 실제로 생성했으면 True, skip/실패 시 False.

        스피드업: S(N) = N·d / (L·d + p·(N/L)·M + d·K)
        N≥515(d=1024,L=256,p=20,M=64) 부터 flat-scan 대비 이득 발생.
        점근치 S_∞ ≈ d·L/(p·M) ≈ 205×.
        """
        import math

        if os.getenv("SEARCH_MODE", "hybrid").lower() == "fts":
            return False

        table = self.get_table(title)
        if table is None:
            return False

        n = table.count_rows()
        min_rows = int(os.getenv("ANN_MIN_ROWS", "256"))
        if n < min_rows:
            return False

        # IVF: num_partitions ≈ √N, bounded [8, 256]
        num_partitions = min(256, max(8, int(math.sqrt(n))))

        # PQ: d의 약수 중 최대값 선택 (96→64→...→4 순)
        dim = self.get_vector_dim(title)
        if dim is None:
            return False

        num_sub_vectors = next(
            (v for v in [96, 64, 48, 32, 16, 8, 4] if dim % v == 0), 1
        )

        try:
            table.create_index(
                metric="cosine",
                vector_column_name="vector",
                index_type="IVF_PQ",
                num_partitions=num_partitions,
                num_sub_vectors=num_sub_vectors,
                replace=True,
            )
            return True
        except Exception as e:
            print(f"[WARN] ANN index 생성 실패 (title={title}): {e}")
            return False

    def delete_by_file(self, title: str, file_name: str) -> None:
        table_name = self._table_name(title)
        if table_name not in self._db.list_tables().tables:
            return
        table = self._db.open_table(table_name)
        safe = file_name.replace("'", "''")
        table.delete(f"file_name = '{safe}'")
        self.delete_page_images_by_file(title, file_name)

    def upsert_parents(self, title: str, parents: list[dict], file_name: str, append: bool = False) -> None:
        """parent 레코드를 저장한다.
        append=False(기본): 같은 file_name의 기존 parents를 먼저 삭제 후 삽입.
        append=True: 삭제 없이 추가만 한다 (db_worker 내 배치별 호출 시 사용).
        """
        if not parents:
            return
        table_name = self._parent_table_name(title)
        existing = self._db.list_tables().tables
        if table_name not in existing:
            self._db.create_table(table_name, data=_to_arrow_safe(parents))
        else:
            tbl = self._db.open_table(table_name)
            if not append:
                safe = file_name.replace("'", "''")
                tbl.delete(f"file_name = '{safe}'")
            tbl.add(parents)
        self._ensure_parent_id_index(table_name)

    def _ensure_parent_id_index(self, table_name: str) -> None:
        """parent_id 에 BTREE scalar 인덱스를 보장. 이미 있으면 no-op.
        get_parents_by_ids 의 IN 조회 푸시다운을 가속한다.
        """
        try:
            tbl = self._db.open_table(table_name)
            for idx in tbl.list_indices():
                cols = getattr(idx, "columns", None) or []
                if "parent_id" in cols:
                    return
            tbl.create_scalar_index("parent_id", index_type="BTREE", replace=False)
        except Exception as e:
            print(f"[WARN] parent_id scalar index 생성 실패 ({table_name}): {e}")

    def ensure_parent_indexes(self, title: str | None = None) -> list[str]:
        """기존 parent 테이블에 scalar 인덱스를 백필한다. 코드 갱신 후 1회 호출 용도.
        반환: 인덱스 보장 시도가 끝난 title 목록.
        """
        if title is not None:
            self._ensure_parent_id_index(self._parent_table_name(title))
            return [title]
        done: list[str] = []
        for t in self._db.list_tables().tables:
            if t.startswith(_PARENT_PREFIX):
                self._ensure_parent_id_index(t)
                try:
                    done.append(_decode_title(t[len(_PARENT_PREFIX):]))
                except (ValueError, UnicodeDecodeError):
                    pass
        return done

    def get_parents_by_ids(self, title: str, parent_ids: list[str]) -> dict[str, dict]:
        """parent_id 목록으로 parent 레코드를 한 번에 조회한다.
        WHERE 절로 LanceDB 에 푸시다운하여 매칭 행만 읽는다.
        """
        if not parent_ids:
            return {}
        table_name = self._parent_table_name(title)
        if table_name not in self._db.list_tables().tables:
            return {}
        tbl = self._db.open_table(table_name)
        # parent_id 는 sha256 hex(16자) — 영숫자만이지만 방어적으로 escaping
        unique_ids = {pid.replace("'", "''") for pid in parent_ids}
        in_clause = ",".join(f"'{pid}'" for pid in unique_ids)
        rows = (
            tbl.search()
            .where(f"parent_id IN ({in_clause})")
            .limit(len(unique_ids))
            .to_list()
        )
        return {r["parent_id"]: r for r in rows}

    def upsert_page_images(self, title: str, rows: list[dict], file_name: str) -> None:
        """rows: [{"file_name": ..., "page": ..., "image_path": ...}]
        같은 file_name 의 기존 행을 먼저 삭제 후 삽입한다."""
        if not rows:
            return
        table_name = self._page_images_table_name(title)
        existing = self._db.list_tables().tables
        if table_name not in existing:
            tbl = self._db.create_table(table_name, data=pa.Table.from_pylist(rows))
            tbl.create_scalar_index("page", index_type="BTREE")
        else:
            tbl = self._db.open_table(table_name)
            safe = file_name.replace("'", "''")
            tbl.delete(f"file_name = '{safe}'")
            tbl.add(rows)

    def get_page_images(self, title: str, keys: list[tuple[str, int]]) -> dict[tuple[str, int], list[str]]:
        """(file_name, page) 목록으로 image_path 목록을 일괄 조회.
        페이지당 여러 크롭이 있을 수 있으므로 반환 값은 list[str].
        반환: {(file_name, page): [image_path, ...]}"""
        if not keys:
            return {}
        table_name = self._page_images_table_name(title)
        if table_name not in self._db.list_tables().tables:
            return {}
        tbl = self._db.open_table(table_name)
        pages = list({page for _, page in keys})
        in_clause = ",".join(str(p) for p in pages)
        rows = (
            tbl.search()
            .where(f"page IN ({in_clause})")
            .limit(len(pages) * 20)
            .to_list()
        )
        key_set = set(keys)
        result: dict[tuple[str, int], list[str]] = {}
        for r in rows:
            key = (r["file_name"], r["page"])
            if key in key_set:
                result.setdefault(key, []).append(r["image_path"])
        return result

    def delete_page_images_by_file(self, title: str, file_name: str) -> None:
        """해당 file_name 의 page_images 행 삭제."""
        table_name = self._page_images_table_name(title)
        if table_name not in self._db.list_tables().tables:
            return
        tbl = self._db.open_table(table_name)
        safe = file_name.replace("'", "''")
        tbl.delete(f"file_name = '{safe}'")

    def get_image_paths_for_title(self, title: str) -> list[str]:
        table_name = self._page_images_table_name(title)
        if table_name not in self._db.list_tables().tables:
            return []
        tbl = self._db.open_table(table_name)
        paths = tbl.to_arrow().column("image_path").to_pylist()
        return list({p for p in paths if p})

    def get_image_paths_for_file(self, title: str, file_name: str) -> list[str]:
        table_name = self._page_images_table_name(title)
        if table_name not in self._db.list_tables().tables:
            return []
        tbl = self._db.open_table(table_name)
        safe = file_name.replace("'", "''")
        rows = (
            tbl.search()
            .where(f"file_name = '{safe}'")
            .select(["image_path"])
            .limit(tbl.count_rows())
            .to_list()
        )
        return list({r["image_path"] for r in rows if r.get("image_path")})

    def delete_parents_by_file(self, title: str, file_name: str) -> None:
        table_name = self._parent_table_name(title)
        if table_name not in self._db.list_tables().tables:
            return
        tbl = self._db.open_table(table_name)
        safe = file_name.replace("'", "''")
        tbl.delete(f"file_name = '{safe}'")

    def delete_table(self, title: str) -> None:
        for tname in [
            self._table_name(title),
            self._parent_table_name(title),
            self._page_images_table_name(title),
        ]:
            if tname in self._db.list_tables().tables:
                self._db.drop_table(tname)

    def list_tables(self) -> list[str]:
        all_tables = self._db.list_tables().tables
        result = []
        for t in all_tables:
            if t.startswith(_PREFIX):
                hex_part = t[len(_PREFIX):]
                try:
                    result.append(_decode_title(hex_part))
                except (ValueError, UnicodeDecodeError):
                    pass
        return result

    def list_files(self, title: str) -> list[str]:
        table_name = self._table_name(title)
        if table_name not in self._db.list_tables().tables:
            return []
        table = self._db.open_table(table_name)
        arrow = table.to_arrow()
        if arrow.num_rows == 0:
            return []
        file_names = arrow.column("file_name").to_pylist()
        return sorted(set(file_names))

    def get_table(self, title: str):
        table_name = self._table_name(title)
        if table_name not in self._db.list_tables().tables:
            return None
        return self._db.open_table(table_name)

    def get_vector_dim(self, title: str) -> int | None:
        """기존 테이블의 vector 컬럼 차원 (fixed_size_list size)을 반환. 없으면 None."""
        import pyarrow as pa
        table = self.get_table(title)
        if table is None:
            return None
        return next(
            (f.type.list_size for f in table.schema
             if f.name == "vector" and pa.types.is_fixed_size_list(f.type)),
            None,
        )

    def has_stale_rows(self, title: str, current_version: str) -> bool:
        """
        db_version 이 current_version 과 다른 row 가 한 개라도 있으면 True.
        db_version 컬럼 자체가 없는 레거시 테이블은 무조건 stale로 판정한다.
        """
        table = self.get_table(title)
        if table is None:
            return False
        if "db_version" not in table.schema.names:
            return True
        try:
            safe = current_version.replace("'", "''")
            stale = (
                table.search()
                .where(f"db_version != '{safe}'")
                .select(["db_version"])
                .limit(1)
                .to_arrow()
            )
            return stale.num_rows > 0
        except Exception:
            return True

    def get_all_rows(self, title: str) -> list[dict]:
        """테이블의 모든 row를 반환한다. 테이블이 없으면 빈 리스트."""
        table = self.get_table(title)
        if table is None:
            return []
        return table.to_arrow().to_pylist()

    def get_stale_rows(self, title: str, current_version: str) -> list[dict]:
        """
        db_version 이 current_version 과 다른 row 만 스트리밍으로 반환한다.
        - db_version 컬럼이 없는 레거시 테이블은 모든 row 가 stale → 전체 반환.
        - NULL 도 stale 로 간주 (SQL `!=` 가 NULL 을 제외하는 것을 회피).
        """
        table = self.get_table(title)
        if table is None:
            return []
        if "db_version" not in table.schema.names:
            return table.to_arrow().to_pylist()
        safe = current_version.replace("'", "''")
        stream_batch_size = int(os.getenv("REEMBED_STREAM_BATCH", "1024"))
        out: list[dict] = []
        reader = (
            table.search()
            .where(f"db_version IS NULL OR db_version != '{safe}'")
            .to_batches(batch_size=stream_batch_size)
        )
        for batch in reader:
            out.extend(batch.to_pylist())
        return out

    def update_rows(self, title: str, rows: list[dict]) -> None:
        """
        id 기준으로 특정 행만 in-place 업데이트한다.
        reembedding의 sentinel 쓰기(①)와 정상값 쓰기(③)에 사용.
        테이블이 없거나 rows가 비어 있으면 no-op.

        매치 실패 row 는 insert 로 폴백한다. 이렇게 하지 않으면 reembed 도중
        외부 경로(예: delete_by_file)로 row 가 사라졌을 때 정상값 쓰기가
        조용히 no-op 으로 끝나 카운터만 증가하고 DB 는 비어 있는 상태가 된다.
        """
        table = self.get_table(title)
        if table is None or not rows:
            return
        for row in rows:
            row.setdefault("image_page", -1)
            row.setdefault("content_hash", "")
            row.setdefault("heading_path", [])
            row.setdefault("source_type", "general")
            row.setdefault("embed_model", "")
            row.setdefault("db_version", "")
        (
            table.merge_insert("id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(rows)
        )

    def replace_table(self, title: str, rows: list[dict]) -> int:
        """
        기존 테이블을 rows 로 통째 교체한다. mode="overwrite" 로 lance manifest 의
        원자적 swap 에 의존 → drop 후 create 전 크래시 시 데이터 유실 방지.
        rows 가 비어 있으면 기존 테이블 drop.
        """
        table_name = self._table_name(title)
        if not rows:
            if table_name in self._db.list_tables().tables:
                self._db.drop_table(table_name)
            return 0
        self._db.create_table(table_name, data=_to_arrow_safe(rows), mode="overwrite")
        return len(rows)

    def ensure_fts_index(self, title: str | None = None) -> list[str]:
        """
        title 지정 시 해당 테이블, 아니면 모든 테이블에 FTS 인덱스를 생성한다.
        vector-only 모드로 운영하다가 hybrid/fts 로 전환할 때 호출.
        반환: 인덱스가 (재)생성된 title 목록.
        """
        targets = [title] if title else self.list_tables()
        rebuilt: list[str] = []
        for t in targets:
            tbl = self.get_table(t)
            if tbl is None:
                continue
            try:
                tbl.create_fts_index("text", replace=True)
                rebuilt.append(t)
            except Exception as e:
                print(f"[WARN] FTS index 생성 실패 (title={t}): {e}")
        return rebuilt

    def ensure_ann_index(self, title: str | None = None) -> list[str]:
        """
        title 지정 시 해당 테이블, 아니면 모든 테이블에 ANN 인덱스를 생성한다.
        fts-only 모드로 운영하다가 vector/hybrid 로 전환할 때 호출.
        반환: 인덱스가 실제로 생성된 title 목록 (skip·실패 제외).
        """
        targets = [title] if title else self.list_tables()
        rebuilt: list[str] = []
        for t in targets:
            if self.rebuild_ann(t):
                rebuilt.append(t)
        return rebuilt
