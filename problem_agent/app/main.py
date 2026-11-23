from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.api import include_problem_feedback_routers
from app.config import get_settings
from app.db import create_db_and_tables


def create_app(*, auto_create_tables: bool | None = None) -> FastAPI:
    settings = get_settings()
    should_create_tables = settings.auto_create_tables if auto_create_tables is None else auto_create_tables

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if should_create_tables:
            create_db_and_tables()
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    include_problem_feedback_routers(app)
    return app


app = create_app()
