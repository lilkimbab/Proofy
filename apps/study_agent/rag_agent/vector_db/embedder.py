import logging
import os
import threading

from dotenv import load_dotenv

from .utils import timed

logger = logging.getLogger(__name__)

load_dotenv()


class Embedder:
    """
    환경변수 EMBED_MODEL에 따라 로컬 또는 OpenAI 임베딩을 제공.
    인스턴스화 시 모델을 로드한다 (로컬은 첫 호출 시 다운로드).

    동시성: SentenceTransformer 의 내부 rust tokenizer 는 thread-safe 하지 않다
    (동시 호출 시 RuntimeError: Already borrowed). embed/embed_single 호출을
    인스턴스 락으로 직렬화한다. throughput 이 병목이면 워커 풀로 교체.
    """

    def __init__(self):
        self._model_type = os.getenv("EMBED_MODEL", "local").lower()
        self._lock = threading.Lock()

        if self._model_type == "local":
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("BAAI/bge-m3")
        elif self._model_type == "openai":
            from openai import OpenAI
            self._client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        else:
            raise ValueError(
                f"Unsupported EMBED_MODEL: '{self._model_type}'. "
                "Use 'local' or 'openai'."
            )

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        텍스트 리스트를 임베딩 벡터 리스트로 변환.
        반환: [[float, ...], [float, ...], ...]
        각 벡터의 차원: bge-m3=1024, openai=1536
        빈 리스트 입력 시 빈 리스트 반환.
        """
        if not texts:
            return []

        with self._lock:
            with timed(f"embed {len(texts)} texts", logger):
                if self._model_type == "local":
                    encode_batch = int(os.getenv("EMBED_ENCODE_BATCH_SIZE", "256"))
                    vectors = self._model.encode(texts, batch_size=encode_batch)
                    return [v.tolist() for v in vectors]
                else:
                    response = self._client.embeddings.create(
                        input=texts,
                        model="text-embedding-3-small",
                    )
                    return [item.embedding for item in response.data]

    def embed_single(self, text: str) -> list[float]:
        """
        단일 텍스트를 임베딩 벡터로 변환.
        embed([text])[0] 을 반환하는 편의 메서드.
        """
        return self.embed([text])[0]

    @property
    def dimension(self) -> int:
        """
        현재 모델의 벡터 차원 반환.
        bge-m3: 1024, openai: 1536
        """
        if self._model_type == "local":
            return 1024
        return 1536
