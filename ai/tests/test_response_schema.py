import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.schemas.common import (
    AnalysisDepth,
    Confidence,
    FindingCategory,
    FindingSeverity,
    LimitationCode,
)
from app.schemas.response import PortfolioReportResponse

BACKEND_CONTRACT_COMMIT = "9d9fc7caf36150bc090c7a5b9bad62ce33743fc3"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "contracts" / "backend_contract"
EXAMPLE_FILES = {
    AnalysisDepth.P0: "analysis-response.p0.example.json",
    AnalysisDepth.P1: "analysis-response.p1.example.json",
    AnalysisDepth.P2: "analysis-response.p2.example.json",
}


def load_example(depth: AnalysisDepth = AnalysisDepth.P0) -> dict[str, Any]:
    with (FIXTURES_DIR / EXAMPLE_FILES[depth]).open(encoding="utf-8") as fixture_file:
        raw_data: object = json.load(fixture_file)

    if not isinstance(raw_data, dict):
        raise TypeError("Response fixture must contain a JSON object")
    return cast(dict[str, Any], raw_data)


@pytest.fixture
def valid_response_data() -> dict[str, Any]:
    return load_example()


@pytest.mark.parametrize("depth", list(AnalysisDepth))
def test_backend_examples_parse_and_round_trip(depth: AnalysisDepth) -> None:
    raw_data = load_example(depth)

    response = PortfolioReportResponse.model_validate(raw_data)

    assert response.requested_analysis_depth is depth
    assert response.model_dump(mode="json", by_alias=True) == raw_data


def test_response_exposes_typed_contract_values(valid_response_data: dict[str, Any]) -> None:
    response = PortfolioReportResponse.model_validate(valid_response_data)
    finding = response.repositories[0].findings[0]

    assert response.schema_version == "1.1"
    assert response.analysis_id == UUID("11111111-1111-4111-8111-111111111111")
    assert finding.category is FindingCategory.DOCUMENTATION
    assert finding.severity is FindingSeverity.POSITIVE
    assert finding.confidence is Confidence.HIGH
    assert response.limitations[0].code is LimitationCode.P0_ONLY


def test_python_field_names_are_accepted(valid_response_data: dict[str, Any]) -> None:
    response = PortfolioReportResponse.model_validate(valid_response_data)

    reparsed = PortfolioReportResponse.model_validate(response.model_dump())

    assert reparsed == response


def test_schema_version_only_accepts_version_1_1(valid_response_data: dict[str, Any]) -> None:
    valid_response_data["schemaVersion"] = "1.0"

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportResponse.model_validate(valid_response_data)

    assert exc_info.value.errors()[0]["type"] == "literal_error"


def test_invalid_analysis_id_is_rejected(valid_response_data: dict[str, Any]) -> None:
    valid_response_data["analysisId"] = "not-a-uuid"

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


