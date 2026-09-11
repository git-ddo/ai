import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.error_handlers import register_exception_handlers
from app.api.health import router as health_router
from app.api.reports import router as reports_router
from app.core.exceptions import (
    LLMRateLimitError,
    LLMServiceError,
    LLMStructuredOutputError,
    LLMTimeoutError,
    ReportPolicyError,
    ResponseMappingError,
)
from app.core.runtime import ReportRuntime
from app.domain import (
    AnalysisDepth,
    AnalysisItemType,
    EvidenceConfidence,
    GroundedAnalysisItem,
    InternalGenerationRecord,
    InternalGenerationStage,
    InternalPortfolioInput,
    InternalPortfolioReport,
    PortfolioAnalysis,
    PortfolioSynthesis,
    RepositoryAnalysis,
    RepresentativeProject,
)
from app.main import create_app
from app.mappers import RequestWireMapper, ResponseWireMapper
from app.schemas.request import PortfolioReportRequest
from app.validators.report_validator import PolicyViolation, PolicyViolationCode

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "contracts" / "backend_contract"
ENDPOINT = "/internal/v1/portfolio-reports"

_CRITERION_BY_DEPTH = {
    AnalysisDepth.P0: "README_READINESS",
    AnalysisDepth.P1: "ACTIVITY_SCOPE",
    AnalysisDepth.P2: "SNIPPET_SCOPE",
}


class _RecordingReportService:
    def __init__(
        self,
        *,
        error: Exception | None = None,
    ) -> None:
        self.error = error
        self.calls: list[InternalPortfolioInput] = []

    async def generate(
        self,
        portfolio: InternalPortfolioInput,
        *,
        question_count: int = 5,
        statement_count: int = 6,
    ) -> InternalPortfolioReport:
        assert question_count == 5
        assert statement_count == 6
        self.calls.append(portfolio)
        if self.error is not None:
            raise self.error
        return _make_internal_report(portfolio)


class _FailingResponseMapper(ResponseWireMapper):
    def to_wire(
        self,
        request: PortfolioReportRequest,
        report: InternalPortfolioReport,
        *,
        evaluator_version: str,
    ) -> Any:
        raise ResponseMappingError("sensitive response mapping detail")


def _load_request_data(depth: AnalysisDepth) -> dict[str, Any]:
    path = FIXTURES_DIR / f"analysis-request.{depth.value.casefold()}.example.json"
    with path.open(encoding="utf-8") as fixture_file:
        raw: object = json.load(fixture_file)
    if not isinstance(raw, dict):
        raise TypeError("Request fixture must contain an object")
    return cast(dict[str, Any], raw)


def _make_runtime(
    service: _RecordingReportService | None = None,
    *,
    response_mapper: ResponseWireMapper | None = None,
) -> tuple[ReportRuntime, _RecordingReportService]:
    selected_service = service or _RecordingReportService()
    return (
        ReportRuntime(
            report_service=selected_service,
            request_mapper=RequestWireMapper(),
            response_mapper=response_mapper or ResponseWireMapper(),
            evaluator_version="test-model:backend-entry-p0-p1-p2-1.1",
        ),
        selected_service,
    )


def _make_internal_report(portfolio: InternalPortfolioInput) -> InternalPortfolioReport:
    analyses: list[RepositoryAnalysis] = []
    repository_records: list[InternalGenerationRecord] = []
    global_refs: list[str] = []
    global_criteria: list[str] = []

    for repository in portfolio.repositories:
        references_by_depth: dict[AnalysisDepth, str] = {}
        for evidence in repository.evidence:
            references_by_depth.setdefault(evidence.analysis_depth, evidence.evidence_id)
        evidence_refs = tuple(references_by_depth.values())
        criterion_keys = tuple(_CRITERION_BY_DEPTH[depth] for depth in references_by_depth)
        global_refs.extend(evidence_refs)
        global_criteria.extend(criterion_keys)

        analyses.append(
            RepositoryAnalysis(
                repository_full_name=repository.repository_full_name,
                summary=_make_item(
                    AnalysisItemType.INTERPRETATION,
                    evidence_refs,
                    criterion_keys,
                    f"{repository.repository_full_name}의 공개 근거를 요약했습니다.",
                ),
                limitations=("전달된 근거 범위에서만 분석했습니다.",),
            )
        )
        repository_records.append(
            InternalGenerationRecord(
                stage=InternalGenerationStage.REPOSITORY,
                repository_full_name=repository.repository_full_name,
                duration_ms=0,
                attempt_count=1,
            )
        )

    evidence_refs = tuple(dict.fromkeys(global_refs))
    criterion_keys = tuple(dict.fromkeys(global_criteria))
    synthesis = PortfolioSynthesis(
        overall_summary=_make_item(
            AnalysisItemType.INTERPRETATION,
            evidence_refs,
            criterion_keys,
            "선택한 저장소의 공개 근거를 종합했습니다.",
        ),
        representative_projects=tuple(
            RepresentativeProject(
                repository_full_name=repository.repository_full_name,
                reason="공개 근거가 확인되는 대표 프로젝트입니다.",
                confidence=EvidenceConfidence.HIGH,
                evidence_refs=(repository.evidence[0].evidence_id,),
            )
            for repository in portfolio.repositories
        ),
        job_appeal=_make_item(
            AnalysisItemType.JOB_APPEAL,
            evidence_refs,
            criterion_keys,
            "공개 근거를 바탕으로 백엔드 경험을 설명할 수 있습니다.",
        ),
        limitations=("사용자의 절대적인 역량을 평가하지 않습니다.",),
    )
    return InternalPortfolioReport(
        analysis=PortfolioAnalysis(
            repository_analyses=tuple(analyses),
            synthesis=synthesis,
        ),
        generation_records=(
            *repository_records,
            InternalGenerationRecord(
                stage=InternalGenerationStage.PORTFOLIO,
                duration_ms=0,
                attempt_count=1,
            ),
            InternalGenerationRecord(
                stage=InternalGenerationStage.STATEMENT,
                duration_ms=0,
                attempt_count=1,
            ),
        ),
    )


