from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.validators.report_validator import PolicyViolation


class LLMProviderError(Exception):
    """Base error exposed by an LLM provider implementation."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        attempt_count: int = 0,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.attempt_count = attempt_count
        self.status_code = status_code


class LLMConfigurationError(LLMProviderError):
    """Raised when a provider cannot be configured safely."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


class LLMRateLimitError(LLMProviderError):
    """Raised when the upstream provider rejects a request due to rate limiting."""


class LLMTimeoutError(LLMProviderError):
    """Raised when an upstream generation attempt exceeds its deadline."""


class LLMServiceError(LLMProviderError):
    """Raised when the upstream provider returns a service or request error."""


class LLMStructuredOutputError(LLMProviderError):
    """Raised when an upstream response cannot be validated as the requested model."""

    def __init__(self, message: str, *, attempt_count: int = 1) -> None:
        super().__init__(message, retryable=False, attempt_count=attempt_count)


class ReportPolicyError(Exception):
    """Raised when an internal report violates one or more fixed policies."""

    def __init__(self, violations: Sequence["PolicyViolation"]) -> None:
        immutable_violations = tuple(violations)
        if not immutable_violations:
            raise ValueError("ReportPolicyError requires at least one violation")

        self.violations = immutable_violations
        violation_codes = ", ".join(violation.code.value for violation in immutable_violations)
        super().__init__(f"Report policy validation failed: {violation_codes}")
