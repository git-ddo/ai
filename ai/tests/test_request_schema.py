import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from app.schemas.common import AnalysisPurpose, TargetJob
from app.schemas.request import PortfolioReportRequest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_json_fixture(filename: str) -> dict[str, Any]:
    with (FIXTURES_DIR / filename).open(encoding="utf-8") as fixture_file:
        raw_data: object = json.load(fixture_file)

    if not isinstance(raw_data, dict):
        raise TypeError("Request fixture must contain a JSON object")

    return cast(dict[str, Any], raw_data)


@pytest.fixture
def valid_request_data() -> dict[str, Any]:
    return load_json_fixture("valid_portfolio_report_request.json")


def test_valid_request_fixture_matches_contract(valid_request_data: dict[str, Any]) -> None:
    request = PortfolioReportRequest.model_validate(valid_request_data)

    assert request.schema_version == "1.0"
    assert request.analysis_id == 123
    assert request.target_job is TargetJob.BACKEND
    assert request.analysis_purpose is AnalysisPurpose.INTERVIEW_PREPARATION
    assert len(request.repositories) == 1
    assert request.repositories[0].github_evidence.languages[0].percentage == 88.5
    assert request.repositories[0].user_provided_role is not None
    assert request.model_dump(mode="json", by_alias=True)["schemaVersion"] == "1.0"


def test_invalid_request_fixture_is_rejected() -> None:
    invalid_data = load_json_fixture("invalid_portfolio_report_request.json")

    with pytest.raises(ValidationError):
        PortfolioReportRequest.model_validate(invalid_data)


def test_schema_version_only_accepts_version_1_0(valid_request_data: dict[str, Any]) -> None:
    valid_request_data["schemaVersion"] = "2.0"

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportRequest.model_validate(valid_request_data)

    assert exc_info.value.errors()[0]["type"] == "literal_error"


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
    ("percentage", "is_valid"),
    [(0, True), (100, True), (-0.1, False), (100.1, False)],
)
def test_language_percentage_range(
    valid_request_data: dict[str, Any], percentage: float, is_valid: bool
) -> None:
    valid_request_data["repositories"][0]["githubEvidence"]["languages"][0]["percentage"] = (
        percentage
    )

    if is_valid:
        PortfolioReportRequest.model_validate(valid_request_data)
        return

    with pytest.raises(ValidationError):
        PortfolioReportRequest.model_validate(valid_request_data)


@pytest.mark.parametrize(("score", "is_valid"), [(0, True), (100, True), (-1, False), (101, False)])
def test_backend_metric_score_range(
    valid_request_data: dict[str, Any], score: int, is_valid: bool
) -> None:
    valid_request_data["repositories"][0]["backendMetrics"]["portfolioReadinessScore"] = score

    if is_valid:
        PortfolioReportRequest.model_validate(valid_request_data)
        return

    with pytest.raises(ValidationError):
        PortfolioReportRequest.model_validate(valid_request_data)


def test_github_evidence_rejects_user_provided_fields(
    valid_request_data: dict[str, Any],
) -> None:
    valid_request_data["repositories"][0]["githubEvidence"]["userProvidedRole"] = {
        "role": "Backend"
    }

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportRequest.model_validate(valid_request_data)

    assert any(error["type"] == "extra_forbidden" for error in exc_info.value.errors())


def test_user_provided_role_rejects_github_evidence_fields(
    valid_request_data: dict[str, Any],
) -> None:
    valid_request_data["repositories"][0]["userProvidedRole"]["githubEvidence"] = {
        "path": "build.gradle"
    }

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportRequest.model_validate(valid_request_data)

    assert any(error["type"] == "extra_forbidden" for error in exc_info.value.errors())


def test_github_evidence_type_only_accepts_github(
    valid_request_data: dict[str, Any],
) -> None:
    valid_request_data["repositories"][0]["githubEvidence"]["techStacks"][0]["evidence"][0][
        "type"
    ] = "USER_PROVIDED"

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportRequest.model_validate(valid_request_data)

    assert exc_info.value.errors()[0]["type"] == "literal_error"


def test_invalid_enum_is_rejected(valid_request_data: dict[str, Any]) -> None:
    valid_request_data["targetJob"] = "DATA"

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportRequest.model_validate(valid_request_data)

    assert exc_info.value.errors()[0]["type"] == "enum"


@pytest.mark.parametrize(
    "required_field",
    ["schemaVersion", "analysisId", "targetJob", "analysisPurpose", "repositories"],
)
def test_missing_required_top_level_fields_are_rejected(
    valid_request_data: dict[str, Any], required_field: str
) -> None:
    valid_request_data.pop(required_field)

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportRequest.model_validate(valid_request_data)

    assert exc_info.value.errors()[0]["type"] == "missing"


def test_missing_required_repository_field_is_rejected(
    valid_request_data: dict[str, Any],
) -> None:
    valid_request_data["repositories"][0].pop("githubEvidence")

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportRequest.model_validate(valid_request_data)

    assert exc_info.value.errors()[0]["type"] == "missing"


def test_user_provided_role_can_be_omitted(valid_request_data: dict[str, Any]) -> None:
    valid_request_data["repositories"][0].pop("userProvidedRole")

    request = PortfolioReportRequest.model_validate(valid_request_data)

    assert request.repositories[0].user_provided_role is None