@pytest.mark.parametrize(
    "required_field",
    [
        "schemaVersion",
        "analysisId",
        "evaluatorVersion",
        "requestedAnalysisDepth",
        "usedEvidenceLevels",
        "summary",
        "repositories",
        "coaching",
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


@pytest.mark.parametrize(
    ("container_path", "unknown_field"),
    [
        ((), "generatedBy"),
        (("repositories", 0), "completedEvidenceLevels"),
        (("repositories", 0, "findings", 0), "criterionKeys"),
        (("coaching",), "roadmap"),
        (("coaching", "portfolioStatements", 0), "type"),
        (("coaching", "interviewQuestions", 0), "repositoryId"),
    ],
)
def test_unknown_fields_are_rejected(
    valid_response_data: dict[str, Any],
    container_path: tuple[str | int, ...],
    unknown_field: str,
) -> None:
    container: Any = valid_response_data
    for part in container_path:
        container = container[part]
    container[unknown_field] = "unexpected"

    with pytest.raises(ValidationError) as exc_info:
        PortfolioReportResponse.model_validate(valid_response_data)

    assert any(error["type"] == "extra_forbidden" for error in exc_info.value.errors())


@pytest.mark.parametrize("field", ["evaluatorVersion", "summary"])
def test_empty_top_level_text_is_rejected(valid_response_data: dict[str, Any], field: str) -> None:
    valid_response_data[field] = ""

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


@pytest.mark.parametrize("field", ["evaluatorVersion", "summary"])
def test_whitespace_text_is_not_rejected_beyond_json_schema(
    valid_response_data: dict[str, Any], field: str
) -> None:
    valid_response_data[field] = " "

    response = PortfolioReportResponse.model_validate(valid_response_data)

    assert getattr(response, {"evaluatorVersion": "evaluator_version", "summary": "summary"}[field])


def test_used_evidence_levels_must_not_be_empty(valid_response_data: dict[str, Any]) -> None:
    valid_response_data["usedEvidenceLevels"] = []

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


@pytest.mark.parametrize("repository_count", [1, 5])
def test_repository_count_accepts_boundaries(
    valid_response_data: dict[str, Any], repository_count: int
) -> None:
    repository = valid_response_data["repositories"][0]
    valid_response_data["repositories"] = [deepcopy(repository) for _ in range(repository_count)]

    response = PortfolioReportResponse.model_validate(valid_response_data)

    assert len(response.repositories) == repository_count


@pytest.mark.parametrize("repository_count", [0, 6])
def test_repository_count_rejects_out_of_range_values(
    valid_response_data: dict[str, Any], repository_count: int
) -> None:
    repository = valid_response_data["repositories"][0]
    valid_response_data["repositories"] = [deepcopy(repository) for _ in range(repository_count)]

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


@pytest.mark.parametrize("depth", list(AnalysisDepth))
def test_all_analysis_depths_are_shape_valid(
    valid_response_data: dict[str, Any], depth: AnalysisDepth
) -> None:
    valid_response_data["requestedAnalysisDepth"] = depth.value
    valid_response_data["usedEvidenceLevels"] = [depth.value]

    response = PortfolioReportResponse.model_validate(valid_response_data)

    assert response.requested_analysis_depth is depth
    assert response.used_evidence_levels == [depth]


def test_used_evidence_levels_order_and_duplicates_are_not_semantically_validated(
    valid_response_data: dict[str, Any],
) -> None:
    valid_response_data["usedEvidenceLevels"] = ["P2", "P0", "P2"]

    response = PortfolioReportResponse.model_validate(valid_response_data)

    assert response.used_evidence_levels == [AnalysisDepth.P2, AnalysisDepth.P0, AnalysisDepth.P2]


@pytest.mark.parametrize(
    "required_field",
    ["repositoryId", "repositoryFullName", "snapshotHashAlgorithm", "snapshotSha", "findings"],
)
def test_missing_repository_fields_are_rejected(
    valid_response_data: dict[str, Any], required_field: str
) -> None:
    valid_response_data["repositories"][0].pop(required_field)

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


def test_invalid_snapshot_hash_algorithm_is_rejected(
    valid_response_data: dict[str, Any],
) -> None:
    valid_response_data["repositories"][0]["snapshotHashAlgorithm"] = "MD5"

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


@pytest.mark.parametrize("finding_id", ["find_12", "finding_001", "find-a"])
def test_invalid_finding_id_is_rejected(
    valid_response_data: dict[str, Any], finding_id: str
) -> None:
    valid_response_data["repositories"][0]["findings"][0]["findingId"] = finding_id

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("category", "SECURITY"),
        ("severity", "WARNING"),
        ("confidence", "NOT_VERIFIABLE"),
    ],
)
def test_invalid_finding_enum_is_rejected(
    valid_response_data: dict[str, Any], field: str, invalid_value: str
) -> None:
    valid_response_data["repositories"][0]["findings"][0][field] = invalid_value

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


@pytest.mark.parametrize("field", ["title", "detail"])
def test_empty_finding_text_is_rejected(valid_response_data: dict[str, Any], field: str) -> None:
    valid_response_data["repositories"][0]["findings"][0][field] = ""

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


def test_finding_allows_empty_reference_arrays(valid_response_data: dict[str, Any]) -> None:
    finding = valid_response_data["repositories"][0]["findings"][0]
    finding["evidenceRefs"] = []
    finding["claimRefs"] = []

    response = PortfolioReportResponse.model_validate(valid_response_data)

    assert response.repositories[0].findings[0].evidence_refs == []
    assert response.repositories[0].findings[0].claim_refs == []


