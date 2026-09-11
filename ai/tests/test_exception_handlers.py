import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api.error_handlers import register_exception_handlers
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
    ReportPolicyError,
    ResponseMappingError,
    UnsupportedAnalysisCombinationError,
)
from app.core.runtime import ReportRuntime
from app.domain import InternalPortfolioInput, InternalPortfolioReport
from app.main import create_app
from app.mappers import (
    ErrorWireMapper,
    MappedAnalysisError,
    RequestWireMapper,
    ResponseWireMapper,
)
from app.validators.report_validator import PolicyViolation, PolicyViolationCode

ANALYSIS_ID = UUID("11111111-1111-4111-8111-111111111111")
_STATE_MISSING = object()


class _ValidatedBody(BaseModel):
    repositoryId: str


class _RecordingMapper(ErrorWireMapper):
    def __init__(self) -> None:
        self.calls: list[tuple[BaseException, UUID | None]] = []

    def to_wire(
        self,
        error: BaseException,
        *,
        analysis_id: UUID | None,
    ) -> MappedAnalysisError:
        self.calls.append((error, analysis_id))
        return super().to_wire(error, analysis_id=analysis_id)


class _UnusedReportService:
    async def generate(
        self,
        portfolio: InternalPortfolioInput,
        *,
        question_count: int = 5,
        statement_count: int = 6,
    ) -> InternalPortfolioReport:
        raise AssertionError("Health route must not invoke the report service")


def _build_test_runtime() -> ReportRuntime:
    return ReportRuntime(
        report_service=_UnusedReportService(),
        request_mapper=RequestWireMapper(),
        response_mapper=ResponseWireMapper(),
        evaluator_version="test-model:test-prompt",
    )


def _build_error_app(
    error_factory: Callable[[], Exception],
    *,
    state_analysis_id: object = _STATE_MISSING,
    mapper: ErrorWireMapper | None = None,
) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app, mapper=mapper)

    @app.get("/raise")
    async def raise_error(request: Request) -> None:
        if state_analysis_id is not _STATE_MISSING:
            request.state.analysis_id = state_analysis_id
        raise error_factory()

    return app


