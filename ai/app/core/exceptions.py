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
