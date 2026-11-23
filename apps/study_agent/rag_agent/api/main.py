import sys
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI


def _configure_vdb_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    vdb_logger = logging.getLogger("vector_db")
    vdb_logger.setLevel(logging.DEBUG)
    vdb_logger.addHandler(handler)
    vdb_logger.propagate = False


_configure_vdb_logging()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from vector_db import VectorDBManager
from api.routes import router

db: VectorDBManager | None = None

# 비동기 인제스트 작업 상태 레지스트리
# {"job_id": {"status": "pending|running|done|failed", "title": str, "file_name": str,
#             "chunks_added": int, "batch": int, "total_batches": int, "error": str|None}}
# ⚠️ in-memory — 서버 재시작 시 소실. 멀티 워커 환경에서는 공유되지 않음.
job_registry: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db
    db = VectorDBManager()
    app.state.db = db
    app.state.job_registry = job_registry
    yield
    app.state.db = None
    db = None


app = FastAPI(
    title="Retrieval Service API",
    description="Vector DB 기반 문서 검색 서비스. 외부 에이전트에 검색 결과를 전달한다.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)
