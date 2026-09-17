"""
Application configuration.

All configuration is sourced from environment variables (optionally loaded
from a local .env file via python-dotenv during development). No secrets are
ever hardcoded. See .env.example at the repository root for the full list of
supported variables and their meaning.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load a local .env file if present. In production, real environment
# variables (set by the deployment platform) take precedence and this is a
# no-op if no .env file exists.
load_dotenv(override=False)


class Settings(BaseSettings):
    """Central, typed configuration object for the whole backend."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Application ---------------------------------------------------
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    request_id_header: str = Field(default="X-Request-ID", alias="REQUEST_ID_HEADER")

    # --- Database --------------------------------------------------------
    database_url: str = Field(
        default="sqlite+aiosqlite:///./researchlens.db",
        alias="DATABASE_URL",
        description="Database connection URL (sqlite+aiosqlite for dev, postgresql+asyncpg for prod)",
    )

    # --- CORS ------------------------------------------------------------
    cors_allowed_origins: str = Field(default="http://localhost:5173", alias="CORS_ALLOWED_ORIGINS")

    # --- LLM provider ------------------------------------------------------
    llm_provider: str = Field(default="mock", alias="LLM_PROVIDER")  # groq | gemini | mock
    llm_model: str = Field(default="mock-model", alias="LLM_MODEL")
    groq_api_key: Optional[str] = Field(default=None, alias="GROQ_API_KEY")
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    llm_timeout_seconds: float = Field(default=30.0, alias="LLM_TIMEOUT_SECONDS")
    llm_max_output_tokens: int = Field(default=2000, alias="LLM_MAX_OUTPUT_TOKENS")

    # --- Search providers ----------------------------------------------
    # Provider A: DuckDuckGo HTML search. No API key required. Used as the
    # always-available baseline provider.
    ddg_enabled: bool = Field(default=True, alias="DDG_ENABLED")
    ddg_timeout_seconds: float = Field(default=8.0, alias="DDG_TIMEOUT_SECONDS")

    # Provider B: Tavily search API. Requires an API key. Optimized for
    # LLM-oriented retrieval with cleaner snippets.
    tavily_enabled: bool = Field(default=True, alias="TAVILY_ENABLED")
    tavily_api_key: Optional[str] = Field(default=None, alias="TAVILY_API_KEY")
    tavily_timeout_seconds: float = Field(default=8.0, alias="TAVILY_TIMEOUT_SECONDS")

    # Provider C: Brave Search API. Requires an API key. Free tier available.
    brave_enabled: bool = Field(default=False, alias="BRAVE_ENABLED")
    brave_api_key: Optional[str] = Field(default=None, alias="BRAVE_API_KEY")
    brave_timeout_seconds: float = Field(default=8.0, alias="BRAVE_TIMEOUT_SECONDS")

    # --- Retrieval / pipeline tuning ------------------------------------
    max_subqueries: int = Field(default=4, alias="MAX_SUBQUERIES")
    max_results_per_provider: int = Field(default=8, alias="MAX_RESULTS_PER_PROVIDER")
    max_sources_to_fetch: int = Field(default=8, alias="MAX_SOURCES_TO_FETCH")
    max_fetch_content_bytes: int = Field(default=300_000, alias="MAX_FETCH_CONTENT_BYTES")
    fetch_timeout_seconds: float = Field(default=10.0, alias="FETCH_TIMEOUT_SECONDS")
    retrieval_concurrency: int = Field(default=4, alias="RETRIEVAL_CONCURRENCY")
    fetch_concurrency: int = Field(default=4, alias="FETCH_CONCURRENCY")

    # --- Reliability -----------------------------------------------------
    provider_max_retries: int = Field(default=2, alias="PROVIDER_MAX_RETRIES")
    provider_backoff_base_seconds: float = Field(default=0.5, alias="PROVIDER_BACKOFF_BASE_SECONDS")
    circuit_breaker_failure_threshold: int = Field(default=3, alias="CIRCUIT_BREAKER_FAILURE_THRESHOLD")
    circuit_breaker_reset_seconds: float = Field(default=30.0, alias="CIRCUIT_BREAKER_RESET_SECONDS")

    # --- Security ----------------------------------------------------------
    max_question_length: int = Field(default=1000, alias="MAX_QUESTION_LENGTH")
    max_request_body_bytes: int = Field(default=20_000, alias="MAX_REQUEST_BODY_BYTES")
    allow_private_network_fetch: bool = Field(default=False, alias="ALLOW_PRIVATE_NETWORK_FETCH")

    @field_validator("llm_provider")
    @classmethod
    def _validate_llm_provider(cls, v: str) -> str:
        allowed = {"groq", "gemini", "mock"}
        if v not in allowed:
            raise ValueError(f"LLM_PROVIDER must be one of {allowed}, got {v!r}")
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (singleton within the process)."""
    return Settings()
