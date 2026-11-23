import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_doc_agent_dir = os.path.dirname(_this_dir)  # document_agent/

sys.path.insert(0, _doc_agent_dir)  # core.*, api.* 임포트용

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

from api.routes import router
from core.manager import StudyManager

manager: StudyManager | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global manager
    manager = StudyManager()
    app.state.manager = manager
    yield
    app.state.manager = None
    manager = None


app = FastAPI(
    title="Document Agent API",
    description="rag_agent 기반 RAG-grounded 교육 자료 생성 서비스",
    version="2.0.0",
    lifespan=lifespan,
)
app.include_router(router)
