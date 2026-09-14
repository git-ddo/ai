import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from app.core.exceptions import (
    RequestMappingError,
    UnsupportedAnalysisCombinationError,
)
from app.domain import (
    AnalysisDepth as InternalAnalysisDepth,
)
from app.domain import (
    EvidenceValueType as InternalEvidenceValueType,
)
from app.domain import (
    InternalEvidenceType,
    InternalPortfolioInput,
)
from app.domain import (
    SnapshotHashAlgorithm as InternalSnapshotHashAlgorithm,
)
from app.mappers import RequestWireMapper
from app.schemas.common import AnalysisDepth as WireAnalysisDepth
from app.schemas.request import PortfolioReportRequest
from app.services import NormalizationService
from app.validators import AnalysisDepthValidator, EvidenceReferenceValidator

BACKEND_CONTRACT_COMMIT = "9d9fc7caf36150bc090c7a5b9bad62ce33743fc3"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "contracts" / "backend_contract"


def load_example(depth: WireAnalysisDepth = WireAnalysisDepth.P0) -> dict[str, Any]:
    path = FIXTURES_DIR / f"analysis-request.{depth.value.casefold()}.example.json"
    with path.open(encoding="utf-8") as fixture_file:
        raw_data: object = json.load(fixture_file)

    if not isinstance(raw_data, dict):
        raise TypeError("Request fixture must contain a JSON object")
    return cast(dict[str, Any], raw_data)


def map_data(data: dict[str, Any]) -> InternalPortfolioInput:
    request = PortfolioReportRequest.model_validate(data)
    return RequestWireMapper().to_internal(request)


def configure_single_evidence(
    data: dict[str, Any],
    *,
    evidence_type: str,
    depth: WireAnalysisDepth,
    value_type: str = "STRING",
) -> dict[str, Any]:
    repository = data["repositories"][0]
    repository["completedEvidenceLevels"] = {
        WireAnalysisDepth.P0: ["P0"],
        WireAnalysisDepth.P1: ["P0", "P1"],
        WireAnalysisDepth.P2: ["P0", "P1", "P2"],
    }[depth]
    data["requestedAnalysisDepth"] = depth.value
    evidence = repository["evidence"][0]
    evidence.update(
        {
            "evidenceType": evidence_type,
            "analysisDepth": depth.value,
            "valueType": value_type,
            "derivedFromLevel": depth.value if evidence_type == "BACKEND_DERIVED" else None,
        }
    )
    if evidence_type == "CODE_EVIDENCE":
        evidence.update(
            {
                "factKey": "CODE_SNIPPET",
                "path": "src/main/App.java",
                "startLine": 1,
                "endLine": 3,
                "commitSha": "abc123",
                "sourceEvidenceRefs": ["ev_999"],
            }
        )
    else:
        evidence.update(
            {
                "startLine": None,
                "endLine": None,
                "sourceEvidenceRefs": [],
            }
        )
    return data


def add_second_repository(data: dict[str, Any]) -> None:
    second = deepcopy(data["repositories"][0])
    second["repositoryId"] = "456"
    second["repositoryFullName"] = "git-ddo/second"
    evidence_id_map: dict[str, str] = {}
    for index, evidence in enumerate(second["evidence"], start=101):
        old_id = evidence["evidenceId"]
        new_id = f"ev_{index:03d}"
        evidence_id_map[old_id] = new_id
        evidence["evidenceId"] = new_id
        evidence["repositoryId"] = second["repositoryId"]
        evidence["repositoryFullName"] = second["repositoryFullName"]
    for evidence in second["evidence"]:
        evidence["sourceEvidenceRefs"] = [
            evidence_id_map.get(reference, reference)
            for reference in evidence["sourceEvidenceRefs"]
        ]
    for index, claim in enumerate(second["userClaims"], start=101):
        claim["claimId"] = f"claim_{index:03d}"
        claim["relatedEvidenceRefs"] = [
            evidence_id_map.get(reference, reference) for reference in claim["relatedEvidenceRefs"]
        ]
    data["repositories"].append(second)


