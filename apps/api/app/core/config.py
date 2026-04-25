from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class Settings:
    storage_backend: str = os.getenv("APP_STORAGE_BACKEND", "memory")
    database_url: str = os.getenv(
        "APP_DATABASE_URL",
        "postgresql://proofy:proofy@localhost:5432/proofy",
    )
    allowed_origins: list[str] = tuple(
        value.strip()
        for value in os.getenv("APP_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
        if value.strip()
    )
    allowed_origin_regex: str = os.getenv(
        "APP_ALLOWED_ORIGIN_REGEX",
        r"^https?://(localhost|127(?:\.\d{1,3}){1,3})(:\d+)?$",
    )
    demo_user_id: str = os.getenv("APP_DEMO_USER_ID", "demo-user")
    content_generation_api_url: str = os.getenv(
        "APP_CONTENT_GENERATION_API_URL",
        "",
    )
    content_generation_api_key: str = os.getenv(
        "APP_CONTENT_GENERATION_API_KEY",
        "",
    )
    content_generation_provider: str = os.getenv(
        "APP_CONTENT_GENERATION_PROVIDER",
        "gemini" if os.getenv("APP_GEMINI_API_KEY") else "generic",
    )
    content_generation_model: str = os.getenv(
        "APP_CONTENT_GENERATION_MODEL",
        os.getenv("APP_GEMINI_MODEL", "gemini-2.5-flash"),
    )
    gemini_api_key: str = os.getenv("APP_GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("APP_GEMINI_MODEL", "gemini-2.5-flash")
    llm_provider: str = os.getenv(
        "APP_LLM_PROVIDER",
        "gemini" if os.getenv("APP_GEMINI_API_KEY") else "generic",
    )
    llm_api_url: str = os.getenv("APP_LLM_API_URL", "")
    llm_api_key: str = os.getenv("APP_LLM_API_KEY", "")
    llm_model: str = os.getenv("APP_LLM_MODEL", "gpt-4.1-mini")
    llm_timeout_seconds: int = int(os.getenv("APP_LLM_TIMEOUT_SECONDS", "20"))


settings = Settings()
