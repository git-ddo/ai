from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
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


class RepositoryAnalysisError(ValueError):
    """Raised when repository service inputs violate orchestration boundaries."""


class PortfolioSynthesisError(ValueError):
    """Raised when portfolio synthesis inputs violate orchestration boundaries."""


class InterviewQuestionGenerationError(ValueError):
    """Raised when interview generation inputs violate orchestration boundaries."""


class PortfolioStatementGenerationError(ValueError):
    """Raised when statement generation inputs violate orchestration boundaries."""


class InputViolationCode(StrEnum):
    """Stable codes for deterministic input graph and depth validation failures."""

    DUPLICATE_REPOSITORY_ID = "DUPLICATE_REPOSITORY_ID"
    DUPLICATE_REPOSITORY_NAME = "DUPLICATE_REPOSITORY_NAME"
    DUPLICATE_EVIDENCE_ID = "DUPLICATE_EVIDENCE_ID"
    DUPLICATE_CLAIM_ID = "DUPLICATE_CLAIM_ID"
    REPOSITORY_OWNERSHIP_MISMATCH = "REPOSITORY_OWNERSHIP_MISMATCH"
    UNKNOWN_SOURCE_EVIDENCE_REF = "UNKNOWN_SOURCE_EVIDENCE_REF"
    UNKNOWN_RELATED_EVIDENCE_REF = "UNKNOWN_RELATED_EVIDENCE_REF"
    CROSS_REPOSITORY_REF = "CROSS_REPOSITORY_REF"
    REFERENCE_CYCLE = "REFERENCE_CYCLE"
    SNAPSHOT_REQUIRED = "SNAPSHOT_REQUIRED"
    DEPTH_EXCEEDS_REQUESTED = "DEPTH_EXCEEDS_REQUESTED"
    COMPLETED_LEVELS_INVALID = "COMPLETED_LEVELS_INVALID"
    EVIDENCE_TYPE_DEPTH_MISMATCH = "EVIDENCE_TYPE_DEPTH_MISMATCH"
    EVIDENCE_DEPTH_NOT_COMPLETED = "EVIDENCE_DEPTH_NOT_COMPLETED"
    P2_METADATA_INVALID = "P2_METADATA_INVALID"
    P2_SOURCE_INVALID = "P2_SOURCE_INVALID"
    UPWARD_DEPTH_DERIVATION = "UPWARD_DEPTH_DERIVATION"


@dataclass(frozen=True, slots=True)
class InputViolation:
    """One non-sensitive input invariant violation."""

    code: InputViolationCode
    message: str
    field_path: str | None = None

    def __post_init__(self) -> None:
        normalized_message = self.message.strip()
        if not normalized_message:
            raise ValueError("Input violation message must not be blank")
        object.__setattr__(self, "message", normalized_message)

        if self.field_path is None:
            return
        normalized_path = self.field_path.strip()
        if not normalized_path:
            raise ValueError("Input violation field_path must not be blank")
        object.__setattr__(self, "field_path", normalized_path)


class InputValidationError(ValueError):
    """Raised when internal analysis input violates graph or depth invariants."""

    def __init__(self, violations: Sequence[InputViolation]) -> None:
        immutable_violations = tuple(violations)
        if not immutable_violations:
            raise ValueError("InputValidationError requires at least one violation")

        self.violations = immutable_violations
        violation_codes = ", ".join(violation.code.value for violation in immutable_violations)
        super().__init__(f"Input validation failed: {violation_codes}")