def add_technology_evidence(
    data: dict[str, Any],
    *,
    evidence_id: str = "ev_900",
    value: str = "SpringBoot",
    source_evidence_id: str = "ev_001",
) -> dict[str, Any]:
    repository = data["repositories"][0]
    source = next(
        evidence
        for evidence in repository["evidence"]
        if evidence["evidenceId"] == source_evidence_id
    )
    source.update(
        {
            "evidenceType": "GITHUB_STATIC",
            "analysisDepth": "P0",
            "factKey": "BUILD_MANIFEST",
            "valueType": "STRING",
            "value": "Backend build manifest",
            "path": "build.gradle",
            "startLine": None,
            "endLine": None,
            "sourceEvidenceRefs": [],
            "derivedFromLevel": None,
        }
    )
    technology = deepcopy(source)
    technology.update(
        {
            "evidenceId": evidence_id,
            "evidenceType": "BACKEND_DERIVED",
            "analysisDepth": "P0",
            "factKey": "TECHNOLOGY_DETECTED",
            "valueType": "STRING",
            "value": value,
            "path": None,
            "commitSha": None,
            "sourceEvidenceRefs": [source_evidence_id],
            "derivedFromLevel": "P0",
        }
    )
    repository["evidence"].append(technology)
    return technology


@pytest.mark.parametrize("depth", list(WireAnalysisDepth))
def test_backend_examples_map_to_internal_portfolio(depth: WireAnalysisDepth) -> None:
    result = map_data(load_example(depth))
    EvidenceReferenceValidator().validate(result)
    AnalysisDepthValidator().validate(result)

    assert result.requested_analysis_depth is InternalAnalysisDepth(depth.value)
    assert result.repositories[0].analysis_depth is InternalAnalysisDepth(depth.value)


def test_maps_repository_fields_and_completed_levels() -> None:
    result = map_data(load_example(WireAnalysisDepth.P2))
    repository = result.repositories[0]

    assert repository.repository_id == "123"
    assert repository.repository_full_name == "git-ddo/backend"
    assert repository.description is None
    assert repository.snapshot_hash_algorithm is InternalSnapshotHashAlgorithm.SHA1
    assert repository.snapshot_sha == "commit-sha"
    assert repository.completed_evidence_levels == (
        InternalAnalysisDepth.P0,
        InternalAnalysisDepth.P1,
        InternalAnalysisDepth.P2,
    )


def test_preserves_repository_evidence_and_claim_order() -> None:
    data = load_example(WireAnalysisDepth.P1)
    add_second_repository(data)

    result = map_data(data)

    assert [item.repository_id for item in result.repositories] == ["123", "456"]
    assert [item.evidence_id for item in result.repositories[0].evidence] == [
        "ev_001",
        "ev_002",
        "ev_003",
        "ev_004",
    ]
    assert [item.claim_id for item in result.repositories[1].user_claims] == ["claim_101"]


@pytest.mark.parametrize(
    ("wire_type", "depth", "internal_type"),
    [
        ("GITHUB_STATIC", WireAnalysisDepth.P0, InternalEvidenceType.GITHUB_STATIC),
        ("GITHUB_ACTIVITY", WireAnalysisDepth.P1, InternalEvidenceType.GITHUB_ACTIVITY),
        ("CODE_EVIDENCE", WireAnalysisDepth.P2, InternalEvidenceType.CODE_EVIDENCE),
        ("BACKEND_DERIVED", WireAnalysisDepth.P0, InternalEvidenceType.BACKEND_DERIVED),
    ],
)
def test_maps_all_evidence_types(
    wire_type: str,
    depth: WireAnalysisDepth,
    internal_type: InternalEvidenceType,
) -> None:
    data = configure_single_evidence(
        load_example(),
        evidence_type=wire_type,
        depth=depth,
    )

    result = map_data(data)

    assert result.repositories[0].evidence[0].evidence_type is internal_type


@pytest.mark.parametrize("value_type", list(InternalEvidenceValueType))
def test_maps_all_evidence_value_types(value_type: InternalEvidenceValueType) -> None:
    data = configure_single_evidence(
        load_example(),
        evidence_type="GITHUB_STATIC",
        depth=WireAnalysisDepth.P0,
        value_type=value_type.value,
    )

    result = map_data(data)

    assert result.repositories[0].evidence[0].value_type is value_type


