"""GET /health — liveness + provider/LLM configuration status."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings

router = APIRouter()


@router.get("/health")
async def health(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "status": "ok",
        "environment": settings.app_env,
        "providers": {
            "duckduckgo": {"enabled": settings.ddg_enabled, "requires_api_key": False},
            "tavily": {
                "enabled": settings.tavily_enabled,
                "requires_api_key": True,
                "configured": bool(settings.tavily_api_key),
            },
        },
        "llm": {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "configured": settings.llm_provider == "mock"
            or bool(settings.groq_api_key)
            or bool(settings.gemini_api_key),
        },
    }
