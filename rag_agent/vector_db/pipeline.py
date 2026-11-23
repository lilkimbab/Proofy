"""
검색 파이프라인.
manager.search() 의 단계별 처리(retrieve → rerank → personalize → record)를
독립된 Stage 객체로 분리하여 단계 추가/제거를 용이하게 한다.

각 Stage 는 SearchContext 를 받아 in-place 로 results / trace 를 갱신한다.
새 단계가 필요하면 Stage 를 하나 더 만들어 SearchPipeline 에 끼워 넣으면 된다.
"""

import logging
from dataclasses import dataclass, field

from .utils import timed

logger = logging.getLogger(__name__)


@dataclass
class SearchContext:
    query: str
    title: str
    query_vector: list[float]
    top_k: int                # 최종 반환할 결과 수
    candidate_top_k: int      # 1차 검색에서 뽑을 후보 수 (rerank 활성 시 더 큼)
    filter: dict | None = None
    user_id: str | None = None
    results: list[dict] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)


class Stage:
    """모든 stage 의 공통 인터페이스. apply() 는 ctx 를 in-place 변경."""

    name: str = "stage"

    def apply(self, ctx: SearchContext) -> None:
        raise NotImplementedError


class RetrieveStage(Stage):
    name = "retrieve"

    def __init__(self, retriever):
        self._retriever = retriever

    def apply(self, ctx: SearchContext) -> None:
        ctx.results = self._retriever.search(
            ctx.title, ctx.query, ctx.query_vector,
            ctx.candidate_top_k, ctx.filter,
        )
        ctx.trace.append(f"retrieve:{self._retriever._mode}")


class RerankStage(Stage):
    name = "rerank"

    def __init__(self, reranker):
        self._reranker = reranker

    def apply(self, ctx: SearchContext) -> None:
        if not self._reranker.enabled:
            return
        ctx.results = self._reranker.rerank(ctx.query, ctx.results, ctx.top_k)
        ctx.trace.append("rerank")


class PersonalBoostStage(Stage):
    name = "personal_boost"

    def __init__(self, personal):
        self._personal = personal

    def apply(self, ctx: SearchContext) -> None:
        if not (self._personal.enabled and ctx.user_id):
            return
        for r in ctx.results:
            cid = r.get("id") or f"{r.get('source')}_{r.get('chunk_index', '')}"
            r["score"] = float(r["score"]) * self._personal.boost(
                ctx.user_id, ctx.title, cid
            )
        ctx.results.sort(key=lambda r: r["score"], reverse=True)
        ctx.trace.append("personal_boost")


class TruncateStage(Stage):
    """rerank 가 비활성인 경우에도 candidate_top_k 가 top_k 와 같으므로 사실상 no-op."""

    name = "truncate"

    def apply(self, ctx: SearchContext) -> None:
        ctx.results = ctx.results[: ctx.top_k]


class QueryRecordStage(Stage):
    name = "query_record"

    def __init__(self, personal):
        self._personal = personal

    def apply(self, ctx: SearchContext) -> None:
        if not ctx.user_id:
            return
        self._personal.record_query(ctx.user_id, ctx.title, ctx.query)
        ctx.trace.append("query_record")


class SearchPipeline:
    """Stage 리스트를 순차 실행."""

    def __init__(self, stages: list[Stage]):
        self.stages = stages

    def run(self, ctx: SearchContext) -> SearchContext:
        for stage in self.stages:
            with timed(f"pipeline.{stage.name}", logger):
                stage.apply(ctx)
        return ctx