def test_maps_evidence_content_path_and_internal_defaults_without_inference() -> None:
    data = load_example()
    wire_evidence = data["repositories"][0]["evidence"][0]
    wire_evidence["factKey"] = "BUILD_MANIFEST"
    wire_evidence["value"] = "Spring Boot dependency"
    wire_evidence["path"] = "build.gradle"

    evidence = map_data(data).repositories[0].evidence[0]

    assert evidence.key == "BUILD_MANIFEST"
    assert evidence.summary == "Spring Boot dependency"
    assert evidence.path == "build.gradle"
    assert evidence.source_paths == ("build.gradle",)
    assert evidence.technology_names == ()


def test_does_not_promote_technology_names_from_readme_text() -> None:
    data = load_example()
    data["repositories"][0]["evidence"][0]["value"] = "Spring Boot, MySQL, Redis"

    evidence = map_data(data).repositories[0].evidence[0]

    assert evidence.key == "README"
    assert evidence.technology_names == ()


def test_maps_only_backend_derived_technology_evidence_to_technology_names() -> None:
    data = load_example()
    add_technology_evidence(data)

    result = map_data(data)
    EvidenceReferenceValidator().validate(result)
    AnalysisDepthValidator().validate(result)

    technology = result.repositories[0].evidence[-1]
    assert technology.key == "TECHNOLOGY_DETECTED"
    assert technology.technology_names == ("SpringBoot",)


def test_normalizes_aliases_deduplicates_and_aggregates_derived_technologies() -> None:
    data = load_example()
    add_technology_evidence(data, evidence_id="ev_900", value="SpringBoot")
    add_technology_evidence(data, evidence_id="ev_901", value="spring-boot")
    add_technology_evidence(data, evidence_id="ev_902", value="mysql")
    add_technology_evidence(data, evidence_id="ev_903", value="Redis")

    repository = map_data(data).repositories[0]
    context = NormalizationService().normalize(repository)

    assert context.technology_names == ("MySQL", "Redis", "Spring Boot")
    assert context.evidence[-1].technology_names == ("Redis",)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evidenceType", "GITHUB_STATIC"),
        ("analysisDepth", "P1"),
        ("valueType", "INTEGER"),
        ("derivedFromLevel", "P1"),
        ("value", "   "),
        ("sourceEvidenceRefs", []),
    ],
)
def test_rejects_invalid_technology_evidence_contract(field: str, value: object) -> None:
    data = load_example(WireAnalysisDepth.P1)
    technology = add_technology_evidence(data)
    technology[field] = value

    with pytest.raises(RequestMappingError, match="Technology Evidence contract mismatch"):
        map_data(data)


@pytest.mark.parametrize(
    ("evidence_type", "analysis_depth", "fact_key"),
    [
        ("GITHUB_STATIC", "P0", "README"),
        ("GITHUB_ACTIVITY", "P1", "COMMIT_SUMMARY"),
        ("CODE_EVIDENCE", "P2", "CODE_SNIPPET"),
        ("BACKEND_DERIVED", "P0", "BUILD_MANIFEST"),
    ],
)
def test_rejects_invalid_technology_source_contract(
    evidence_type: str,
    analysis_depth: str,
    fact_key: str,
) -> None:
    requested_depth = WireAnalysisDepth.P2 if analysis_depth == "P2" else WireAnalysisDepth.P1
    data = load_example(requested_depth)
    add_technology_evidence(data)
    source = data["repositories"][0]["evidence"][0]
    source.update(
        {
            "evidenceType": evidence_type,
            "analysisDepth": analysis_depth,
            "factKey": fact_key,
            "derivedFromLevel": "P0" if evidence_type == "BACKEND_DERIVED" else None,
        }
    )
    if evidence_type == "CODE_EVIDENCE":
        source.update(
            {
                "path": "src/App.java",
                "startLine": 1,
                "endLine": 1,
                "commitSha": "abc123",
                "sourceEvidenceRefs": ["ev_002"],
            }
        )

    with pytest.raises(RequestMappingError, match="Technology Evidence source contract mismatch"):
        map_data(data)