@pytest.mark.parametrize("file_path", ["/etc/passwd", "src/../secret.txt", "file..txt", ""])
def test_invalid_repository_file_path_is_rejected(
    valid_response_data: dict[str, Any], file_path: str
) -> None:
    valid_response_data["repositories"][0]["findings"][0]["filePaths"] = [file_path]

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


@pytest.mark.parametrize(
    "file_path", ["README.md", "src/main/App.java", ".github/workflows/ci.yml"]
)
def test_repository_relative_file_path_is_allowed(
    valid_response_data: dict[str, Any], file_path: str
) -> None:
    valid_response_data["repositories"][0]["findings"][0]["filePaths"] = [file_path]

    response = PortfolioReportResponse.model_validate(valid_response_data)

    assert response.repositories[0].findings[0].file_paths == [file_path]


@pytest.mark.parametrize("section", ["strengths", "gaps", "nextActions"])
def test_coaching_items_require_evidence(valid_response_data: dict[str, Any], section: str) -> None:
    valid_response_data["coaching"][section][0]["evidenceRefs"] = []

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


def test_job_appeal_requires_evidence(valid_response_data: dict[str, Any]) -> None:
    valid_response_data["coaching"]["jobAppeal"]["evidenceRefs"] = []

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


def test_coaching_arrays_can_be_empty(valid_response_data: dict[str, Any]) -> None:
    coaching = valid_response_data["coaching"]
    coaching["strengths"] = []
    coaching["gaps"] = []
    coaching["nextActions"] = []
    coaching["portfolioStatements"] = []
    coaching["interviewQuestions"] = []

    response = PortfolioReportResponse.model_validate(valid_response_data)

    assert response.coaching.strengths == []
    assert response.coaching.portfolio_statements == []


def test_unknown_but_well_formed_evidence_ref_is_shape_valid(
    valid_response_data: dict[str, Any],
) -> None:
    valid_response_data["coaching"]["jobAppeal"]["evidenceRefs"] = ["ev_999"]

    response = PortfolioReportResponse.model_validate(valid_response_data)

    assert response.coaching.job_appeal.evidence_refs == ["ev_999"]


@pytest.mark.parametrize(
    ("evidence_refs", "claim_refs"),
    [
        (["ev_001"], []),
        ([], ["claim_001"]),
        (["ev_001"], ["claim_001"]),
    ],
)
def test_portfolio_statement_accepts_at_least_one_reference_type(
    valid_response_data: dict[str, Any], evidence_refs: list[str], claim_refs: list[str]
) -> None:
    statement = valid_response_data["coaching"]["portfolioStatements"][0]
    statement["evidenceRefs"] = evidence_refs
    statement["claimRefs"] = claim_refs

    response = PortfolioReportResponse.model_validate(valid_response_data)

    assert response.coaching.portfolio_statements[0].evidence_refs == evidence_refs
    assert response.coaching.portfolio_statements[0].claim_refs == claim_refs


def test_portfolio_statement_rejects_missing_references(
    valid_response_data: dict[str, Any],
) -> None:
    statement = valid_response_data["coaching"]["portfolioStatements"][0]
    statement["evidenceRefs"] = []
    statement["claimRefs"] = []

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


@pytest.mark.parametrize(
    ("field", "invalid_ref"),
    [("evidenceRefs", "ev_12"), ("claimRefs", "claim_12")],
)
def test_portfolio_statement_rejects_invalid_reference_pattern(
    valid_response_data: dict[str, Any], field: str, invalid_ref: str
) -> None:
    valid_response_data["coaching"]["portfolioStatements"][0][field] = [invalid_ref]

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


def test_portfolio_statement_rejects_empty_text(valid_response_data: dict[str, Any]) -> None:
    valid_response_data["coaching"]["portfolioStatements"][0]["text"] = ""

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


