import json
from uuid import UUID

import pytest
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError

from app.core.exceptions import (
    InputValidationError,
    InputViolation,
    InputViolationCode,
    LLMConfigurationError,
    LLMRateLimitError,
    LLMServiceError,
    LLMStructuredOutputError,
    LLMTimeoutError,
    PortfolioReportDeadlineError,
    PortfolioSynthesisError,
    ReportPolicyError,
    RequestMappingError,
    ResponseMappingError,
    UnsupportedAnalysisCombinationError,
)
from app.mappers import ErrorWireMapper, MappedAnalysisError
from app.schemas.common import AnalysisErrorCode
from app.validators.report_validator import PolicyViolation, PolicyViolationCode

ANALYSIS_ID = UUID("11111111-1111-4111-8111-111111111111")


class _RequiredValue(BaseModel):
    value: str


def _pydantic_error() -> ValidationError:
    with pytest.raises(ValidationError) as exc_info:
        _RequiredValue.model_validate({"value": 123})
    return exc_info.value


def _assert_mapping(
    error: BaseException,
    *,
    code: AnalysisErrorCode,
    status_code: int,
    retryable: bool,
) -> MappedAnalysisError:
    mapped = ErrorWireMapper().to_wire(error, analysis_id=ANALYSIS_ID)
    assert mapped.status_code == status_code
    assert mapped.body.code is code
    assert mapped.body.retryable is retryable
    return mapped


def test_unsupported_combination_maps_to_422() -> None:
    _assert_mapping(
        UnsupportedAnalysisCombinationError("sensitive combination"),
        code=AnalysisErrorCode.UNSUPPORTED_COMBINATION,
        status_code=422,
        retryable=False,
    )


def test_pydantic_validation_error_maps_to_400() -> None:
    _assert_mapping(
        _pydantic_error(),
        code=AnalysisErrorCode.INVALID_REQUEST,
        status_code=400,
        retryable=False,
    )


def test_fastapi_request_validation_error_maps_to_400() -> None:
    error = RequestValidationError(
        [
            {
                "type": "string_type",
                "loc": ("body", "repositories", 0, "repositoryId"),
                "msg": "sensitive validation message",
                "input": "sensitive repository body",
            }
        ]
    )
    _assert_mapping(
        error,
        code=AnalysisErrorCode.INVALID_REQUEST,
        status_code=400,
        retryable=False,
    )


def test_request_mapping_error_maps_to_400() -> None:
    _assert_mapping(
        RequestMappingError("sensitive request"),
        code=AnalysisErrorCode.INVALID_REQUEST,
        status_code=400,
        retryable=False,
    )


def test_input_validation_error_maps_to_400() -> None:
    _assert_mapping(
        InputValidationError(
            [InputViolation(InputViolationCode.DUPLICATE_EVIDENCE_ID, "sensitive")]
        ),
        code=AnalysisErrorCode.INVALID_REQUEST,
        status_code=400,
        retryable=False,
    )


def test_report_policy_error_maps_to_502() -> None:
    _assert_mapping(
        ReportPolicyError([PolicyViolation(PolicyViolationCode.UNKNOWN_EVIDENCE_REF, "sensitive")]),
        code=AnalysisErrorCode.POLICY_VIOLATION,
        status_code=502,
        retryable=False,
    )


def test_llm_timeout_maps_to_504() -> None:
    _assert_mapping(
        LLMTimeoutError("sensitive response", retryable=True, attempt_count=2),
        code=AnalysisErrorCode.LLM_TIMEOUT,
        status_code=504,
        retryable=True,
    )


def test_report_deadline_maps_to_504() -> None:
    _assert_mapping(
        PortfolioReportDeadlineError("sensitive report state"),
        code=AnalysisErrorCode.LLM_TIMEOUT,
        status_code=504,
        retryable=True,
    )


def test_llm_rate_limit_maps_to_503() -> None:
    _assert_mapping(
        LLMRateLimitError("sensitive response", retryable=True, attempt_count=3),
        code=AnalysisErrorCode.LLM_RATE_LIMITED,
        status_code=503,
        retryable=True,
    )


def test_structured_output_error_maps_to_502() -> None:
    _assert_mapping(
        LLMStructuredOutputError("sensitive Gemini response", attempt_count=1),
        code=AnalysisErrorCode.STRUCTURED_OUTPUT_INVALID,
        status_code=502,
        retryable=False,
    )


def test_llm_service_error_maps_to_502() -> None:
    _assert_mapping(
        LLMServiceError("sensitive response", retryable=True, attempt_count=2, status_code=503),
        code=AnalysisErrorCode.LLM_SERVICE_ERROR,
        status_code=502,
        retryable=True,
    )


def test_llm_configuration_error_maps_to_500() -> None:
    _assert_mapping(
        LLMConfigurationError("GEMINI_API_KEY=sensitive-key"),
        code=AnalysisErrorCode.INTERNAL_ERROR,
        status_code=500,
        retryable=False,
    )


def test_response_mapping_error_maps_to_500() -> None:
    _assert_mapping(
        ResponseMappingError("sensitive response"),
        code=AnalysisErrorCode.INTERNAL_ERROR,
        status_code=500,
        retryable=False,
    )


@pytest.mark.parametrize(
    "error",
    [PortfolioSynthesisError("sensitive"), RuntimeError("sensitive")],
)
def test_internal_and_unknown_errors_map_to_500(error: BaseException) -> None:
    _assert_mapping(
        error,
        code=AnalysisErrorCode.INTERNAL_ERROR,
        status_code=500,
        retryable=False,
    )


