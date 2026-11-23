from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}


def validate_auto_create_tables_allowed(database_url: str) -> None:
    if database_url.startswith("sqlite"):
        return
    raise RuntimeError(
        "AUTO_CREATE_TABLES is only allowed for local SQLite demo databases. "
        "Use the integrated service migration flow for PostgreSQL."
    )


settings = get_settings()
engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


async def get_db() -> AsyncGenerator[Session, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_db_and_tables() -> None:
    validate_auto_create_tables_allowed(settings.database_url)
    # Import models before create_all so SQLAlchemy registers metadata.
    import app.models.entities  # noqa: F401

    Base.metadata.create_all(bind=engine)