@pytest.mark.parametrize(
    ("evidence_refs", "claim_refs"),
    [
        (["ev_001"], []),
        ([], ["claim_001"]),
        (["ev_001"], ["claim_001"]),
    ],
)
def test_interview_question_accepts_at_least_one_reference_type(
    valid_response_data: dict[str, Any], evidence_refs: list[str], claim_refs: list[str]
) -> None:
    question = valid_response_data["coaching"]["interviewQuestions"][0]
    question["evidenceRefs"] = evidence_refs
    question["claimRefs"] = claim_refs

    response = PortfolioReportResponse.model_validate(valid_response_data)

    assert response.coaching.interview_questions[0].evidence_refs == evidence_refs
    assert response.coaching.interview_questions[0].claim_refs == claim_refs


def test_interview_question_rejects_missing_references(
    valid_response_data: dict[str, Any],
) -> None:
    question = valid_response_data["coaching"]["interviewQuestions"][0]
    question["evidenceRefs"] = []
    question["claimRefs"] = []

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


def test_interview_question_requires_answer_guide(valid_response_data: dict[str, Any]) -> None:
    valid_response_data["coaching"]["interviewQuestions"][0]["answerGuide"] = []

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


@pytest.mark.parametrize("field", ["answerGuide", "followUpQuestions"])
def test_interview_question_rejects_empty_list_item(
    valid_response_data: dict[str, Any], field: str
) -> None:
    valid_response_data["coaching"]["interviewQuestions"][0][field] = [""]

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


def test_interview_question_allows_empty_follow_up_questions(
    valid_response_data: dict[str, Any],
) -> None:
    valid_response_data["coaching"]["interviewQuestions"][0]["followUpQuestions"] = []

    response = PortfolioReportResponse.model_validate(valid_response_data)

    assert response.coaching.interview_questions[0].follow_up_questions == []


@pytest.mark.parametrize("field", ["question", "intent"])
def test_interview_question_rejects_empty_required_text(
    valid_response_data: dict[str, Any], field: str
) -> None:
    valid_response_data["coaching"]["interviewQuestions"][0][field] = ""

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


@pytest.mark.parametrize("limitation_code", list(LimitationCode))
def test_all_limitation_codes_are_allowed(
    valid_response_data: dict[str, Any], limitation_code: LimitationCode
) -> None:
    valid_response_data["limitations"][0]["code"] = limitation_code.value

    response = PortfolioReportResponse.model_validate(valid_response_data)

    assert response.limitations[0].code is limitation_code


def test_unknown_limitation_code_is_rejected(valid_response_data: dict[str, Any]) -> None:
    valid_response_data["limitations"][0]["code"] = "COLLECTION_WARNING"

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


def test_empty_limitation_message_is_rejected(valid_response_data: dict[str, Any]) -> None:
    valid_response_data["limitations"][0]["message"] = ""

    with pytest.raises(ValidationError):
        PortfolioReportResponse.model_validate(valid_response_data)


def test_limitations_can_be_empty(valid_response_data: dict[str, Any]) -> None:
    valid_response_data["limitations"] = []

    response = PortfolioReportResponse.model_validate(valid_response_data)

    assert response.limitations == []


def test_duplicate_finding_ids_remain_semantic_validation(
    valid_response_data: dict[str, Any],
) -> None:
    duplicate_repository = deepcopy(valid_response_data["repositories"][0])
    duplicate_repository["repositoryId"] = "456"
    duplicate_repository["repositoryFullName"] = "git-ddo/another"
    valid_response_data["repositories"].append(duplicate_repository)

    response = PortfolioReportResponse.model_validate(valid_response_data)

    assert response.repositories[0].findings[0].finding_id == "find_001"
    assert response.repositories[1].findings[0].finding_id == "find_001"


def test_depth_and_finding_category_mismatch_remains_semantic_validation(
    valid_response_data: dict[str, Any],
) -> None:
    valid_response_data["usedEvidenceLevels"] = ["P0"]
    valid_response_data["repositories"][0]["findings"][0]["category"] = "CODE_QUALITY"

    response = PortfolioReportResponse.model_validate(valid_response_data)

    assert response.repositories[0].findings[0].category is FindingCategory.CODE_QUALITY


def test_wire_response_does_not_convert_to_internal_models(
    valid_response_data: dict[str, Any],
) -> None:
    response = PortfolioReportResponse.model_validate(valid_response_data)

    assert not hasattr(response, "to_internal")
    assert not hasattr(response, "to_wire")
