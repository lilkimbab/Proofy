import base64
import logging
import os
import queue
import shutil
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)
from collections.abc import Callable
from datetime import datetime, timezone

from .utils import timed
from .parser import parse_file
from .chunker import chunk_documents
from .parent_builder import build_parents
from .embedder import Embedder
from .store import VectorStore
from .retriever import Retriever
from .reranker import Reranker
from .personalization import PersonalizationStore
from .pipeline import (
    SearchContext, SearchPipeline,
    RetrieveStage, RerankStage, PersonalBoostStage, QueryRecordStage,
)
from . import embed_meta


# reembed_title() 진행 중인 배치를 DB에 표시하는 sentinel.
# 서버 크래시 후 재시작 시 _trigger_reembed_if_stale()이 sentinel 행을 stale로 감지한다.
_REEMBED_SENTINEL = "reembed_in_progress"


class ReembedInProgressError(Exception):
    """해당 title의 재임베딩이 진행 중일 때 search()에서 발생한다."""
    def __init__(self, title: str):
        super().__init__(f"reembedding in progress for title: {title}")
        self.title = title


def _encode_image(image_path: str) -> str | None:
    if not image_path or not os.path.exists(image_path):
        return None
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


class _TitleWriteLockGuard:
    """
    title write lock 컨텍스트 매니저.
    enter 시 refcount++ 후 lock.acquire(), exit 시 lock.release() 후 refcount-- (0이면 GC).
    refcount 가 0이 될 때만 dict 에서 제거되므로 다른 holder 가 보유한 동안 락이 사라지지 않음.
    """

    def __init__(self, manager: "VectorDBManager", title: str):
        self._mgr = manager
        self._title = title
        self._lock: threading.Lock | None = None

    def __enter__(self):
        self._lock = self._mgr._acquire_title_write_lock(self._title)
        self._lock.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._lock is not None:
                self._lock.release()
        finally:
            self._mgr._release_title_write_lock(self._title)
        return False


