import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.schemas.common import (
    AnalysisDepth,
    RequestAnalysisPurpose,
    RequestEvidenceType,
    TargetCareerLevel,
    TargetJob,
)
from app.schemas.request import PortfolioReportRequest

BACKEND_CONTRACT_COMMIT = "9d9fc7caf36150bc090c7a5b9bad62ce33743fc3"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "contracts" / "backend_contract"
EXAMPLE_FILES = {
    AnalysisDepth.P0: "analysis-request.p0.example.json",
    AnalysisDepth.P1: "analysis-request.p1.example.json",
    AnalysisDepth.P2: "analysis-request.p2.example.json",
}


def load_example(depth: AnalysisDepth = AnalysisDepth.P0) -> dict[str, Any]:
    with (FIXTURES_DIR / EXAMPLE_FILES[depth]).open(encoding="utf-8") as fixture_file:
        raw_data: object = json.load(fixture_file)

    if not isinstance(raw_data, dict):
        raise TypeError("Request fixture must contain a JSON object")
    return cast(dict[str, Any], raw_data)


@pytest.fixture
def valid_request_data() -> dict[str, Any]:
    return load_example()


@pytest.mark.parametrize("depth", list(AnalysisDepth))
def test_backend_examples_parse_and_round_trip(depth: AnalysisDepth) -> None:
    raw_data = load_example(depth)

    request = PortfolioReportRequest.model_validate(raw_data)

    assert request.requested_analysis_depth is depth
    assert request.model_dump(mode="json", by_alias=True) == raw_data


def test_request_exposes_typed_contract_values(valid_request_data: dict[str, Any]) -> None:
    request = PortfolioReportRequest.model_validate(valid_request_data)

    assert request.schema_version == "1.0"
    assert request.analysis_id == UUID("11111111-1111-4111-8111-111111111111")
    assert request.target_job is TargetJob.BACKEND
    assert request.target_career_level is TargetCareerLevel.ENTRY
    assert request.analysis_purpose is RequestAnalysisPurpose.PORTFOLIO_ANALYSIS
    assert request.repositories[0].evidence[0].evidence_type is RequestEvidenceType.GITHUB_STATIC


def test_python_field_names_are_accepted(valid_request_data: dict[str, Any]) -> None:
    request = PortfolioReportRequest.model_validate(valid_request_data)

    reparsed = PortfolioReportRequest.model_validate(request.model_dump())

    assert reparsed == request


def test_schema_version_only_accepts_version_1_0(valid_request_data: dict[str, Any]) -> None:
    valid_request_data["schemaVersion"] = "1.1"

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportRequest.model_validate(valid_request_data)

    assert exc_info.value.errors()[0]["type"] == "literal_error"


def test_invalid_analysis_id_is_rejected(valid_request_data: dict[str, Any]) -> None:
    valid_request_data["analysisId"] = "not-a-uuid"

    with pytest.raises(ValidationError):
        PortfolioReportRequest.model_validate(valid_request_data)


@pytest.mark.parametrize(
    "required_field",
    [
        "schemaVersion",
        "analysisId",
        "targetJob",
        "targetCareerLevel",
        "analysisPurpose",
        "requestedAnalysisDepth",
        "extractorVersion",
        "repositories",
    ],
)
def test_missing_required_top_level_fields_are_rejected(
    valid_request_data: dict[str, Any], required_field: str
) -> None:
    valid_request_data.pop(required_field)

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportRequest.model_validate(valid_request_data)

    assert exc_info.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize(
    ("container_path", "unknown_field"),
    [
        ((), "unexpectedTopLevel"),
        (("repositories", 0), "unexpectedRepositoryField"),
        (("repositories", 0, "userClaims", 0), "unexpectedClaimField"),
        (("repositories", 0, "evidence", 0), "unexpectedEvidenceField"),
    ],
)
def test_unknown_fields_are_rejected(
    valid_request_data: dict[str, Any],
    container_path: tuple[str | int, ...],
    unknown_field: str,
) -> None:
    container: Any = valid_request_data
    for part in container_path:
        container = container[part]
    container[unknown_field] = "unexpected"

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportRequest.model_validate(valid_request_data)

    assert any(error["type"] == "extra_forbidden" for error in exc_info.value.errors())


@pytest.mark.parametrize("repository_count", [1, 5])
def test_repository_count_accepts_boundaries(
    valid_request_data: dict[str, Any], repository_count: int
) -> None:
    repository = valid_request_data["repositories"][0]
    valid_request_data["repositories"] = [deepcopy(repository) for _ in range(repository_count)]

    request = PortfolioReportRequest.model_validate(valid_request_data)

    assert len(request.repositories) == repository_count


@pytest.mark.parametrize("repository_count", [0, 6])
def test_repository_count_rejects_out_of_range_values(
    valid_request_data: dict[str, Any], repository_count: int
) -> None:
    repository = valid_request_data["repositories"][0]
    valid_request_data["repositories"] = [deepcopy(repository) for _ in range(repository_count)]

    with pytest.raises(ValidationError):
        PortfolioReportRequest.model_validate(valid_request_data)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("targetJob", "DATA"),
        ("targetCareerLevel", "STAFF"),
        ("analysisPurpose", "INTERVIEW_PREPARATION"),
        ("requestedAnalysisDepth", "P3"),
    ],
)
def test_invalid_top_level_enum_is_rejected(
    valid_request_data: dict[str, Any], field: str, invalid_value: str
) -> None:
    valid_request_data[field] = invalid_value

    with pytest.raises(ValidationError):
        PortfolioReportRequest.model_validate(valid_request_data)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("evidenceType", "USER_PROVIDED"),
        ("valueType", "OBJECT"),
        ("analysisDepth", "P3"),
        ("snapshotHashAlgorithm", "MD5"),
    ],
)
def test_invalid_evidence_enum_is_rejected(
    valid_request_data: dict[str, Any], field: str, invalid_value: str
) -> None:
    valid_request_data["repositories"][0]["evidence"][0][field] = invalid_value

    with pytest.raises(ValidationError):
        PortfolioReportRequest.model_validate(valid_request_data)


