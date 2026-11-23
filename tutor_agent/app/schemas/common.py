from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


AgentType = Literal["tutor", "problem", "feedback", "roadmap"]
Level = Literal["beginner", "intermediate", "advanced"]
Mode = Literal["fast", "balanced", "deep"]


class AgentOptions(BaseModel):
    level: Level | None = None
    mode: Mode = "balanced"
    language: str = "ko"
    include_sources: bool = True
    save_result: bool = False


class AgentRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: f"req_{uuid4().hex}")
    user_id: str = "guest"
    agent_type: AgentType = "tutor"
    request_type: str = "tutor.answer"
    document_id: str | None = None
    section_id: str | None = None
    selected_text: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    options: AgentOptions = Field(default_factory=AgentOptions)


class AgentTrace(BaseModel):
    request_id: str
    agent: str
    version: str
    steps: list[str] = Field(default_factory=list)
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None
    error: str | None = None


class GuardResult(BaseModel):
    allowed: bool
    reason: str
    message: str | None = None


class Source(BaseModel):
    chunk_id: str | None = None
    section_id: str | None = None
    title: str | None = None
    index: int | None = None
    quote: str | None = None
    score: float = 0


class AgentContext(BaseModel):
    user_model: dict[str, Any] = Field(default_factory=dict)
    document: dict[str, Any] = Field(default_factory=dict)
    retrieved_chunks: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    history: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    ok: bool
    agent_type: str
    mode: str
    answer: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    sources: list[Source] = Field(default_factory=list)
    annotations: list[dict[str, Any]] = Field(default_factory=list)
    next_actions: list[dict[str, Any]] = Field(default_factory=list)
    guard: GuardResult | None = None
    trace: AgentTrace