class VectorDBManager:
    """
    Vector DB 모듈의 외부 진입점.
    parser → chunker → embedder → store/retriever를 내부적으로 연결한다.
    다른 에이전트는 이 클래스만 import하여 사용한다.
    """

    def __init__(self, subject_id: str | None = None):
        self._store = VectorStore()
        self._embedder = Embedder()
        self._retriever = Retriever(self._store)
        self._reranker = Reranker()
        self._personal = PersonalizationStore()
        self._subject_id = subject_id
        self._rerank_multiplier = int(os.getenv("RERANK_CANDIDATE_MULTIPLIER", "4"))
        self._pipeline = self._build_pipeline()

        # 동시성:
        #  - _title_write_locks: title 당 ingest/reembed 직렬화용 lock (검색은 영향 없음)
        #  - _title_write_refs: 같은 title 락을 잡고/대기 중인 holder 수. 0이 되면 dict 에서 제거
        #  - _reembedding_titles: 현재 재임베딩이 진행 중인 title 집합. search()는 이 집합만 본다
        #  - _meta_lock: 위 자료구조들의 mutation 보호
        # ⚠️ 단일 프로세스 한정. uvicorn --workers N 환경에서는 file lock/Redis 등으로 교체 필요.
        self._title_write_locks: dict[str, threading.Lock] = {}
        self._title_write_refs: dict[str, int] = {}
        self._reembedding_titles: set[str] = set()
        self._meta_lock = threading.Lock()

        # 서버 시작 시 stale title 자동 재임베딩
        self._trigger_reembed_if_stale()

    def _build_pipeline(self) -> SearchPipeline:
        return SearchPipeline([
            RetrieveStage(self._retriever),
            RerankStage(self._reranker),
            PersonalBoostStage(self._personal),
            QueryRecordStage(self._personal),
        ])

    def _title_write_lock(self, title: str) -> "_TitleWriteLockGuard":
        """
        title 단위 write lock 컨텍스트 매니저.
        refcount 로 holder 수를 추적해 마지막 holder 가 빠질 때 dict 에서 제거 →
        무작위 title 호출로 인한 lock dict 의 무한 증식 방지.
        """
        return _TitleWriteLockGuard(self, title)

    def _acquire_title_write_lock(self, title: str) -> threading.Lock:
        with self._meta_lock:
            if title not in self._title_write_locks:
                self._title_write_locks[title] = threading.Lock()
                self._title_write_refs[title] = 0
            self._title_write_refs[title] += 1
            return self._title_write_locks[title]

    def _release_title_write_lock(self, title: str) -> None:
        with self._meta_lock:
            self._title_write_refs[title] -= 1
            if self._title_write_refs[title] <= 0:
                self._title_write_refs.pop(title, None)
                self._title_write_locks.pop(title, None)

    def _mark_reembedding(self, title: str) -> None:
        with self._meta_lock:
            self._reembedding_titles.add(title)

    def _unmark_reembedding(self, title: str) -> None:
        with self._meta_lock:
            self._reembedding_titles.discard(title)

    def _is_reembedding(self, title: str) -> bool:
        with self._meta_lock:
            return title in self._reembedding_titles

    def _group_by_heading(self, chunks: list[dict]) -> list[list[dict]]:
        """
        heading_path[0] 기준으로 연속된 청크를 배치로 그루핑.
        헤딩이 전혀 없는 문서는 INGEST_BATCH_SIZE 크기의 고정 배치로 폴백.
        """
        batch_size = int(os.getenv("INGEST_BATCH_SIZE", "32"))
        has_headings = any(c.get("heading_path") for c in chunks)

        if not has_headings:
            return [chunks[i:i + batch_size] for i in range(0, len(chunks), batch_size)]

        groups: list[list[dict]] = []
        cur_key: str | None = None
        for c in chunks:
            hp = c.get("heading_path") or []
            key = hp[0] if hp else "__no_heading__"
            if key != cur_key:
                groups.append([])
                cur_key = key
            groups[-1].append(c)
        return groups

    def _embed_and_store(
        self,
        title: str,
        chunks: list[dict],
        parents: list[dict],
        on_batch: Callable | None = None,
        page_images: list[dict] | None = None,
    ) -> dict:
        """
        청크 + 부모 청크를 받아 임베딩 → 저장까지 수행.
        parse_document()로 이미 파싱된 결과를 재사용할 때 직접 호출한다.
        """
        # _embed_and_store 와 달리 chunks=[] 가드가 없어
        # 빈 PDF/빈 페이지만 있는 문서를 만나면 chunks[0] 에서 IndexError 로 죽고
        # BackgroundTask 가 silent failed 로 끝난다.
        if not chunks:
            return {"status": "ok", "chunks_added": 0}
        _t0 = time.perf_counter()
        _file_name = chunks[0]["file_name"]
        with self._title_write_lock(title):
            added_at = datetime.now(timezone.utc).isoformat()
            file_name = chunks[0]["file_name"]
            current_embed_model = os.getenv("EMBED_MODEL", "local").lower()
            current_db_version = embed_meta.current_db_version()

            parent_lookup = {p["parent_id"]: p for p in parents}
            batches = self._group_by_heading(chunks)
            n_batches = len(batches)
            row_queue: queue.Queue = queue.Queue(maxsize=int(os.getenv("EMBED_QUEUE_SIZE", "1")))
            cancel = threading.Event()
            db_exc: list[BaseException | None] = [None]
            total_ref = [0]

            def _enqueue(rows: list, batch_parents: list) -> None:
                """DB 스레드 사망 시 put()이 영구 블록하지 않도록 timeout 루프."""
                while not cancel.is_set():
                    try:
                        row_queue.put((rows, batch_parents), timeout=0.05)
                        return
                    except queue.Full:
                        pass

            def _send_sentinel() -> None:
                """sentinel(None) 투입.
                queue가 full + db_thread hang 조합에서 무한 루프 방지를 위해
                DB_THREAD_JOIN_TIMEOUT과 동일한 상한 내에 포기하고 join()에게 위임한다.
                """
                join_timeout = float(os.getenv("DB_THREAD_JOIN_TIMEOUT", "60"))
                deadline = time.monotonic() + join_timeout
                while True:
                    try:
                        row_queue.put(None, timeout=0.1)
                        return
                    except queue.Full:
                        if not db_thread.is_alive():
                            return
                        if time.monotonic() >= deadline:
                            return  # join(timeout=T) 이 TimeoutError 를 발생시킨다

            def db_worker() -> None:
                try:
                    self._store.delete_by_file(title, file_name)
                    self._store.delete_parents_by_file(title, file_name)
                    if page_images is not None:
                        self._store.upsert_page_images(title, page_images, file_name)
                    batch_i = 0
                    while True:
                        item = row_queue.get()
                        if item is None:
                            return
                        rows, batch_parents = item
                        self._store.upsert(title, rows, append=(batch_i > 0))
                        self._store.upsert_parents(title, batch_parents, file_name, append=True)
                        total_ref[0] += len(rows)
                        if on_batch:
                            on_batch(batch_i + 1, n_batches, total_ref[0])
                        batch_i += 1
                except BaseException as e:
                    logger.error(
                        "DB 스레드 오류 [title=%s file=%s]: %s",
                        title, file_name, e, exc_info=True,
                    )
                    db_exc[0] = e
                    cancel.set()

            db_thread = threading.Thread(target=db_worker, daemon=True)
            db_thread.start()

            try:
                emitted_parent_ids: set[str] = set()
                for i, batch in enumerate(batches):
                    if cancel.is_set():
                        break
                    vectors = self._embedder.embed([c["text"] for c in batch])
                    if len(vectors) != len(batch):
                        raise RuntimeError(
                            f"embed() 반환 개수 불일치: 입력 {len(batch)}개, "
                            f"반환 {len(vectors)}개 [title={title} batch={i+1}/{n_batches}]"
                        )
                    rows = []
                    new_parent_ids: set[str] = set()
                    for chunk, vector in zip(batch, vectors):
                        row = dict(chunk)
                        row["vector"] = vector
                        row["id"] = f"{chunk['file_name']}_{chunk['content_hash'][:12]}"
                        row["added_at"] = added_at
                        row["embed_model"] = current_embed_model
                        row["db_version"] = current_db_version
                        rows.append(row)
                        pid = row.get("parent_id")
                        if pid and pid not in emitted_parent_ids:
                            new_parent_ids.add(pid)
                    missing_pids = new_parent_ids - parent_lookup.keys()
                    if missing_pids:
                        logger.warning(
                            "parent_id 누락 [title=%s file=%s batch=%d/%d]: "
                            "%d개 청크가 parent 없이 저장됨: %s",
                            title, file_name, i + 1, n_batches,
                            len(missing_pids), missing_pids,
                        )
                    batch_parents = [parent_lookup[pid] for pid in new_parent_ids if pid in parent_lookup]
                    emitted_parent_ids |= new_parent_ids
                    _enqueue(rows, batch_parents)
            except Exception as e:
                logger.error(
                    "embed 오류 [title=%s file=%s batch=%d/%d]: %s",
                    title, file_name, i + 1, n_batches, e, exc_info=True,
                )
                raise
            finally:
                _send_sentinel()
                join_timeout = float(os.getenv("DB_THREAD_JOIN_TIMEOUT", "60"))
                db_thread.join(timeout=join_timeout)
                if db_thread.is_alive():
                    raise TimeoutError(
                        f"db_worker가 {join_timeout}s 내에 완료되지 않음 "
                        f"[title={title} file={file_name}]"
                    )

            if db_exc[0]:
                raise db_exc[0]

            self._store.rebuild_fts(title)
            result = {"status": "ok", "chunks_added": total_ref[0]}

        # 락 해제 후 ANN 빌드 — 빌드 시간이 길어도 검색을 블록하지 않음
        self._store.rebuild_ann(title)
        logger.info(
            "_embed_and_store %s/%s %d chunks: %.3fs",
            title, _file_name, result["chunks_added"], time.perf_counter() - _t0,
        )
        return result

    def parse_document(self, file_path: str) -> dict:
        """
        파일을 파싱 → 청킹 → 부모 청크 생성까지 수행.
        임베딩 없이 텍스트 전문 + 메타데이터를 반환한다.
        에이전트의 텍스트 접근 경로이며, 인제스트(embed+store)와 독립적이다.
        page_images: 비주얼이 있는 페이지의 {"file_name", "page", "image_path"} 행 목록.
        """
        parsed = parse_file(file_path)
        page_images = [
            {"file_name": d["file_name"], "page": d["page"], "image_path": path}
            for d in parsed
            for path in d.get("image_paths", [])
        ]
        raw_chunks = chunk_documents(parsed)
        if not raw_chunks:
            return {"chunks": [], "parents": [], "page_images": page_images}
        chunks, parents = build_parents(raw_chunks)
        return {"chunks": chunks, "parents": parents, "page_images": page_images}

    def search(
        self,
        query: str,
        title: str,
        top_k: int | None = None,
        filter: dict | None = None,
        user_id: str | None = None,
    ) -> list[dict]:
        """
        SearchPipeline 으로 단계별 검색 수행.
        해당 title의 재임베딩이 진행 중이면 즉시 ReembedInProgressError를 발생시킨다.
        검색끼리는 동시성 제한이 없다.
        """
        if self._is_reembedding(title):
            raise ReembedInProgressError(title)
        return self._search(query, title, top_k, filter, user_id)

    def _search(
        self,
        query: str,
        title: str,
        top_k: int | None = None,
        filter: dict | None = None,
        user_id: str | None = None,
    ) -> list[dict]:
        _t0 = time.perf_counter()
        k = top_k if top_k is not None else int(os.getenv("TOP_K", "5"))
        candidate_k = k * self._rerank_multiplier if self._reranker.enabled else k

        with timed("embed_single (query)", logger):
            query_vector = self._embedder.embed_single(query)

        ctx = SearchContext(
            query=query,
            title=title,
            query_vector=query_vector,
            top_k=k,
            candidate_top_k=candidate_k,
            filter=filter,
            user_id=user_id,
        )
        self._pipeline.run(ctx)

        results = ctx.results[:k]

        # parent 텍스트 조회 (검색 결과당 1번의 추가 DB 조회)
        with timed("parent+image lookup", logger):
            parent_ids = [r["parent_id"] for r in results if r.get("parent_id")]
            parent_map = self._store.get_parents_by_ids(title, parent_ids) if parent_ids else {}

            image_keys = [
                (r["source"], r["image_page"])
                for r in results
                if r.get("image_page", -1) != -1
            ]
            image_map = self._store.get_page_images(title, image_keys) if image_keys else {}

        encoded_cache: dict[str, str | None] = {}

        for r in results:
            parent = parent_map.get(r.get("parent_id", ""))
            r["parent_text"] = parent["text"] if parent else r.get("text")
            image_page = r.pop("image_page", -1)
            image_paths = image_map.get((r["source"], image_page), []) if image_page != -1 else []
            for p in image_paths:
                if p not in encoded_cache:
                    encoded_cache[p] = _encode_image(p)
            r["image"] = encoded_cache.get(image_paths[0]) if image_paths else None
            r["pipeline"] = list(ctx.trace)

        logger.info("search %r (title=%s, k=%d): %.3fs", query[:40], title, k, time.perf_counter() - _t0)
        return results

    def fetch(
        self,
        title: str,
        filter: dict,
        limit: int = 1000,
    ) -> list[dict]:
        """
        의미 검색 없이 filter 조건(page, file_name 등)만으로 chunks를 전부 조회한다.
        SearchPipeline을 거치지 않으므로 reranking/personalization 미적용.
        "315페이지의 모든 내용" 같은 구조적 쿼리에 사용한다.
        """
        rows = self._retriever.fetch(title, filter, limit)
        image_keys = [
            (r["source"], r["image_page"])
            for r in rows
            if r.get("image_page", -1) != -1
        ]
        image_map = self._store.get_page_images(title, image_keys) if image_keys else {}
        encoded_cache: dict[str, str | None] = {}

        for r in rows:
            image_page = r.pop("image_page", -1)
            image_paths = image_map.get((r["source"], image_page), []) if image_page != -1 else []
            for p in image_paths:
                if p not in encoded_cache:
                    encoded_cache[p] = _encode_image(p)
            r["image"] = encoded_cache.get(image_paths[0]) if image_paths else None
            r["parent_text"] = None
        return rows

    def record_feedback(self, user_id: str, title: str, chunk_id: str,
                        kind: str = "useful") -> None:
        self._personal.record_signal(user_id, title, chunk_id, kind=kind)

    def reload_config(self) -> dict:
        """
        .env 파일을 다시 읽고 retrieval 관련 컴포넌트를 재구성한다.
        EMBED_MODEL이 변경된 경우 임베더도 재초기화하며, stale title 은
        백그라운드에서 자동 재임베딩된다 (반환값엔 포함되지 않음).
        """
        from dotenv import load_dotenv
        old_model = os.getenv("EMBED_MODEL", "local")
        load_dotenv(override=False)
        new_model = os.getenv("EMBED_MODEL", "local")

        if old_model != new_model:
            self._embedder = Embedder()

        self._retriever = Retriever(self._store)
        self._reranker = Reranker()
        self._personal = PersonalizationStore()
        self._rerank_multiplier = int(os.getenv("RERANK_CANDIDATE_MULTIPLIER", "4"))
        self._pipeline = self._build_pipeline()

        self._trigger_reembed_if_stale()
        return {
            "search_mode": self._retriever._mode,
            "rerank_enabled": self._reranker.enabled,
            "personalization_enabled": self._personal.enabled,
            "rerank_candidate_multiplier": self._rerank_multiplier,
            "top_k_default": int(os.getenv("TOP_K", "5")),
            "chunk_strategy": os.getenv("CHUNK_STRATEGY", "structural"),
        }

    def list_titles(self) -> list[str]:
        return self._store.list_tables()

    def list_files(self, title: str) -> list[str]:
        return self._store.list_files(title)

    def _delete_image_dirs(self, image_paths: list[str]) -> None:
        dirs = {str(Path(p).parent) for p in image_paths if p}
        for d in dirs:
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)

    def delete_file(self, title: str, file_name: str) -> None:
        image_paths = self._store.get_image_paths_for_file(title, file_name)
        self._store.delete_by_file(title, file_name)
        self._store.delete_parents_by_file(title, file_name)
        self._delete_image_dirs(image_paths)

    def delete_title(self, title: str) -> None:
        image_paths = self._store.get_image_paths_for_title(title)
        self._store.delete_table(title)
        self._delete_image_dirs(image_paths)
        with self._meta_lock:
            # refcount 가 0인 title 만 정리 (in-flight write 가 있으면 그쪽이 정리)
            if self._title_write_refs.get(title, 0) == 0:
                self._title_write_locks.pop(title, None)
                self._title_write_refs.pop(title, None)
            self._reembedding_titles.discard(title)

    def _trigger_reembed_if_stale(self) -> None:
        """stale row가 있는 title을 DB에서 직접 스캔해 백그라운드 재임베딩을 시작한다."""
        current_version = embed_meta.current_db_version()
        targets = [
            t for t in self.list_titles()
            if self._store.has_stale_rows(t, current_version)
        ]
        if not targets:
            return
        print(f"[INFO] stale 벡터 감지 — 자동 재임베딩 시작: {targets}")
        threading.Thread(target=self._run_reembed, args=(targets,), daemon=True).start()

    def _run_reembed(self, titles: list[str]) -> None:
        for title in titles:
            try:
                result = self.reembed_title(title)
                print(f"[INFO] 재임베딩 완료: {title} ({result['chunks_reembedded']} chunks)")
            except Exception as e:
                print(f"[ERROR] 재임베딩 실패: {title}: {e}")

    def reembed_title(
        self,
        title: str,
        on_batch: Callable | None = None,
    ) -> dict:
        """
        title 내 stale row(db_version 불일치)만 선별해 현재 embedding 모델로 재생성한다.
        텍스트는 DB에서 읽으므로 원본 파일 없이 실행 가능하다.

        - dim 동일 (예: DB_VERSION 만 변경): 배치마다 ① sentinel 쓰기 → ② 임베딩 → ③ 정상값 쓰기.
          서버 크래시 후 재시작 시 sentinel 행이 stale로 감지되어 자동 재시도된다.
        - dim 변경 (예: EMBED_MODEL=local→openai, 1024→1536): 기존 fixed_size_list 스키마와
          호환되지 않으므로 전 row 임베딩 후 테이블을 통째로 교체한다. FTS 인덱스도 재구성한다.

        진행 중에는 _reembedding_titles 에 등록되어 search() 가 ReembedInProgressError 를 낸다.
        """
        self._mark_reembedding(title)
        try:
            return self._reembed_title_impl(title, on_batch)
        finally:
            self._unmark_reembedding(title)

    def _reembed_title_impl(
        self,
        title: str,
        on_batch: Callable | None,
    ) -> dict:
        with self._title_write_lock(title):
            current_version = embed_meta.current_db_version()
            current_model = os.getenv("EMBED_MODEL", "local").lower()
            new_dim = self._embedder.dimension
            old_dim = self._store.get_vector_dim(title)

            # dim 변경 시: fixed_size_list 재정의 필요 → 전 row 재임베딩 + 테이블 교체
            if old_dim is not None and old_dim != new_dim:
                rows = self._store.get_all_rows(title)
                if not rows:
                    return {"status": "ok", "title": title, "chunks_reembedded": 0}
                for row in rows:
                    row.setdefault("embed_model", "")
                    row.setdefault("db_version", "")
                    row.setdefault("image_page", -1)
                return self._reembed_with_table_replace(
                    title, rows, current_model, current_version, on_batch
                )

            # in-place: stale row 만 스트리밍 로드 (텍스트 불변, vector/db_version 만 갱신)
            stale_rows = self._store.get_stale_rows(title, current_version)
            if not stale_rows:
                return {"status": "ok", "title": title, "chunks_reembedded": 0}
            for row in stale_rows:
                row.setdefault("embed_model", "")
                row.setdefault("db_version", "")
                row.setdefault("image_page", -1)
            return self._reembed_in_place(
                title, stale_rows, current_model, current_version, on_batch
            )

    def _reembed_in_place(
        self,
        title: str,
        stale_rows: list[dict],
        current_model: str,
        current_version: str,
        on_batch: Callable | None,
    ) -> dict:
        embedded = 0
        batch_size = int(os.getenv("INGEST_BATCH_SIZE", "32"))
        total = len(stale_rows)
        total_batches = (total + batch_size - 1) // batch_size

        for b in range(0, total, batch_size):
            batch = stale_rows[b:b + batch_size]

            # 배치 진행 중을 DB 에 표시 → 크래시 후 재시작 시 stale 로 감지되어 자동 재시도
            sentinel_rows = []
            for r in batch:
                s = dict(r)
                s["db_version"] = _REEMBED_SENTINEL
                s["embed_model"] = ""
                sentinel_rows.append(s)
            self._store.update_rows(title, sentinel_rows)

            vectors = self._embedder.embed([r["text"] for r in batch])
            if len(vectors) != len(batch):
                raise RuntimeError(
                    f"embed() 반환 개수 불일치: 입력 {len(batch)}개, "
                    f"반환 {len(vectors)}개 [title={title} reembed_in_place]"
                )

            for r, vec in zip(batch, vectors):
                r["vector"] = vec
                r["embed_model"] = current_model
                r["db_version"] = current_version
            self._store.update_rows(title, batch)

            embedded += len(batch)
            if on_batch:
                on_batch(b // batch_size + 1, total_batches, embedded)

        # 텍스트 불변 → FTS 재구성 불필요
        self._store.rebuild_ann(title)
        return {"status": "ok", "title": title, "chunks_reembedded": embedded}

    def _reembed_with_table_replace(
        self,
        title: str,
        rows: list[dict],
        current_model: str,
        current_version: str,
        on_batch: Callable | None,
    ) -> dict:
        """
        embedding 차원이 바뀐 경우(예: bge-m3 1024 → openai 1536) 호출된다.
        기존 fixed_size_list 스키마는 새 dim 을 못 받으므로 테이블을 교체한다.
        """
        print(f"[INFO] embedding dim 변경 감지 — 테이블 재생성: title={title} "
              f"({self._store.get_vector_dim(title)} → {self._embedder.dimension})")

        batch_size = int(os.getenv("INGEST_BATCH_SIZE", "32"))
        total_batches = (len(rows) + batch_size - 1) // batch_size
        embedded = 0

        for b in range(0, len(rows), batch_size):
            chunk_rows = rows[b:b + batch_size]
            vectors = self._embedder.embed([r["text"] for r in chunk_rows])
            if len(vectors) != len(chunk_rows):
                raise RuntimeError(
                    f"embed() 반환 개수 불일치: 입력 {len(chunk_rows)}개, "
                    f"반환 {len(vectors)}개 [title={title} reembed_table_replace]"
                )
            for r, vec in zip(chunk_rows, vectors):
                r["vector"] = vec
                r["embed_model"] = current_model
                r["db_version"] = current_version
            embedded += len(chunk_rows)
            if on_batch:
                on_batch(b // batch_size + 1, total_batches, embedded)

        self._store.replace_table(title, rows)
        # 스키마가 바뀌어 인덱스가 모두 무효화됨
        self._store.rebuild_fts(title)
        self._store.rebuild_ann(title)
        return {"status": "ok", "title": title, "chunks_reembedded": embedded}