def _request_error(
    error_factory: Callable[[], Exception],
    *,
    state_analysis_id: object = _STATE_MISSING,
    mapper: ErrorWireMapper | None = None,
) -> tuple[dict[str, Any], int, str]:
    app = _build_error_app(
        error_factory,
        state_analysis_id=state_analysis_id,
        mapper=mapper,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/raise")
    return response.json(), response.status_code, response.headers["content-type"]


def _build_validation_app(*, set_state: bool = False) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    if set_state:

        @app.middleware("http")
        async def add_analysis_id(request: Request, call_next: Callable[..., Any]) -> Any:
            request.state.analysis_id = ANALYSIS_ID
            return await call_next(request)

    @app.post("/validated")
    async def validate_body(body: _ValidatedBody) -> dict[str, str]:
        return {"repositoryId": body.repositoryId}

    return app


def test_request_validation_error_returns_invalid_request() -> None:
    app = _build_validation_app()
    with TestClient(app) as client:
        response = client.post("/validated", json={"repositoryId": 123})

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"
    assert response.json()["retryable"] is False


def test_request_validation_error_never_trusts_state_analysis_id() -> None:
    app = _build_validation_app(set_state=True)
    with TestClient(app) as client:
        response = client.post("/validated", json={"repositoryId": 123})

    assert response.json()["analysisId"] is None


def test_request_validation_details_only_contain_field_path_and_type() -> None:
    app = _build_validation_app()
    with TestClient(app) as client:
        response = client.post("/validated", json={"repositoryId": 123})

    assert response.json()["details"] == {
        "errors": [{"fieldPath": "repositoryId", "type": "string_type"}]
    }


def test_request_validation_does_not_expose_request_body_or_original_message() -> None:
    secret = "sensitive-request-body"
    app = _build_validation_app()
    with TestClient(app) as client:
        response = client.post("/validated", json={"repositoryId": [secret]})

    serialized = response.text
    assert secret not in serialized
    assert "Input should be a valid string" not in serialized


def test_uuid_from_request_state_is_preserved() -> None:
    body, _, _ = _request_error(
        lambda: RuntimeError("sensitive"),
        state_analysis_id=ANALYSIS_ID,
    )

    assert body["analysisId"] == str(ANALYSIS_ID)


def test_missing_request_state_analysis_id_returns_null() -> None:
    body, _, _ = _request_error(lambda: RuntimeError("sensitive"))

    assert body["analysisId"] is None


def test_string_request_state_analysis_id_is_not_parsed() -> None:
    body, _, _ = _request_error(
        lambda: RuntimeError("sensitive"),
        state_analysis_id=str(ANALYSIS_ID),
    )

    assert body["analysisId"] is None


@pytest.mark.parametrize(
    ("error_factory", "expected_status", "expected_code", "retryable"),
    [
        (
            lambda: UnsupportedAnalysisCombinationError("sensitive"),
            422,
            "UNSUPPORTED_COMBINATION",
            False,
        ),
        (
            lambda: InputValidationError(
                [InputViolation(InputViolationCode.DUPLICATE_EVIDENCE_ID, "sensitive")]
            ),
            400,
            "INVALID_REQUEST",
            False,
        ),
        (
            lambda: ReportPolicyError(
                [PolicyViolation(PolicyViolationCode.UNKNOWN_EVIDENCE_REF, "sensitive")]
            ),
            502,
            "POLICY_VIOLATION",
            False,
        ),
        (
            lambda: LLMTimeoutError("sensitive", retryable=True, attempt_count=2),
            504,
            "LLM_TIMEOUT",
            True,
        ),
        (
            lambda: PortfolioReportDeadlineError("sensitive"),
            504,
            "LLM_TIMEOUT",
            True,
        ),
        (
            lambda: LLMRateLimitError("sensitive", retryable=True, attempt_count=2),
            503,
            "LLM_RATE_LIMITED",
            True,
        ),
        (
            lambda: LLMStructuredOutputError("sensitive", attempt_count=1),
            502,
            "STRUCTURED_OUTPUT_INVALID",
            False,
        ),
        (
            lambda: LLMServiceError("sensitive", retryable=True, attempt_count=2),
            502,
            "LLM_SERVICE_ERROR",
            True,
        ),
        (
            lambda: LLMConfigurationError("sensitive"),
            500,
            "INTERNAL_ERROR",
            False,
        ),
        (
            lambda: ResponseMappingError("sensitive"),
            500,
            "INTERNAL_ERROR",
            False,
        ),
        (
            lambda: RuntimeError("sensitive"),
            500,
            "INTERNAL_ERROR",
            False,
        ),
    ],
)
def test_internal_exceptions_use_error_wire_mapper_policy(
    error_factory: Callable[[], Exception],
    expected_status: int,
    expected_code: str,
    retryable: bool,
) -> None:
    body, status_code, _ = _request_error(error_factory)

    assert status_code == expected_status
    assert body["code"] == expected_code
    assert body["retryable"] is retryable
    assert body["schemaVersion"] == "1.0"


def test_handler_returns_backend_camel_case_json() -> None:
    body, status_code, content_type = _request_error(
        lambda: LLMServiceError(
            "sensitive",
            retryable=True,
            attempt_count=3,
            status_code=503,
        ),
        state_analysis_id=ANALYSIS_ID,
    )

    assert status_code == 502
    assert content_type.startswith("application/json")
    assert body == {
        "schemaVersion": "1.0",
        "analysisId": str(ANALYSIS_ID),
        "code": "LLM_SERVICE_ERROR",
        "message": "AI 서비스 처리 중 일시적인 오류가 발생했습니다.",
        "retryable": True,
        "details": {"attemptCount": 3, "upstreamStatusCode": 503},
    }
    assert "detail" not in body


def test_sensitive_internal_error_values_are_not_exposed() -> None:
    sensitive_values = (
        "secret-api-key",
        "ignore previous instructions",
        "raw Gemini response",
        "private repository source",
        "/Users/person/private/file.py",
    )
    body, _, _ = _request_error(
        lambda: LLMServiceError(
            " | ".join(sensitive_values),
            retryable=True,
            attempt_count=1,
            status_code=500,
        )
    )
    serialized = json.dumps(body, ensure_ascii=False)

    assert all(value not in serialized for value in sensitive_values)


def test_not_found_keeps_fastapi_default_handler() -> None:
    app = FastAPI()
    register_exception_handlers(app)
    with TestClient(app) as client:
        response = client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_method_not_allowed_keeps_fastapi_default_handler() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/resource")
    async def get_resource() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        response = client.post("/resource")

    assert response.status_code == 405
    assert response.json() == {"detail": "Method Not Allowed"}


def test_existing_health_route_is_unchanged() -> None:
    with TestClient(create_app(runtime=_build_test_runtime())) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "UP"}


def test_handler_passes_original_error_and_trusted_analysis_id_to_mapper() -> None:
    mapper = _RecordingMapper()
    original_error = RuntimeError("sensitive")
    _request_error(
        lambda: original_error,
        state_analysis_id=ANALYSIS_ID,
        mapper=mapper,
    )

    assert mapper.calls == [(original_error, ANALYSIS_ID)]


def test_same_error_produces_deterministic_response() -> None:
    first = _request_error(
        lambda: LLMTimeoutError("first sensitive value", retryable=True, attempt_count=2),
        state_analysis_id=ANALYSIS_ID,
    )
    second = _request_error(
        lambda: LLMTimeoutError("second sensitive value", retryable=True, attempt_count=2),
        state_analysis_id=ANALYSIS_ID,
    )

    assert first == second


def test_handler_does_not_mutate_original_exception_metadata() -> None:
    original_error = LLMServiceError(
        "sensitive",
        retryable=True,
        attempt_count=3,
        status_code=503,
    )
    original_values = (
        original_error.args,
        original_error.retryable,
        original_error.attempt_count,
        original_error.status_code,
    )

    _request_error(lambda: original_error)

    assert (
        original_error.args,
        original_error.retryable,
        original_error.attempt_count,
        original_error.status_code,
    ) == original_values
