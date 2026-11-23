import logging
import os

from dotenv import load_dotenv

from .utils import timed

logger = logging.getLogger(__name__)

load_dotenv()


class Retriever:
    def __init__(self, store):
        self._store = store
        self._default_top_k = int(os.getenv("TOP_K", "5"))
        self._mode = os.getenv("SEARCH_MODE", "hybrid").lower()
        self._rrf_k = int(os.getenv("RRF_K", "60"))
        self._candidate_multiplier = int(os.getenv("CANDIDATE_MULTIPLIER", "4"))

    def search(
        self,
        title: str,
        query_text: str,
        query_vector: list[float],
        top_k: int | None = None,
        filter: dict | None = None,
    ) -> list[dict]:
        table = self._store.get_table(title)
        if table is None:
            return []

        k = top_k if top_k is not None else self._default_top_k

        if self._mode == "vector":
            rows = self._vector_rows(table, query_vector, k, filter)
        elif self._mode == "fts":
            rows = self._fts_rows(table, query_text, k, filter)
        else:
            rows = self._hybrid_rows(table, query_text, query_vector, k, filter)

        return [self._format(r) for r in rows]

    # ---------- internals ----------
    _SCALAR_FIELDS = (
        "file_name", "source_type", "page", "chunk_index",
        "content_hash", "id", "added_at", "parent_id",
    )

    def _apply_filter(self, query, filter: dict | None):
        """
        지원 형태:
          {"file_name": "x.pdf"}                     → file_name = 'x.pdf'
          {"source_type": "slide"}                   → source_type = 'slide'
          {"source_type": ["slide", "code"]}         → source_type IN ('slide','code')
          {"page": 5}                                → page = 5
          {"page": {"gte": 1, "lte": 10}}            → page >= 1 AND page <= 10
          {"file_name": "x.pdf", "source_type":"slide"} → AND 결합

        지원 필드: file_name, source_type, page, chunk_index, content_hash, id, added_at.
        heading_path 같은 리스트 필드는 LanceDB SQL 한계로 호출 측에서 후처리 필요.
        """
        if not filter:
            return query
        clauses: list[str] = []
        for key, val in filter.items():
            if val is None or key not in self._SCALAR_FIELDS:
                continue
            clause = self._build_clause(key, val)
            if clause:
                clauses.append(clause)
        if clauses:
            query = query.where(" AND ".join(clauses))
        return query

    @staticmethod
    def _quote(v):
        if isinstance(v, str):
            return "'" + v.replace("'", "''") + "'"
        return str(v)

    def _build_clause(self, key: str, val) -> str | None:
        if isinstance(val, list):
            if not val:
                return None
            return f"{key} IN ({', '.join(self._quote(v) for v in val)})"
        if isinstance(val, dict):
            op_map = {"gte": ">=", "gt": ">", "lte": "<=", "lt": "<", "eq": "=", "ne": "!="}
            parts = []
            for op, v in val.items():
                if op in op_map and v is not None:
                    parts.append(f"{key} {op_map[op]} {self._quote(v)}")
            return " AND ".join(parts) if parts else None
        return f"{key} = {self._quote(val)}"

    def _vector_rows(self, table, query_vector, limit, filter):
        # ANN 인덱스가 빌드되기 전(행 수 < ANN_MIN_ROWS)에는 LanceDB 가 default L2 로 검색해
        # 같은 쿼리에서도 인덱스 빌드 전후의 _distance 스케일이 달라진다 (L2² vs cosine).
        # 항상 cosine 으로 명시해 score 의 의미를 일관되게 유지한다.
        with timed("vector_search", logger):
            q = table.search(query_vector).distance_type("cosine").limit(limit)
            q = self._apply_filter(q, filter)
            return q.to_list()

    def _fts_rows(self, table, query_text, limit, filter):
        try:
            with timed("fts_search", logger):
                q = table.search(query_text, query_type="fts").limit(limit)
                q = self._apply_filter(q, filter)
                return q.to_list()
        except Exception as e:
            print(f"[WARN] FTS 검색 실패, 벡터 검색만 사용: {e}")
            return []

    def _hybrid_rows(self, table, query_text, query_vector, k, filter):
        n = k * self._candidate_multiplier
        v_rows = self._vector_rows(table, query_vector, n, filter)
        f_rows = self._fts_rows(table, query_text, n, filter)
        return self._rrf_merge(v_rows, f_rows, k)

    def _rrf_merge(self, vector_rows, fts_rows, k):
        # row id → 누적 RRF score
        scored: dict[str, dict] = {}
        for rank, row in enumerate(vector_rows):
            rid = row.get("id") or f"{row.get('file_name')}_{row.get('chunk_index')}"
            scored.setdefault(rid, {"row": row, "rrf": 0.0})
            scored[rid]["rrf"] += 1.0 / (self._rrf_k + rank + 1)
        for rank, row in enumerate(fts_rows):
            rid = row.get("id") or f"{row.get('file_name')}_{row.get('chunk_index')}"
            scored.setdefault(rid, {"row": row, "rrf": 0.0})
            scored[rid]["rrf"] += 1.0 / (self._rrf_k + rank + 1)
        merged = sorted(scored.values(), key=lambda x: x["rrf"], reverse=True)[:k]
        out = []
        for entry in merged:
            r = dict(entry["row"])
            r["_rrf"] = entry["rrf"]
            out.append(r)
        return out

    def fetch(
        self,
        title: str,
        filter: dict,
        limit: int = 1000,
    ) -> list[dict]:
        """의미 검색 없이 filter 조건만으로 chunks를 전부 조회한다."""
        table = self._store.get_table(title)
        if table is None:
            return []
        q = table.search().limit(limit)
        q = self._apply_filter(q, filter)
        return [self._format(r) for r in q.to_list()]

    def _format(self, row):
        # 점수: hybrid 모드는 rrf, 그 외는 1 - distance
        if "_rrf" in row:
            score = float(row["_rrf"])
        else:
            distance = row.get("_distance", 0.0)
            score = 1.0 - distance
        return {
            "id": row.get("id"),
            "text": row["text"],
            "source": row["file_name"],
            "page": row["page"],
            "chunk_index": row.get("chunk_index"),
            "score": score,
            "image_page": row.get("image_page", -1),
            "content_hash": row.get("content_hash", ""),
            "heading_path": list(row.get("heading_path") or []),
            "source_type": row.get("source_type", "general"),
            "parent_id": row.get("parent_id", ""),
        }
