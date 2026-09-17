"""FastAPI application entrypoint.

Wires configuration, providers, the LLM client, and the research pipeline
into `app.state` at startup so route handlers stay thin (see
app/api/routes/research.py). Also configures structured logging, CORS,
request-size limiting, and request-ID correlation middleware.
"""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import health, providers, research
from app.config import get_settings
from app.observability.logging import configure_logging, set_request_id
from app.orchestration.research_pipeline import ResearchPipeline
from app.providers.brave_provider import BraveProvider
from app.providers.base import SearchProvider
from app.providers.duckduckgo_provider import DuckDuckGoProvider
from app.providers.tavily_provider import TavilyProvider
from app.reliability.circuit_breaker import CircuitBreakerRegistry
from app.synthesis.llm_client import build_llm_client

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("research_agent.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    provs = _build_providers()
    llm_client = build_llm_client(
        provider=settings.llm_provider,
        model=settings.llm_model,
        groq_api_key=settings.groq_api_key,
        gemini_api_key=settings.gemini_api_key,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    breaker_registry = CircuitBreakerRegistry(
        failure_threshold=settings.circuit_breaker_failure_threshold,
        reset_seconds=settings.circuit_breaker_reset_seconds,
    )
    app.state.pipeline = ResearchPipeline(settings, provs, llm_client, breaker_registry)
    app.state.providers = provs
    app.state.breaker_registry = breaker_registry
    logger.info(
        "application_startup",
        extra={
            "providers": [p.name for p in provs],
            "llm_provider": settings.llm_provider,
            "environment": settings.app_env,
        },
    )
    yield


app = FastAPI(
    title="Multi-Source Web Research Agent",
    description="Evidence-grounded research API backed by multiple search providers.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """Assigns a request ID for log correlation and enforces a max body size."""
    request_id = str(uuid.uuid4())
    set_request_id(request_id)

    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.max_request_body_bytes:
        return JSONResponse(
            status_code=413,
            content={"error_code": "validation_error", "message": "Request body too large."},
        )

    start = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000
    response.headers[settings.request_id_header] = request_id
    logger.info(
        "http_request_completed",
        extra={
            "path": request.url.path,
            "method": request.method,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 1),
            "request_id": request_id,
        },
    )
    return response


def _build_providers() -> list[SearchProvider]:
    provs: list[SearchProvider] = []
    if settings.ddg_enabled:
        provs.append(DuckDuckGoProvider(timeout_seconds=settings.ddg_timeout_seconds))
    if settings.tavily_enabled:
        provs.append(TavilyProvider(api_key=settings.tavily_api_key, timeout_seconds=settings.tavily_timeout_seconds))
    if settings.brave_enabled:
        provs.append(BraveProvider(api_key=settings.brave_api_key, timeout_seconds=settings.brave_timeout_seconds))
    return provs


app.include_router(health.router)
app.include_router(providers.router)
app.include_router(research.router)
