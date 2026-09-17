"""Search provider abstraction.

Every search/retrieval source implements this interface. The rest of the
pipeline (orchestrator, normalizer, ranker, ...) depends only on
`SearchProvider` and `RawSearchResult` — never on a provider's raw HTTP
response format. This is what allows a new provider to be added without
touching the core pipeline: implement `SearchProvider`, register it in
`app/providers/__init__.py`'s provider registry (wired in
`retrieval/orchestrator.py`), done.

Design note: providers are intentionally synchronous-callable-but-async
(`async def search`) using `httpx.AsyncClient` so the orchestrator can run
multiple providers concurrently with bounded parallelism.

ProviderHealth model lives in app.models.status and is used by the
health-check / status endpoint to report per-provider configuration state
and circuit breaker status.
"""
from __future__ import annotations

import abc
from typing import List

from app.models.search import RawSearchResult


class SearchProvider(abc.ABC):
    """Abstract base class for a search/retrieval provider."""

    #: Short, stable identifier used in logs, trace output, and result provenance.
    name: str

    @abc.abstractmethod
    async def search(self, query: str, max_results: int) -> List[RawSearchResult]:
        """Execute a search and return normalized-but-not-yet-deduplicated results.

        Implementations must:
          * respect the given timeout (configured per-provider)
          * raise `app.models.errors.ProviderError` on failure, with
            `retryable` set appropriately (True for timeouts/5xx/connection
            errors, False for auth failures / bad requests)
          * never raise a bare/unstructured exception for expected failure
            modes (the reliability layer wraps this call with retries, but
            it needs a typed error to decide whether retrying makes sense)
        """
        raise NotImplementedError

    async def health_check(self) -> bool:
        """Optional lightweight health check. Default: assume healthy.

        Providers that support a cheap health endpoint can override this;
        it is used by GET /health to report provider configuration status
        without making an expensive real search call.

        Returns True if the provider is configured and reachable, False
        otherwise. Implementations should check for required credentials
        or configuration and return False immediately if missing.
        """
        return True
