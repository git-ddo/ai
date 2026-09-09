from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from fastapi.exceptions import RequestValidationError
from pydantic import JsonValue, ValidationError

from app.core.exceptions import (
    InputValidationError,
    InputViolation,
    LLMConfigurationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMServiceError,
    LLMStructuredOutputError,
    LLMTimeoutError,
    PortfolioReportDeadlineError,
    ReportPolicyError,
    RequestMappingError,
    ResponseMappingError,
    UnsupportedAnalysisCombinationError,
)
from app.schemas.common import AnalysisErrorCode
from app.schemas.error import AnalysisErrorResponse
from app.validators.report_validator import PolicyViolation

_ERROR_MESSAGES: Final[dict[AnalysisErrorCode, str]] = {
    AnalysisErrorCode.INVALID_REQUEST: "요청 형식 또는 분석 입력이 올바르지 않습니다.",
    AnalysisErrorCode.UNSUPPORTED_COMBINATION: "현재 지원하지 않는 분석 조합입니다.",
    AnalysisErrorCode.POLICY_VIOLATION: (
        "생성된 분석 결과가 근거 및 안전 정책을 충족하지 못했습니다."
    ),
    AnalysisErrorCode.LLM_TIMEOUT: "AI 분석 처리 시간이 초과되었습니다.",
    AnalysisErrorCode.LLM_RATE_LIMITED: "AI 서비스 요청 한도에 도달했습니다.",
    AnalysisErrorCode.LLM_SERVICE_ERROR: ("AI 서비스 처리 중 일시적인 오류가 발생했습니다."),
    AnalysisErrorCode.STRUCTURED_OUTPUT_INVALID: (
        "AI 분석 결과를 정해진 형식으로 검증하지 못했습니다."
    ),
    AnalysisErrorCode.INTERNAL_ERROR: "AI 서버 내부 오류가 발생했습니다.",
}


@dataclass(frozen=True, slots=True)
class MappedAnalysisError:
    """HTTP metadata and validated Backend error-envelope body."""

    status_code: int
    body: AnalysisErrorResponse


class ErrorWireMapper:
    """Convert an internal exception into a safe Backend error envelope."""

    def to_wire(
        self,
        error: BaseException,
        *,
        analysis_id: UUID | None,
    ) -> MappedAnalysisError:
        code, status_code, retryable = self._classify(error)
        body = AnalysisErrorResponse(
            schema_version="1.0",
            analysis_id=analysis_id,
            code=code,
            message=_ERROR_MESSAGES[code],
            retryable=retryable,
            details=self._safe_details(error),
        )
        return MappedAnalysisError(status_code=status_code, body=body)

    @staticmethod
    def _classify(error: BaseException) -> tuple[AnalysisErrorCode, int, bool]:
        if isinstance(error, UnsupportedAnalysisCombinationError):
            return AnalysisErrorCode.UNSUPPORTED_COMBINATION, 422, False
        if isinstance(error, ValidationError | RequestValidationError):
            return AnalysisErrorCode.INVALID_REQUEST, 400, False
        if isinstance(error, RequestMappingError | InputValidationError):
            return AnalysisErrorCode.INVALID_REQUEST, 400, False
        if isinstance(error, ReportPolicyError):
            return AnalysisErrorCode.POLICY_VIOLATION, 502, False
        if isinstance(error, LLMConfigurationError):
            return AnalysisErrorCode.INTERNAL_ERROR, 500, False
        if isinstance(error, LLMTimeoutError | PortfolioReportDeadlineError):
            return AnalysisErrorCode.LLM_TIMEOUT, 504, True
        if isinstance(error, LLMRateLimitError):
            return AnalysisErrorCode.LLM_RATE_LIMITED, 503, True
        if isinstance(error, LLMStructuredOutputError):
            return AnalysisErrorCode.STRUCTURED_OUTPUT_INVALID, 502, False
        if isinstance(error, LLMServiceError):
            return AnalysisErrorCode.LLM_SERVICE_ERROR, 502, True
        if isinstance(error, ResponseMappingError | LLMProviderError):
            return AnalysisErrorCode.INTERNAL_ERROR, 500, False
        return AnalysisErrorCode.INTERNAL_ERROR, 500, False

    @classmethod
    def _safe_details(cls, error: BaseException) -> dict[str, JsonValue]:
        if isinstance(error, InputValidationError):
            return cls._violation_details(error.violations)
        if isinstance(error, ReportPolicyError):
            return cls._violation_details(error.violations)
        if isinstance(error, ValidationError | RequestValidationError):
            return cls._validation_details(error)
        if isinstance(error, LLMProviderError):
            return cls._llm_details(error)
        return {}

    @staticmethod
    def _violation_details(
        violations: Sequence[InputViolation | PolicyViolation],
    ) -> dict[str, JsonValue]:
        items: list[JsonValue] = []
        for violation in violations:
            item: dict[str, JsonValue] = {"code": violation.code.value}
            if violation.field_path is not None:
                item["fieldPath"] = violation.field_path
            items.append(item)
        return {"violations": items}

    @classmethod
    def _validation_details(
        cls,
        error: ValidationError | RequestValidationError,
    ) -> dict[str, JsonValue]:
        items: list[JsonValue] = []
        for validation_error in error.errors():
            location = validation_error.get("loc", ())
            field_path = cls._format_location(location)
            error_type = validation_error.get("type", "validation_error")
            items.append(
                {
                    "fieldPath": field_path,
                    "type": str(error_type),
                }
            )
        return {"errors": items}

    @staticmethod
    def _format_location(location: object) -> str:
        if not isinstance(location, list | tuple):
            return "$"
        parts = list(location)
        if parts and parts[0] == "body":
            parts = parts[1:]
        return ".".join(str(part) for part in parts) or "$"

    @staticmethod
    def _llm_details(error: LLMProviderError) -> dict[str, JsonValue]:
        details: dict[str, JsonValue] = {}
        if error.attempt_count > 0:
            details["attemptCount"] = error.attempt_count
        if error.status_code is not None:
            details["upstreamStatusCode"] = error.status_code
        return details


__all__ = ["ErrorWireMapper", "MappedAnalysisError"]