def test_shared_reference_validator_rejects_unknown_technology_source() -> None:
    data = load_example()
    technology = add_technology_evidence(data)
    technology["sourceEvidenceRefs"] = ["ev_999"]
    result = map_data(data)

    with pytest.raises(ValueError, match="UNKNOWN_SOURCE_EVIDENCE_REF"):
        EvidenceReferenceValidator().validate(result)


def test_shared_reference_validator_rejects_cross_repository_technology_source() -> None:
    data = load_example()
    technology = add_technology_evidence(data)
    add_second_repository(data)
    technology["sourceEvidenceRefs"] = ["ev_101"]
    result = map_data(data)

    with pytest.raises(ValueError, match="CROSS_REPOSITORY_REF"):
        EvidenceReferenceValidator().validate(result)


def test_evidence_without_path_has_no_source_paths() -> None:
    data = load_example()
    data["repositories"][0]["evidence"][0]["path"] = None

    evidence = map_data(data).repositories[0].evidence[0]

    assert evidence.path is None
    assert evidence.source_paths == ()


def test_maps_backend_p1_changed_file_list_to_source_paths() -> None:
    evidence = map_data(load_example(WireAnalysisDepth.P1)).repositories[0].evidence[2]

    assert evidence.key == "CHANGED_FILES"
    assert evidence.path is None
    assert evidence.source_paths == ("src/AuthFilter.java",)


def test_maps_multiple_unique_p1_file_paths_in_wire_order() -> None:
    data = load_example(WireAnalysisDepth.P1)
    evidence = data["repositories"][0]["evidence"][2]
    evidence["value"] = (
        "sha=abc123\nfiles:\n"
        "modified\tsrc/AuthFilter.java\t+20/-1\n"
        "added\tsrc/AuthConfig.java\t+10/-0\n"
        "modified\tsrc/AuthFilter.java\t+2/-1"
    )

    internal = map_data(data).repositories[0].evidence[2]

    assert internal.source_paths == (
        "src/AuthFilter.java",
        "src/AuthConfig.java",
    )


def test_maps_p1_pull_request_file_list_to_source_paths() -> None:
    data = load_example(WireAnalysisDepth.P1)
    evidence = data["repositories"][0]["evidence"][3]
    evidence["value"] = (
        "number=12\ntitle=Add auth filter\nfiles:\nadded\tsrc/AuthFilter.java\t+20/-1"
    )

    internal = map_data(data).repositories[0].evidence[3]

    assert internal.key == "PULL_REQUEST"
    assert internal.source_paths == ("src/AuthFilter.java",)


def test_skips_malformed_and_unsafe_p1_file_list_entries() -> None:
    data = load_example(WireAnalysisDepth.P1)
    evidence = data["repositories"][0]["evidence"][2]
    evidence["value"] = (
        "sha=abc123\nfiles:\n"
        "modified\tsrc/Safe.java\t+1/-1\n"
        "missing-tabs\n"
        "added\t../secret.env\t+1/-0\n"
        "added\t/absolute/path.java\t+1/-0\n"
        "added\tsrc\\windows.java\t+1/-0"
    )

    internal = map_data(data).repositories[0].evidence[2]

    assert internal.source_paths == ("src/Safe.java",)


def test_does_not_parse_file_like_text_from_unrelated_evidence() -> None:
    data = load_example(WireAnalysisDepth.P1)
    evidence = data["repositories"][0]["evidence"][1]
    evidence["value"] = "message=files:\nadded\tsrc/AuthFilter.java\t+20/-1"

    internal = map_data(data).repositories[0].evidence[1]

    assert internal.key == "COMMIT_SUMMARY"
    assert internal.source_paths == ()


def test_maps_p2_location_and_source_metadata() -> None:
    data = load_example(WireAnalysisDepth.P2)
    data["repositories"][0]["evidence"][-1]["pullRequestNumber"] = 12

    result = map_data(data)
    code_evidence = result.repositories[0].evidence[-1]

    assert code_evidence.path == "src/AuthFilter.java"
    assert code_evidence.start_line == 5
    assert code_evidence.end_line == 9
    assert code_evidence.commit_sha == "abc123"
    assert code_evidence.pull_request_number == 12
    assert code_evidence.source_evidence_refs == ("ev_002",)


