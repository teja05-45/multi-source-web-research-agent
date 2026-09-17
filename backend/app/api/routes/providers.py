"""Provider status endpoint.

Exposes GET /api/providers/status with per-provider configuration and
circuit breaker state. Used by the frontend (and operational dashboards)
to display which search backends are enabled and healthy.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/providers/status")
async def provider_status(request: Request) -> dict:
    providers = getattr(request.app.state, "providers", [])
    breaker_registry = getattr(request.app.state, "breaker_registry", None)

    status_list = []
    for p in providers:
        entry: dict = {
            "name": p.name,
            "configured": True,
            "enabled": True,
        }
        if breaker_registry:
            cb = breaker_registry.get(p.name)
            if cb is not None:
                entry["circuit_breaker_state"] = cb.state.value
                entry["circuit_breaker_failure_count"] = cb._failure_count
        status_list.append(entry)

    return {"providers": status_list}