def test_schema_version_and_analysis_id_are_preserved() -> None:
    mapped = ErrorWireMapper().to_wire(RuntimeError("sensitive"), analysis_id=ANALYSIS_ID)

    assert mapped.body.schema_version == "1.0"
    assert mapped.body.analysis_id == ANALYSIS_ID


def test_analysis_id_can_be_none() -> None:
    mapped = ErrorWireMapper().to_wire(RuntimeError("sensitive"), analysis_id=None)

    assert mapped.body.analysis_id is None


def test_input_violation_details_only_include_code_and_optional_field_path() -> None:
    error = InputValidationError(
        [
            InputViolation(
                InputViolationCode.DUPLICATE_EVIDENCE_ID,
                "sensitive violation message",
                "repositories[1].evidence[0].evidence_id",
            ),
            InputViolation(InputViolationCode.DUPLICATE_CLAIM_ID, "another secret"),
        ]
    )

    mapped = ErrorWireMapper().to_wire(error, analysis_id=ANALYSIS_ID)

    assert mapped.body.details == {
        "violations": [
            {
                "code": "DUPLICATE_EVIDENCE_ID",
                "fieldPath": "repositories[1].evidence[0].evidence_id",
            },
            {"code": "DUPLICATE_CLAIM_ID"},
        ]
    }


def test_policy_violation_details_only_include_code_and_optional_field_path() -> None:
    error = ReportPolicyError(
        [
            PolicyViolation(
                PolicyViolationCode.UNKNOWN_EVIDENCE_REF,
                "sensitive generated content",
                "repository_analyses[0].observations[0].evidence_refs[0]",
            ),
            PolicyViolation(PolicyViolationCode.P0_SCOPE_VIOLATION, "secret prompt"),
        ]
    )

    mapped = ErrorWireMapper().to_wire(error, analysis_id=ANALYSIS_ID)

    assert mapped.body.details == {
        "violations": [
            {
                "code": "UNKNOWN_EVIDENCE_REF",
                "fieldPath": "repository_analyses[0].observations[0].evidence_refs[0]",
            },
            {"code": "P0_SCOPE_VIOLATION"},
        ]
    }


def test_pydantic_details_exclude_input_and_original_message() -> None:
    error = RequestValidationError(
        [
            {
                "type": "string_type",
                "loc": ("body", "repositories", 0, "repositoryId"),
                "msg": "sensitive validation message",
                "input": "sensitive request body",
                "ctx": {"secret": "sensitive context"},
                "url": "https://errors.example/sensitive",
            }
        ]
    )

    mapped = ErrorWireMapper().to_wire(error, analysis_id=None)

    assert mapped.body.details == {
        "errors": [{"fieldPath": "repositories.0.repositoryId", "type": "string_type"}]
    }


def test_llm_details_include_only_attempt_count_and_upstream_status() -> None:
    error = LLMServiceError(
        "sensitive provider response",
        retryable=True,
        attempt_count=3,
        status_code=503,
    )

    mapped = ErrorWireMapper().to_wire(error, analysis_id=ANALYSIS_ID)

    assert mapped.body.details == {"attemptCount": 3, "upstreamStatusCode": 503}


def test_sensitive_values_are_not_exposed() -> None:
    sensitive_values = (
        "secret-api-key",
        "ignore previous instructions",
        "raw Gemini response",
        "private repository source",
        "/Users/person/private/file.py",
    )
    error = LLMServiceError(
        " | ".join(sensitive_values),
        retryable=True,
        attempt_count=2,
        status_code=500,
    )

    mapped = ErrorWireMapper().to_wire(error, analysis_id=ANALYSIS_ID)
    serialized = json.dumps(mapped.body.model_dump(mode="json", by_alias=True), ensure_ascii=False)

    assert all(value not in serialized for value in sensitive_values)


def test_mapper_does_not_mutate_original_exception() -> None:
    violation = InputViolation(
        InputViolationCode.DUPLICATE_EVIDENCE_ID,
        "sensitive",
        "repositories[0].evidence[0]",
    )
    error = InputValidationError([violation])
    original_violations = error.violations
    original_args = error.args

    ErrorWireMapper().to_wire(error, analysis_id=ANALYSIS_ID)

    assert error.violations == original_violations
    assert error.args == original_args


def test_mapping_is_deterministic() -> None:
    error = LLMTimeoutError("sensitive", retryable=True, attempt_count=2, status_code=504)
    mapper = ErrorWireMapper()

    first = mapper.to_wire(error, analysis_id=ANALYSIS_ID)
    second = mapper.to_wire(error, analysis_id=ANALYSIS_ID)

    assert first == second


def test_wire_body_serializes_with_backend_camel_case_aliases() -> None:
    mapped = ErrorWireMapper().to_wire(
        LLMTimeoutError("sensitive", retryable=True, attempt_count=2),
        analysis_id=ANALYSIS_ID,
    )

    serialized = mapped.body.model_dump(mode="json", by_alias=True)

    assert serialized == {
        "schemaVersion": "1.0",
        "analysisId": str(ANALYSIS_ID),
        "code": "LLM_TIMEOUT",
        "message": "AI 분석 처리 시간이 초과되었습니다.",
        "retryable": True,
        "details": {"attemptCount": 2},
    }