def test_maps_derived_from_level() -> None:
    data = configure_single_evidence(
        load_example(),
        evidence_type="BACKEND_DERIVED",
        depth=WireAnalysisDepth.P0,
    )

    evidence = map_data(data).repositories[0].evidence[0]

    assert evidence.derived_from_level is InternalAnalysisDepth.P0


def test_maps_user_claim_without_promoting_or_rewriting_it() -> None:
    data = load_example()
    claim = data["repositories"][0]["userClaims"][0]
    claim.update(
        {
            "statement": "API를 구현했습니다.",
            "participationLevel": "LEAD",
            "participationStartedOn": "2026-03-01",
            "participationEndedOn": "2026-06-01",
            "relatedEvidenceRefs": ["ev_001"],
        }
    )

    repository = map_data(data).repositories[0]
    internal_claim = repository.user_claims[0]

    assert internal_claim.claim_id == "claim_001"
    assert internal_claim.repository_full_name == "git-ddo/backend"
    assert internal_claim.statement == "API를 구현했습니다."
    assert internal_claim.related_evidence_refs == ("ev_001",)
    assert len(repository.evidence) == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repositoryId", "999"),
        ("repositoryFullName", "other/repository"),
        ("snapshotHashAlgorithm", "SHA256"),
        ("snapshotSha", "different-sha"),
    ],
)
def test_rejects_evidence_parent_or_snapshot_mismatch(field: str, value: str) -> None:
    data = load_example()
    sensitive_value = "PRIVATE-README-CONTENT"
    evidence = data["repositories"][0]["evidence"][0]
    evidence["value"] = sensitive_value
    evidence[field] = value
    request = PortfolioReportRequest.model_validate(data)

    with pytest.raises(RequestMappingError) as exc_info:
        RequestWireMapper().to_internal(request)

    assert sensitive_value not in str(exc_info.value)
    assert "evidence[0]" in str(exc_info.value)


@pytest.mark.parametrize(
    "completed_levels",
    [[], ["P1"], ["P2"], ["P0", "P2"], ["P1", "P0"], ["P0", "P0"]],
)
def test_rejects_invalid_completed_level_sequences(completed_levels: list[str]) -> None:
    data = load_example()
    data["repositories"][0]["completedEvidenceLevels"] = completed_levels
    request = PortfolioReportRequest.model_validate(data)

    with pytest.raises(RequestMappingError):
        RequestWireMapper().to_internal(request)


def test_rejects_repository_depth_above_requested_depth() -> None:
    data = load_example()
    data["repositories"][0]["completedEvidenceLevels"] = ["P0", "P1"]
    request = PortfolioReportRequest.model_validate(data)

    with pytest.raises(RequestMappingError, match="exceeds"):
        RequestWireMapper().to_internal(request)


@pytest.mark.parametrize("target_job", ["FRONTEND", "AI", "CLOUD_INFRA"])
def test_rejects_unsupported_target_jobs(target_job: str) -> None:
    data = load_example()
    data["targetJob"] = target_job
    request = PortfolioReportRequest.model_validate(data)

    with pytest.raises(UnsupportedAnalysisCombinationError):
        RequestWireMapper().to_internal(request)


@pytest.mark.parametrize("career_level", ["JUNIOR", "MID", "SENIOR"])
def test_rejects_unsupported_career_levels(career_level: str) -> None:
    data = load_example()
    data["targetCareerLevel"] = career_level
    request = PortfolioReportRequest.model_validate(data)

    with pytest.raises(UnsupportedAnalysisCombinationError):
        RequestWireMapper().to_internal(request)


def test_rejects_unsupported_analysis_purpose() -> None:
    request = PortfolioReportRequest.model_validate(load_example()).model_copy(
        update={"analysis_purpose": "GITHUB_DIAGNOSIS"}
    )

    with pytest.raises(UnsupportedAnalysisCombinationError):
        RequestWireMapper().to_internal(request)


