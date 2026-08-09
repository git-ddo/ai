import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from app.schemas.common import EvidenceType, Priority, TargetJob
from app.schemas.response import PortfolioReportResponse

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_json_fixture(filename: str) -> dict[str, Any]:
    with (FIXTURES_DIR / filename).open(encoding="utf-8") as fixture_file:
        raw_data: object = json.load(fixture_file)

    if not isinstance(raw_data, dict):
        raise TypeError("Response fixture must contain a JSON object")

    return cast(dict[str, Any], raw_data)


@pytest.fixture
def valid_response_data() -> dict[str, Any]:
    return load_json_fixture("valid_portfolio_report_response.json")


def test_valid_response_fixture_matches_contract(valid_response_data: dict[str, Any]) -> None:
    response = PortfolioReportResponse.model_validate(valid_response_data)

    assert response.schema_version == "1.0"
    assert response.analysis_id == 123
    assert response.overall_diagnosis.strengths[0].evidence_type is EvidenceType.GITHUB
    assert response.representative_projects[0].repository_name == "festival-order-service"
    assert response.job_appeal.target_job is TargetJob.BACKEND
    assert response.roadmap[0].priority is Priority.HIGH
    assert response.model_dump(mode="json", by_alias=True)["overallDiagnosis"]["summary"]


def test_invalid_response_fixture_is_rejected() -> None:
    invalid_data = load_json_fixture("invalid_portfolio_report_response.json")

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(invalid_data)


def test_schema_version_only_accepts_version_1_0(valid_response_data: dict[str, Any]) -> None:
    valid_response_data["schemaVersion"] = "2.0"

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportResponse.model_validate(valid_response_data)

    assert exc_info.value.errors()[0]["type"] == "literal_error"


@pytest.mark.parametrize("repository_count", [1, 5])
def test_repository_report_count_accepts_boundaries(
    valid_response_data: dict[str, Any], repository_count: int
) -> None:
    repository_report = valid_response_data["repositoryReports"][0]
    valid_response_data["repositoryReports"] = [
        deepcopy(repository_report) for _ in range(repository_count)
    ]

    response = PortfolioReportResponse.model_validate(valid_response_data)

    assert len(response.repository_reports) == repository_count


@pytest.mark.parametrize("repository_count", [0, 6])
def test_repository_report_count_rejects_out_of_range_values(
    valid_response_data: dict[str, Any], repository_count: int
) -> None:
    repository_report = valid_response_data["repositoryReports"][0]
    valid_response_data["repositoryReports"] = [
        deepcopy(repository_report) for _ in range(repository_count)
    ]

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


def test_representative_project_is_required(valid_response_data: dict[str, Any]) -> None:
    valid_response_data["representativeProjects"] = []

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportResponse.model_validate(valid_response_data)

    assert exc_info.value.errors()[0]["type"] == "too_short"


def test_finding_requires_evidence(valid_response_data: dict[str, Any]) -> None:
    valid_response_data["overallDiagnosis"]["strengths"][0]["evidence"] = []

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportResponse.model_validate(valid_response_data)

    assert exc_info.value.errors()[0]["type"] == "too_short"


def test_invalid_evidence_type_is_rejected(valid_response_data: dict[str, Any]) -> None:
    valid_response_data["overallDiagnosis"]["strengths"][0]["evidenceType"] = "SYSTEM"

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportResponse.model_validate(valid_response_data)

    assert exc_info.value.errors()[0]["type"] == "enum"


def test_invalid_target_job_is_rejected(valid_response_data: dict[str, Any]) -> None:
    valid_response_data["jobAppeal"]["targetJob"] = "DATA"

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportResponse.model_validate(valid_response_data)

    assert exc_info.value.errors()[0]["type"] == "enum"


def test_invalid_roadmap_priority_is_rejected(valid_response_data: dict[str, Any]) -> None:
    valid_response_data["roadmap"][0]["priority"] = "URGENT"

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportResponse.model_validate(valid_response_data)

    assert exc_info.value.errors()[0]["type"] == "enum"


def test_roadmap_item_requires_action(valid_response_data: dict[str, Any]) -> None:
    valid_response_data["roadmap"][0]["actions"] = []

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportResponse.model_validate(valid_response_data)

    assert exc_info.value.errors()[0]["type"] == "too_short"


@pytest.mark.parametrize("required_section", ["roadmap", "interviewQuestions"])
def test_generated_sections_require_at_least_one_item(
    valid_response_data: dict[str, Any], required_section: str
) -> None:
    valid_response_data[required_section] = []

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportResponse.model_validate(valid_response_data)

    assert exc_info.value.errors()[0]["type"] == "too_short"


@pytest.mark.parametrize("required_list", ["answerGuide", "evidence"])
def test_interview_question_requires_guidance_and_evidence(
    valid_response_data: dict[str, Any], required_list: str
) -> None:
    valid_response_data["interviewQuestions"][0][required_list] = []

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportResponse.model_validate(valid_response_data)

    assert exc_info.value.errors()[0]["type"] == "too_short"


def test_limitations_are_required(valid_response_data: dict[str, Any]) -> None:
    valid_response_data["limitations"] = []

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportResponse.model_validate(valid_response_data)

    assert exc_info.value.errors()[0]["type"] == "too_short"


@pytest.mark.parametrize(
    "required_field",
    [
        "schemaVersion",
        "analysisId",
        "overallDiagnosis",
        "representativeProjects",
        "repositoryReports",
        "jobAppeal",
        "roadmap",
        "interviewQuestions",
        "portfolioStatements",
        "limitations",
    ],
)
def test_missing_required_top_level_fields_are_rejected(
    valid_response_data: dict[str, Any], required_field: str
) -> None:
    valid_response_data.pop(required_field)

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportResponse.model_validate(valid_response_data)

    assert exc_info.value.errors()[0]["type"] == "missing"


def test_blank_required_text_is_rejected(valid_response_data: dict[str, Any]) -> None:
    valid_response_data["overallDiagnosis"]["summary"] = "   "

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportResponse.model_validate(valid_response_data)

    assert exc_info.value.errors()[0]["type"] == "string_too_short"


def test_unknown_fields_are_rejected(valid_response_data: dict[str, Any]) -> None:
    valid_response_data["generatedBy"] = "gemini"

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportResponse.model_validate(valid_response_data)

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"
