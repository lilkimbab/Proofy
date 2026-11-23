from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str
    title: str
    top_k: int | None = Field(default=None, ge=1, le=20)
    filter: dict | None = None
    user_id: str | None = None


class BaseResult(BaseModel):
    text: str
    source: str
    page: int
    score: float
    image: str | None = None  # base64 PNG 또는 None (텍스트 전용 페이지)
    id: str | None = None
    chunk_index: int | None = None
    content_hash: str | None = None
    heading_path: list[str] | None = None
    source_type: str | None = None
    parent_id: str | None = None


class SearchResult(BaseResult):
    text: str | None = Field(default=None, exclude=True)  # parent_text에 포함됨, 직렬화 제외
    pipeline: list[str] | None = None
    parent_text: str | None = None  # LLM 컨텍스트용 확장 텍스트 (child가 속한 섹션 전체)


class FeedbackRequest(BaseModel):
    user_id: str
    title: str
    chunk_id: str
    kind: str = "useful"  # "view" | "useful"


class FeedbackResponse(BaseModel):
    status: str


class ReloadResponse(BaseModel):
    status: str
    config: dict


class SearchResponse(BaseModel):
    results: list[SearchResult]


class ParseParent(BaseModel):
    parent_id: str
    text: str
    source: str
    page_start: int
    page_end: int
    heading_path: list[str] | None = None
    source_type: str | None = None
    image: str | None = None  # base64 PNG (페이지에 시각 요소가 있는 경우)


class AddAcceptedResponse(BaseModel):
    """POST /add 의 응답. parse는 동기, embed·저장은 백그라운드에서 진행되며 job_id 로 진행 상태를 조회한다."""
    status: str   # "accepted"
    job_id: str
    title: str
    file_name: str
    parents: list[ParseParent]


class JobStatusResponse(BaseModel):
    """GET /jobs/{job_id} 의 응답."""
    job_id: str
    status: str           # "pending" | "running" | "done" | "failed"
    title: str | None = None
    file_name: str | None = None
    chunks_added: int = 0
    batch: int = 0
    total_batches: int = 0
    error: str | None = None


class TitlesResponse(BaseModel):
    titles: list[str]


class FilesResponse(BaseModel):
    title: str
    files: list[str]


class StatusResponse(BaseModel):
    status: str


class FetchRequest(BaseModel):
    title: str
    filter: dict
    limit: int = Field(default=1000, ge=1, le=10000)


class FetchResult(BaseResult):
    score: float = 0.0


class FetchResponse(BaseModel):
    results: list[FetchResult]
    count: int


