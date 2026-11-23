import pytest

import app.db as db_module
from app.db import validate_auto_create_tables_allowed


def test_auto_create_tables_is_allowed_for_local_sqlite_demo():
    validate_auto_create_tables_allowed("sqlite+pysqlite:///./study_agent_free.db")
    validate_auto_create_tables_allowed("sqlite+pysqlite://")


def test_auto_create_tables_is_rejected_for_postgres():
    with pytest.raises(RuntimeError, match="AUTO_CREATE_TABLES is only allowed"):
        validate_auto_create_tables_allowed(
            "postgresql+psycopg://postgres:postgres@localhost:5432/study_agent"
        )


def test_create_db_and_tables_refuses_postgres_startup(monkeypatch):
    monkeypatch.setattr(
        db_module,
        "settings",
        type("Settings", (), {"database_url": "postgresql+psycopg://postgres:postgres@localhost/db"})(),
    )

    with pytest.raises(RuntimeError, match="migration flow"):
        db_module.create_db_and_tables()


def test_create_db_and_tables_allows_sqlite_demo(monkeypatch):
    calls = []

    def fake_create_all(*, bind):
        calls.append(bind)

    fake_engine = object()
    monkeypatch.setattr(
        db_module,
        "settings",
        type("Settings", (), {"database_url": "sqlite+pysqlite:///./demo.db"})(),
    )
    monkeypatch.setattr(db_module, "engine", fake_engine)
    monkeypatch.setattr(db_module.Base.metadata, "create_all", fake_create_all)

    db_module.create_db_and_tables()

    assert calls == [fake_engine]
