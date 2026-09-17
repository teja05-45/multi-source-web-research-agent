"""Domain-level exceptions and error codes.

These are distinct from HTTP exceptions. The API layer translates these into
appropriate HTTP responses with safe, user-facing messages (see
app/api/routes/research.py). Internal detail is preserved in logs only.
"""
from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "validation_error"
    PROVIDER_ERROR = "provider_error"
    ALL_PROVIDERS_FAILED = "all_providers_failed"
    FETCH_ERROR = "fetch_error"
    LLM_ERROR = "llm_error"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    INTERNAL_ERROR = "internal_error"


class ResearchAgentError(Exception):
    """Base class for all domain errors raised by the research pipeline."""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationError(ResearchAgentError):
    code = ErrorCode.VALIDATION_ERROR


class ProviderError(ResearchAgentError):
    """A single provider failed. Not necessarily fatal to the request."""

    code = ErrorCode.PROVIDER_ERROR

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        retryable: bool,
        status_code: int | None = None,
        details: dict | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.provider = provider
        self.retryable = retryable
        self.status_code = status_code


class AllProvidersFailedError(ResearchAgentError):
    code = ErrorCode.ALL_PROVIDERS_FAILED


class FetchError(ResearchAgentError):
    code = ErrorCode.FETCH_ERROR


class LLMError(ResearchAgentError):
    code = ErrorCode.LLM_ERROR


class InsufficientEvidenceError(ResearchAgentError):
    code = ErrorCode.INSUFFICIENT_EVIDENCE
