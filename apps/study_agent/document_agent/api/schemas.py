from __future__ import annotations

from pydantic import BaseModel, Field


class TaskStatusSchema(BaseModel):
    task_id: str
    doc_id: str
    status: str
    progress: float = Field(ge=0.0, le=1.0)
    message: str
    error: str | None = None
    created_at: str
    completed_at: str | None = None


class SourceSchema(BaseModel):
    file: str
    page: int
    chunk_id: str


class ChunkTextSchema(BaseModel):
    chunk_id: str
    text: str
    file: str
    page: int


class FlashcardSchema(BaseModel):
    question: str
    answer_hint: str
    answer: str = ""


class ExecSummarySchema(BaseModel):
    key_topics: list[str] = []
    learning_objectives: list[str] = []
    conceptual_flow: str = ""


class SectionSchema(BaseModel):
    title: str
    intent: str
    content: str
    focus: str
    source_chunks: list[ChunkTextSchema]
    grounding_issues: list[str] = []
    flashcards: list[FlashcardSchema] = []


class LearningFlowItem(BaseModel):
    step: int
    title: str
    intent: str
    focus: str


class StudyMaterialSchema(BaseModel):
    doc_id: str
    query: str
    title: str
    document: str
    exec_summary: ExecSummarySchema = Field(default_factory=ExecSummarySchema)
    learning_flow: list[LearningFlowItem] = []
    sections: list[SectionSchema] = []
    sources: list[SourceSchema]
    warnings: list[str]
    generated_at: str


class UploadResponse(BaseModel):
    task_id: str
    doc_id: str
    job_id: str


class FeedbackRequest(BaseModel):
    user_id: str
    title: str
    chunk_id: str


class FeedbackResponse(BaseModel):
    status: str