def _make_item(
    item_type: AnalysisItemType,
    evidence_refs: Sequence[str],
    criterion_keys: Sequence[str],
    content: str,
) -> GroundedAnalysisItem:
    return GroundedAnalysisItem(
        item_type=item_type,
        content=content,
        confidence=EvidenceConfidence.HIGH,
        evidence_refs=tuple(evidence_refs),
        criterion_keys=tuple(criterion_keys),
    )


@pytest.mark.parametrize("depth", list(AnalysisDepth))
def test_report_endpoint_maps_backend_fixture_without_gemini(depth: AnalysisDepth) -> None:
    raw = _load_request_data(depth)
    runtime, service = _make_runtime()
    app = create_app(runtime=runtime)

    with TestClient(app) as client:
        response = client.post(ENDPOINT, json=raw)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["schemaVersion"] == "1.1"
    assert body["analysisId"] == raw["analysisId"]
    assert body["requestedAnalysisDepth"] == raw["requestedAnalysisDepth"]
    assert body["evaluatorVersion"] == runtime.evaluator_version
    used_depths = {
        evidence.analysis_depth
        for repository in service.calls[0].repositories
        for evidence in repository.evidence
    }
    assert body["usedEvidenceLevels"] == [
        item.value for item in AnalysisDepth if item in used_depths
    ]
    assert service.calls[0].requested_analysis_depth.value == raw["requestedAnalysisDepth"]
    assert len(service.calls) == 1

    for request_repository, response_repository in zip(
        raw["repositories"], body["repositories"], strict=True
    ):
        assert response_repository["repositoryId"] == request_repository["repositoryId"]
        assert response_repository["repositoryFullName"] == request_repository["repositoryFullName"]
        assert (
            response_repository["snapshotHashAlgorithm"]
            == request_repository["snapshotHashAlgorithm"]
        )
        assert response_repository["snapshotSha"] == request_repository["snapshotSha"]

    serialized = response.text
    assert "generationRecords" not in serialized
    assert "criterionKeys" not in serialized
    assert "requested_analysis_depth" not in serialized


def test_response_mapper_output_is_returned_unchanged() -> None:
    raw = _load_request_data(AnalysisDepth.P0)
    request_model = PortfolioReportRequest.model_validate(raw)
    runtime, service = _make_runtime()
    expected = runtime.response_mapper.to_wire(
        request_model,
        _make_internal_report(runtime.request_mapper.to_internal(request_model)),
        evaluator_version=runtime.evaluator_version,
    )

    with TestClient(create_app(runtime=runtime)) as client:
        response = client.post(ENDPOINT, json=raw)

    assert response.json() == expected.model_dump(mode="json", by_alias=True)
    assert len(service.calls) == 1


def test_openapi_and_health_include_report_api() -> None:
    runtime, _ = _make_runtime()
    with TestClient(create_app(runtime=runtime)) as client:
        health_response = client.get("/health")
        openapi_response = client.get("/openapi.json")

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "UP"}
    assert ENDPOINT in openapi_response.json()["paths"]