def test_does_not_copy_wire_only_fields_or_collection_warnings() -> None:
    data = load_example()
    data["repositories"][0]["defaultBranch"] = "wire-only-branch"
    data["repositories"][0]["collectionWarnings"] = [
        {"code": "TRUNCATED_INPUT", "path": "README.md", "message": "잘림"}
    ]

    result = map_data(data)
    repository = result.repositories[0]

    assert not hasattr(result, "schema_version")
    assert not hasattr(result, "analysis_id")
    assert not hasattr(result, "extractor_version")
    assert repository.description is None
    assert all(item.key != "TRUNCATED_INPUT" for item in repository.evidence)


def test_does_not_mutate_wire_request() -> None:
    request = PortfolioReportRequest.model_validate(load_example(WireAnalysisDepth.P1))
    before = request.model_dump(mode="json", by_alias=True)

    RequestWireMapper().to_internal(request)

    assert request.model_dump(mode="json", by_alias=True) == before


def test_does_not_run_reference_or_depth_validators(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_validation(*args: object, **kwargs: object) -> None:
        raise AssertionError("existing validators must not run inside the mapper")

    monkeypatch.setattr(EvidenceReferenceValidator, "validate", fail_validation)
    monkeypatch.setattr(AnalysisDepthValidator, "validate", fail_validation)
    data = load_example()
    data["repositories"][0]["evidence"][0]["sourceEvidenceRefs"] = ["ev_999"]
    data["repositories"][0]["userClaims"][0]["relatedEvidenceRefs"] = ["ev_998"]

    result = map_data(data)

    assert result.repositories[0].evidence[0].source_evidence_refs == ("ev_999",)
    assert result.repositories[0].user_claims[0].related_evidence_refs == ("ev_998",)


def test_mapper_is_stateless() -> None:
    assert vars(RequestWireMapper()) == {}


def test_converts_internal_evidence_validation_failure_to_safe_mapping_error() -> None:
    data = load_example()
    sensitive_value = "DO-NOT-LEAK-README"
    evidence = data["repositories"][0]["evidence"][0]
    evidence["factKey"] = ""
    evidence["value"] = sensitive_value
    request = PortfolioReportRequest.model_validate(data)

    with pytest.raises(RequestMappingError) as exc_info:
        RequestWireMapper().to_internal(request)

    assert "Evidence mapping failed" in str(exc_info.value)
    assert sensitive_value not in str(exc_info.value)


def test_converts_internal_claim_validation_failure_to_safe_mapping_error() -> None:
    data = load_example()
    data["repositories"][0]["userClaims"][0]["statement"] = ""
    request = PortfolioReportRequest.model_validate(data)

    with pytest.raises(RequestMappingError) as exc_info:
        RequestWireMapper().to_internal(request)

    assert "UserClaim mapping failed" in str(exc_info.value)
    assert "API를 구현했습니다." not in str(exc_info.value)


def test_converts_internal_repository_validation_failure_to_mapping_error() -> None:
    data = load_example()
    repository = data["repositories"][0]
    repository["repositoryId"] = "not-numeric"
    repository["evidence"][0]["repositoryId"] = "not-numeric"
    request = PortfolioReportRequest.model_validate(data)

    with pytest.raises(RequestMappingError, match=r"repositories\[0\]"):
        RequestWireMapper().to_internal(request)


def test_converts_internal_portfolio_validation_failure_to_mapping_error() -> None:
    data = load_example()
    add_second_repository(data)
    data["repositories"][1]["repositoryId"] = "123"
    for evidence in data["repositories"][1]["evidence"]:
        evidence["repositoryId"] = "123"
    request = PortfolioReportRequest.model_validate(data)

    with pytest.raises(RequestMappingError, match="internal portfolio input"):
        RequestWireMapper().to_internal(request)


def test_wire_schema_validation_still_precedes_mapping() -> None:
    data = load_example()
    data["schemaVersion"] = "2.0"

    with pytest.raises(ValidationError):
        PortfolioReportRequest.model_validate(data)
