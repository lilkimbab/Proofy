from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    PostgreSQL is the production default because the wider service is expected
    to use pgvector. Tests override this with an in-memory SQLite database.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Study Agent Problem Feedback"
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/study_agent",
        alias="DATABASE_URL",
    )
    search_agent_url: str | None = Field(default=None, alias="SEARCH_AGENT_URL")
    search_agent_api_key: str | None = Field(default=None, alias="SEARCH_AGENT_API_KEY")
    search_agent_api_key_header: str = Field(default="X-API-Key", alias="SEARCH_AGENT_API_KEY_HEADER")
    search_agent_timeout_seconds: float = Field(default=20.0, alias="SEARCH_AGENT_TIMEOUT_SECONDS", ge=1.0, le=120.0)
    rag_agent_url: str | None = Field(default=None, alias="RAG_AGENT_URL")
    rag_agent_search_path: str = Field(default="/search", alias="RAG_AGENT_SEARCH_PATH")
    rag_agent_chunks_path: str | None = Field(default=None, alias="RAG_AGENT_CHUNKS_PATH")
    rag_agent_fetch_path: str | None = Field(default="/fetch", alias="RAG_AGENT_FETCH_PATH")
    rag_agent_text_only: bool = Field(default=True, alias="RAG_AGENT_TEXT_ONLY")
    rag_agent_skip_ngrok_warning: bool = Field(default=False, alias="RAG_AGENT_SKIP_NGROK_WARNING")
    rag_agent_preserve_image_payloads: bool = Field(default=False, alias="RAG_AGENT_PRESERVE_IMAGE_PAYLOADS")
    demo_search_enabled: bool = Field(default=False, alias="DEMO_SEARCH_ENABLED")
    generated_artifact_index_url: str | None = Field(default=None, alias="GENERATED_ARTIFACT_INDEX_URL")
    generated_artifact_add_url: str | None = Field(default=None, alias="GENERATED_ARTIFACT_ADD_URL")
    generated_artifact_add_title_prefix: str = Field(
        default="generated_artifact",
        alias="GENERATED_ARTIFACT_ADD_TITLE_PREFIX",
    )
    generated_problem_rag_upload_enabled: bool = Field(
        default=True,
        alias="GENERATED_PROBLEM_RAG_UPLOAD_ENABLED",
    )
    generated_problem_rag_add_path: str = Field(default="/add", alias="GENERATED_PROBLEM_RAG_ADD_PATH")
    generated_artifact_publish_enabled: bool = Field(default=False, alias="GENERATED_ARTIFACT_PUBLISH_ENABLED")
    generated_artifact_publish_fail_fast: bool = Field(default=False, alias="GENERATED_ARTIFACT_PUBLISH_FAIL_FAST")
    generated_artifact_api_key: str | None = Field(default=None, alias="GENERATED_ARTIFACT_API_KEY")
    generated_artifact_api_key_header: str = Field(default="X-API-Key", alias="GENERATED_ARTIFACT_API_KEY_HEADER")
    generated_artifact_timeout_seconds: float = Field(
        default=3.0,
        alias="GENERATED_ARTIFACT_TIMEOUT_SECONDS",
        ge=0.2,
        le=30.0,
    )
    generated_artifact_publish_concurrency: int = Field(
        default=4,
        alias="GENERATED_ARTIFACT_PUBLISH_CONCURRENCY",
        ge=1,
        le=16,
    )
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_openai_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai/",
        alias="GEMINI_OPENAI_BASE_URL",
    )
    llm_fallback_enabled: bool = Field(default=False, alias="LLM_FALLBACK_ENABLED")
    auto_create_tables: bool = Field(default=False, alias="AUTO_CREATE_TABLES")

    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")
    problem_model: str = Field(default="gpt-5.4-mini", alias="PROBLEM_MODEL")
    problem_quality_model: str = Field(default="gpt-5.5", alias="PROBLEM_QUALITY_MODEL")
    problem_agent_cost_profile: str = Field(
        default="balanced",
        alias="PROBLEM_AGENT_COST_PROFILE",
        pattern="^(cheap|balanced|full)$",
    )
    problem_agent_allow_premium_escalation: bool = Field(
        default=False,
        alias="PROBLEM_AGENT_ALLOW_PREMIUM_ESCALATION",
    )
    problem_agent_prompt_compression_enabled: bool = Field(
        default=True,
        alias="PROBLEM_AGENT_PROMPT_COMPRESSION_ENABLED",
    )
    problem_agent_evidence_pack_max_atoms: int = Field(
        default=6,
        alias="PROBLEM_AGENT_EVIDENCE_PACK_MAX_ATOMS",
        ge=1,
        le=20,
    )
    problem_agent_evidence_pack_max_quote_chars: int = Field(
        default=420,
        alias="PROBLEM_AGENT_EVIDENCE_PACK_MAX_QUOTE_CHARS",
        ge=80,
        le=2000,
    )
    problem_agent_context_raw_chunk_max_chars: int = Field(
        default=700,
        alias="PROBLEM_AGENT_CONTEXT_RAW_CHUNK_MAX_CHARS",
        ge=120,
        le=3000,
    )
    problem_agent_include_mcq_fewshots_in_cheap: bool = Field(
        default=False,
        alias="PROBLEM_AGENT_INCLUDE_MCQ_FEWSHOTS_IN_CHEAP",
    )
    problem_agent_live_eval_rejected_candidate_export_mode: str = Field(
        default="redacted",
        alias="PROBLEM_AGENT_LIVE_EVAL_REJECTED_CANDIDATE_EXPORT_MODE",
        pattern="^(redacted|full)$",
    )
    problem_agent_generation_strategy: str | None = Field(
        default=None,
        alias="PROBLEM_AGENT_GENERATION_STRATEGY",
        pattern="^(batch_candidates|single_then_repair)$",
    )
    learning_content_model: str = Field(default="gpt-5.4-mini", alias="LEARNING_CONTENT_MODEL")
    learning_content_quality_model: str = Field(default="gpt-5.5", alias="LEARNING_CONTENT_QUALITY_MODEL")
    feedback_model: str = Field(default="gpt-5.4-nano", alias="FEEDBACK_MODEL")
    grading_model: str = Field(default="gpt-5.4-mini", alias="GRADING_MODEL")
    grading_quality_model: str = Field(default="gpt-5.5", alias="GRADING_QUALITY_MODEL")
    multiple_choice_feedback_llm_enabled: bool = Field(
        default=False,
        alias="MULTIPLE_CHOICE_FEEDBACK_LLM_ENABLED",
    )
    llm_chunk_char_limit: int = Field(default=1800, alias="LLM_CHUNK_CHAR_LIMIT", ge=300, le=6000)
    llm_max_output_tokens_problem: int = Field(default=2500, alias="LLM_MAX_OUTPUT_TOKENS_PROBLEM", ge=256, le=10000)
    llm_max_output_tokens_learning_content: int = Field(
        default=1800,
        alias="LLM_MAX_OUTPUT_TOKENS_LEARNING_CONTENT",
        ge=256,
        le=8000,
    )
    llm_max_output_tokens_feedback: int = Field(default=900, alias="LLM_MAX_OUTPUT_TOKENS_FEEDBACK", ge=128, le=4000)
    llm_reasoning_effort_problem: str = Field(default="low", alias="LLM_REASONING_EFFORT_PROBLEM")
    llm_reasoning_effort_problem_quality: str = Field(default="medium", alias="LLM_REASONING_EFFORT_PROBLEM_QUALITY")
    llm_reasoning_effort_learning_content: str = Field(default="low", alias="LLM_REASONING_EFFORT_LEARNING_CONTENT")
    llm_reasoning_effort_feedback: str = Field(default="low", alias="LLM_REASONING_EFFORT_FEEDBACK")
    llm_gemini_high_rigor_candidate_multiplier: int = Field(
        default=1,
        alias="LLM_GEMINI_HIGH_RIGOR_CANDIDATE_MULTIPLIER",
        ge=1,
        le=5,
    )
    problem_agent_high_rigor_mcq_min_candidates: int = Field(
        default=3,
        alias="PROBLEM_AGENT_HIGH_RIGOR_MCQ_MIN_CANDIDATES",
        ge=1,
        le=10,
    )
    problem_agent_high_rigor_mcq_retry_count: int = Field(
        default=2,
        alias="PROBLEM_AGENT_HIGH_RIGOR_MCQ_RETRY_COUNT",
        ge=0,
        le=4,
    )
    problem_agent_search_query_mode: str = Field(
        default="compact",
        alias="PROBLEM_AGENT_SEARCH_QUERY_MODE",
        pattern="^(compact|expanded|hybrid)$",
    )
    problem_agent_generation_context_packing_enabled: bool = Field(
        default=True,
        alias="PROBLEM_AGENT_GENERATION_CONTEXT_PACKING_ENABLED",
    )
    problem_agent_generation_context_max_chunks: int = Field(
        default=8,
        alias="PROBLEM_AGENT_GENERATION_CONTEXT_MAX_CHUNKS",
        ge=1,
        le=30,
    )
    problem_agent_generation_context_min_chunks: int = Field(
        default=3,
        alias="PROBLEM_AGENT_GENERATION_CONTEXT_MIN_CHUNKS",
        ge=1,
        le=30,
    )
    problem_agent_answer_verification_enabled: bool = Field(
        default=False,
        alias="PROBLEM_AGENT_ANSWER_VERIFICATION_ENABLED",
    )
    problem_agent_answer_verification_llm_enabled: bool = Field(
        default=False,
        alias="PROBLEM_AGENT_ANSWER_VERIFICATION_LLM_ENABLED",
    )
    problem_agent_answer_verification_model: str | None = Field(
        default=None,
        alias="PROBLEM_AGENT_ANSWER_VERIFICATION_MODEL",
    )
    problem_agent_use_domain_general_kernels: bool = Field(
        default=True,
        alias="PROBLEM_AGENT_USE_DOMAIN_GENERAL_KERNELS",
    )
    problem_agent_allow_standard_fallback_on_kernel_failure: bool = Field(
        default=False,
        alias="PROBLEM_AGENT_ALLOW_STANDARD_FALLBACK_ON_KERNEL_FAILURE",
    )
    openai_timeout_seconds: float = Field(default=30.0, alias="OPENAI_TIMEOUT_SECONDS", ge=1.0, le=120.0)
    openai_max_retries: int = Field(default=1, alias="OPENAI_MAX_RETRIES", ge=0, le=5)
    llm_standard_input_price_krw_per_1m_tokens: float = Field(
        default=0.0,
        alias="LLM_STANDARD_INPUT_PRICE_KRW_PER_1M_TOKENS",
        ge=0,
    )
    llm_standard_output_price_krw_per_1m_tokens: float = Field(
        default=0.0,
        alias="LLM_STANDARD_OUTPUT_PRICE_KRW_PER_1M_TOKENS",
        ge=0,
    )
    llm_premium_input_price_krw_per_1m_tokens: float = Field(
        default=0.0,
        alias="LLM_PREMIUM_INPUT_PRICE_KRW_PER_1M_TOKENS",
        ge=0,
    )
    llm_premium_output_price_krw_per_1m_tokens: float = Field(
        default=0.0,
        alias="LLM_PREMIUM_OUTPUT_PRICE_KRW_PER_1M_TOKENS",
        ge=0,
    )
    llm_monthly_user_budget_krw: float = Field(default=0.0, alias="LLM_MONTHLY_USER_BUDGET_KRW", ge=0)
    llm_budget_warning_ratio: float = Field(default=0.8, alias="LLM_BUDGET_WARNING_RATIO", ge=0, le=1)
    llm_enforce_monthly_budget: bool = Field(default=False, alias="LLM_ENFORCE_MONTHLY_BUDGET")
    problem_generation_monthly_limit: int = Field(default=0, alias="PROBLEM_GENERATION_MONTHLY_LIMIT", ge=0)
    problem_generation_high_rigor_monthly_limit: int = Field(
        default=0,
        alias="PROBLEM_GENERATION_HIGH_RIGOR_MONTHLY_LIMIT",
        ge=0,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