def test_invalid_body_returns_null_analysis_id() -> None:
    runtime, _ = _make_runtime()
    with TestClient(create_app(runtime=runtime), raise_server_exceptions=False) as client:
        response = client.post(ENDPOINT, json={"analysisId": "not-a-uuid"})

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"
    assert response.json()["analysisId"] is None


def test_unsupported_combination_preserves_analysis_id() -> None:
    raw = _load_request_data(AnalysisDepth.P0)
    raw["targetJob"] = "FRONTEND"
    runtime, _ = _make_runtime()

    with TestClient(create_app(runtime=runtime), raise_server_exceptions=False) as client:
        response = client.post(ENDPOINT, json=raw)

    assert response.status_code == 422
    assert response.json()["code"] == "UNSUPPORTED_COMBINATION"
    assert response.json()["analysisId"] == raw["analysisId"]


def test_request_mapper_error_preserves_analysis_id() -> None:
    raw = _load_request_data(AnalysisDepth.P1)
    raw["repositories"][0]["completedEvidenceLevels"] = []
    runtime, _ = _make_runtime()

    with TestClient(create_app(runtime=runtime), raise_server_exceptions=False) as client:
        response = client.post(ENDPOINT, json=raw)

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"
    assert response.json()["analysisId"] == raw["analysisId"]


@pytest.mark.parametrize(
    ("error", "status_code", "code", "retryable"),
    [
        (
            ReportPolicyError(
                [PolicyViolation(PolicyViolationCode.UNKNOWN_EVIDENCE_REF, "sensitive")]
            ),
            502,
            "POLICY_VIOLATION",
            False,
        ),
        (LLMTimeoutError("sensitive", retryable=True, attempt_count=2), 504, "LLM_TIMEOUT", True),
        (
            LLMRateLimitError("sensitive", retryable=True, attempt_count=2),
            503,
            "LLM_RATE_LIMITED",
            True,
        ),
        (
            LLMStructuredOutputError("sensitive", attempt_count=1),
            502,
            "STRUCTURED_OUTPUT_INVALID",
            False,
        ),
        (
            LLMServiceError("sensitive", retryable=True, attempt_count=2),
            502,
            "LLM_SERVICE_ERROR",
            True,
        ),
    ],
)
def test_report_service_errors_use_existing_exception_handler(
    error: Exception,
    status_code: int,
    code: str,
    retryable: bool,
) -> None:
    raw = _load_request_data(AnalysisDepth.P0)
    runtime, _ = _make_runtime(_RecordingReportService(error=error))

    with TestClient(create_app(runtime=runtime), raise_server_exceptions=False) as client:
        response = client.post(ENDPOINT, json=raw)

    assert response.status_code == status_code
    assert response.json()["code"] == code
    assert response.json()["retryable"] is retryable
    assert response.json()["analysisId"] == raw["analysisId"]


def test_response_mapper_error_returns_safe_internal_error() -> None:
    raw = _load_request_data(AnalysisDepth.P0)
    runtime, _ = _make_runtime(response_mapper=_FailingResponseMapper())

    with TestClient(create_app(runtime=runtime), raise_server_exceptions=False) as client:
        response = client.post(ENDPOINT, json=raw)

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert response.json()["analysisId"] == raw["analysisId"]
    assert "sensitive response mapping detail" not in response.text


def test_missing_runtime_returns_safe_internal_error_with_analysis_id() -> None:
    raw = _load_request_data(AnalysisDepth.P0)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(reports_router)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(ENDPOINT, json=raw)

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert response.json()["analysisId"] == raw["analysisId"]
    assert "runtime" not in response.text.casefold()


def test_invalid_runtime_type_returns_safe_internal_error() -> None:
    raw = _load_request_data(AnalysisDepth.P0)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(reports_router)
    app.state.report_runtime = object()

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(ENDPOINT, json=raw)

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert response.json()["analysisId"] == raw["analysisId"]


def test_failure_does_not_expose_request_or_provider_secrets() -> None:
    raw = _load_request_data(AnalysisDepth.P0)
    sensitive_values = (
        "sensitive-evidence-value",
        "sensitive-system-prompt",
        "sensitive-user-prompt",
        "sensitive-api-key",
        "sensitive-gemini-response",
    )
    raw["repositories"][0]["evidence"][0]["value"] = sensitive_values[0]
    service = _RecordingReportService(
        error=LLMServiceError(
            " ".join(sensitive_values[1:]),
            retryable=True,
            attempt_count=1,
            status_code=500,
        )
    )
    runtime, _ = _make_runtime(service)

    with TestClient(create_app(runtime=runtime), raise_server_exceptions=False) as client:
        response = client.post(ENDPOINT, json=raw)

    assert response.status_code == 502
    assert all(value not in response.text for value in sensitive_values)
