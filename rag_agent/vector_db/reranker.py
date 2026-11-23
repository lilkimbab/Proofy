import logging
import os

from dotenv import load_dotenv

from .utils import timed

logger = logging.getLogger(__name__)

load_dotenv()


class Reranker:
    """
    BAAI/bge-reranker-v2-m3 기반 cross-encoder reranker.
    RERANK_ENABLED=false 또는 모델 로드 실패 시 입력 순서를 그대로 반환(no-op).
    """

    def __init__(self):
        self._enabled = os.getenv("RERANK_ENABLED", "true").lower() == "true"
        self._model_name = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
        self._reranker = None
        if self._enabled:
            try:
                from FlagEmbedding import FlagReranker
                self._reranker = FlagReranker(self._model_name, use_fp16=True)
            except Exception as e:
                print(f"[WARN] Reranker 로드 실패, no-op 으로 동작: {e}")
                self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled and self._reranker is not None

    def rerank(self, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        if not self.enabled or not candidates:
            return candidates[:top_k]

        pairs: list[tuple[str, str]] = [(query, c["text"]) for c in candidates]
        assert self._reranker is not None  # enabled 가드로 보장됨
        with timed(f"rerank {len(candidates)}→{top_k}", logger, logging.INFO):
            scores = self._reranker.compute_score(pairs, normalize=True)

        # 단일 후보일 경우 scores 가 float, 실패 시 None 일 수 있음
        if scores is None:
            return candidates[:top_k]
        if isinstance(scores, float):
            scores = [scores]

        ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
        out = []
        for cand, score in ranked[:top_k]:
            r = dict(cand)
            r["score"] = float(score)
            r["_rerank_score"] = float(score)
            out.append(r)
        return out
