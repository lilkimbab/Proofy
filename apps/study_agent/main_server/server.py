"""
Main API server for the study_agent repository.

This server mounts the existing frontend-facing backend agents from sibling
directories and keeps the RAG service behind an HTTP boundary.
"""

from __future__ import annotations

import contextlib
import importlib
import os
import sys
from contextlib import asynccontextmanager
from typing import Any

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(ROOT)

load_dotenv()


def _prepend(*subdirs: str) -> None:
    for subdir in subdirs:
        path = os.path.join(REPO_ROOT, subdir)
        if path not in sys.path:
            sys.path.insert(0, path)


def _purge(*prefixes: str) -> None:
    for key in list(sys.modules):
        if any(key == prefix or key.startswith(prefix + ".") for prefix in prefixes):
            del sys.modules[key]


def _unavailable_app(agent_name: str, error: str) -> FastAPI:
    unavailable = FastAPI(title=f"{agent_name} unavailable")

    @unavailable.get("/{path:path}")
    async def unavailable_get(path: str) -> dict[str, str]:
        raise HTTPException(status_code=503, detail={"agent": agent_name, "error": error})

    @unavailable.post("/{path:path}")
    async def unavailable_post(path: str) -> dict[str, str]:
        raise HTTPException(status_code=503, detail={"agent": agent_name, "error": error})

    return unavailable


_agent_load_status: dict[str, dict[str, Any]] = {}


def _load_agent_app(agent_name: str, path: str, module_name: str, *purge_prefixes: str) -> FastAPI:
    _prepend(path)
    _purge(*purge_prefixes)
    try:
        module = importlib.import_module(module_name)
        loaded_app = getattr(module, "app")
        _agent_load_status[agent_name] = {"name": agent_name, "configured": True, "ok": True}
        return loaded_app
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        _agent_load_status[agent_name] = {
            "name": agent_name,
            "configured": True,
            "ok": False,
            "error": error,
        }
        return _unavailable_app(agent_name, error)


_document_app = _load_agent_app("document_agent", "document_agent", "api.main", "api", "core")
_roadmap_app = _load_agent_app("roadmap_agent", "roadmap_agent", "api.main", "api", "core")
_problem_app = _load_agent_app("problem_agent", "problem_agent", "app.main", "app")
_tutor_app = _load_agent_app("tutor_agent", "tutor_agent", "app.main", "app")

_sub_apps = [_document_app, _roadmap_app, _problem_app, _tutor_app]


def _rag_server_url() -> str:
    return os.getenv("RAG_SERVER_URL", "http://127.0.0.1:8001").rstrip("/")


async def _check_url(name: str, url: str, timeout: float = 5.0) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
        return {
            "name": name,
            "configured": True,
            "ok": response.status_code < 500,
            "status_code": response.status_code,
        }
    except Exception as exc:
        return {
            "name": name,
            "configured": True,
            "ok": False,
            "error": str(exc),
        }


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with contextlib.AsyncExitStack() as stack:
        for sub_app in _sub_apps:
            context = getattr(getattr(sub_app, "router", None), "lifespan_context", None)
            if context is not None:
                await stack.enter_async_context(context(sub_app))
        yield


app = FastAPI(
    title="Study Agent Main API",
    description="Frontend-facing API and learning-agent orchestration server.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "main_server"}


@app.get("/api/agents/status")
async def agent_status() -> dict[str, list[dict[str, Any]]]:
    rag_url = _rag_server_url()
    agents = [
        {"name": "main_server", "configured": True, "ok": True},
        await _check_url("rag_server", f"{rag_url}/health"),
        _agent_load_status.get("document_agent", {"name": "document_agent", "configured": False, "ok": False}),
        _agent_load_status.get("roadmap_agent", {"name": "roadmap_agent", "configured": False, "ok": False}),
        _agent_load_status.get("problem_agent", {"name": "problem_agent", "configured": False, "ok": False}),
        _agent_load_status.get("tutor_agent", {"name": "tutor_agent", "configured": False, "ok": False}),
    ]
    return {"agents": agents}


app.mount("/api/document", _document_app)
app.mount("/api/roadmap", _roadmap_app)
app.mount("/api/problem", _problem_app)
app.mount("/api/tutor", _tutor_app)


def main() -> None:
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