@pytest.mark.parametrize(
    ("location", "invalid_id"),
    [
        ("claimId", "claim_12"),
        ("claimId", "claim-a"),
        ("evidenceId", "ev_12"),
        ("evidenceId", "evidence_001"),
    ],
)
def test_invalid_contract_id_pattern_is_rejected(
    valid_request_data: dict[str, Any], location: str, invalid_id: str
) -> None:
    if location == "claimId":
        valid_request_data["repositories"][0]["userClaims"][0][location] = invalid_id
    else:
        valid_request_data["repositories"][0]["evidence"][0][location] = invalid_id

    with pytest.raises(ValidationError):
        PortfolioReportRequest.model_validate(valid_request_data)


def test_nullable_fields_accept_null(valid_request_data: dict[str, Any]) -> None:
    repository = valid_request_data["repositories"][0]
    repository["defaultBranch"] = None
    warning = {"code": "TRUNCATED_INPUT", "path": None, "message": "입력이 잘렸습니다."}
    repository["collectionWarnings"] = [warning]
    claim = repository["userClaims"][0]
    claim["participationLevel"] = None
    claim["participationStartedOn"] = None
    claim["participationEndedOn"] = None
    evidence = repository["evidence"][0]
    for field in (
        "path",
        "startLine",
        "endLine",
        "commitSha",
        "pullRequestNumber",
        "derivedFromLevel",
    ):
        evidence[field] = None

    PortfolioReportRequest.model_validate(valid_request_data)


def test_participation_dates_parse_and_serialize(valid_request_data: dict[str, Any]) -> None:
    claim = valid_request_data["repositories"][0]["userClaims"][0]
    claim["participationStartedOn"] = "2026-03-01"
    claim["participationEndedOn"] = "2026-08-31"

    request = PortfolioReportRequest.model_validate(valid_request_data)
    serialized = request.model_dump(mode="json", by_alias=True)

    assert request.repositories[0].user_claims[0].participation_started_on == date(2026, 3, 1)
    assert serialized["repositories"][0]["userClaims"][0]["participationStartedOn"] == (
        "2026-03-01"
    )
    assert serialized["repositories"][0]["userClaims"][0]["participationEndedOn"] == ("2026-08-31")


@pytest.mark.parametrize("field", ["startLine", "endLine", "pullRequestNumber"])
def test_integer_fields_reject_boolean(valid_request_data: dict[str, Any], field: str) -> None:
    valid_request_data["repositories"][0]["evidence"][0][field] = True

    with pytest.raises(ValidationError):
        PortfolioReportRequest.model_validate(valid_request_data)


@pytest.mark.parametrize("target_job", list(TargetJob))
def test_all_schema_target_jobs_are_shape_valid(
    valid_request_data: dict[str, Any], target_job: TargetJob
) -> None:
    valid_request_data["targetJob"] = target_job.value

    request = PortfolioReportRequest.model_validate(valid_request_data)

    assert request.target_job is target_job


@pytest.mark.parametrize("career_level", list(TargetCareerLevel))
def test_all_schema_career_levels_are_shape_valid(
    valid_request_data: dict[str, Any], career_level: TargetCareerLevel
) -> None:
    valid_request_data["targetCareerLevel"] = career_level.value

    request = PortfolioReportRequest.model_validate(valid_request_data)

    assert request.target_career_level is career_level


@pytest.mark.parametrize("depth", list(AnalysisDepth))
def test_all_schema_depths_are_shape_valid(
    valid_request_data: dict[str, Any], depth: AnalysisDepth
) -> None:
    valid_request_data["requestedAnalysisDepth"] = depth.value

    request = PortfolioReportRequest.model_validate(valid_request_data)

    assert request.requested_analysis_depth is depth


def test_unresolved_evidence_references_remain_semantic_validation(
    valid_request_data: dict[str, Any],
) -> None:
    repository = valid_request_data["repositories"][0]
    repository["userClaims"][0]["relatedEvidenceRefs"] = ["ev_999"]
    repository["evidence"][0]["sourceEvidenceRefs"] = ["ev_998"]

    request = PortfolioReportRequest.model_validate(valid_request_data)

    assert request.repositories[0].user_claims[0].related_evidence_refs == ["ev_999"]
    assert request.repositories[0].evidence[0].source_evidence_refs == ["ev_998"]


def test_schema_does_not_add_repository_id_or_completed_level_semantics(
    valid_request_data: dict[str, Any],
) -> None:
    repository = valid_request_data["repositories"][0]
    repository["repositoryId"] = "repository-alpha"
    repository["completedEvidenceLevels"] = []

    request = PortfolioReportRequest.model_validate(valid_request_data)

    assert request.repositories[0].repository_id == "repository-alpha"
    assert request.repositories[0].completed_evidence_levels == []


def test_wire_request_does_not_convert_to_internal_models(
    valid_request_data: dict[str, Any],
) -> None:
    request = PortfolioReportRequest.model_validate(valid_request_data)

    assert not hasattr(request, "to_internal")
    assert not hasattr(request.repositories[0], "normalize")
