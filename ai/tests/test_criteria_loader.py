from copy import deepcopy
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from app.criteria import (
    CriteriaFileNotFoundError,
    CriteriaGuardrailCode,
    CriteriaLoader,
    CriteriaParseError,
    CriteriaValidationError,
    UnsupportedCriteriaError,
)
from app.domain import AnalysisDepth, InternalEvidenceType

P0_KEYS = (
    "README_READINESS",
    "TECH_STACK_EVIDENCE",
    "TEST_PRESENCE",
    "DOCKER_CONFIGURATION",
    "GITHUB_ACTIONS_CONFIGURATION",
)
P1_KEYS = (
    "ACTIVITY_SCOPE",
    "CLAIM_ACTIVITY_LINK",
    "CHANGE_AREA_OBSERVATION",
)
P2_KEYS = (
    "SNIPPET_SCOPE",
    "INPUT_VALIDATION_OBSERVATION",
    "ERROR_HANDLING_OBSERVATION",
    "RESPONSIBILITY_OBSERVATION",
    "TEST_CASE_OBSERVATION",
)
KEYS_BY_DEPTH = {
    AnalysisDepth.P0: P0_KEYS,
    AnalysisDepth.P1: P1_KEYS,
    AnalysisDepth.P2: P2_KEYS,
}
GUARDRAILS_BY_DEPTH = {
    AnalysisDepth.P0: (
        "USER_ABILITY_ASSERTION",
        "CONTRIBUTION_ASSERTION",
        "CAREER_LEVEL_ASSERTION",
        "EMPLOYMENT_PROBABILITY_ASSERTION",
        "NOT_OBSERVED_AS_ABSENCE",
        "CODE_QUALITY_WITHOUT_P2",
    ),
    AnalysisDepth.P1: (
        "ACTIVITY_VOLUME_AS_SKILL",
        "ACTIVITY_VOLUME_AS_CONTRIBUTION",
        "ACTIVITY_ABSENCE_AS_NON_CONTRIBUTION",
        "CODE_QUALITY_WITHOUT_P2",
        "USER_CLAIM_AS_FACT",
    ),
    AnalysisDepth.P2: (
        "REPOSITORY_WIDE_GENERALIZATION",
        "USER_ABILITY_ASSERTION",
        "CONTRIBUTION_ASSERTION",
        "CAREER_LEVEL_ASSERTION",
        "CODE_EXECUTION",
    ),
}
EVIDENCE_TYPES_BY_DEPTH = {
    AnalysisDepth.P0: ("GITHUB_STATIC", "BACKEND_DERIVED"),
    AnalysisDepth.P1: ("GITHUB_ACTIVITY", "BACKEND_DERIVED"),
    AnalysisDepth.P2: ("CODE_EVIDENCE", "BACKEND_DERIVED"),
}
FILENAMES_BY_DEPTH = {
    AnalysisDepth.P0: "backend.yaml",
    AnalysisDepth.P1: "backend_p1.yaml",
    AnalysisDepth.P2: "backend_p2.yaml",
}
DEPTH_PREFIXES = {
    AnalysisDepth.P0: (AnalysisDepth.P0,),
    AnalysisDepth.P1: (AnalysisDepth.P0, AnalysisDepth.P1),
    AnalysisDepth.P2: (AnalysisDepth.P0, AnalysisDepth.P1, AnalysisDepth.P2),
}


def build_layer(
    depth: AnalysisDepth,
    *,
    keys: tuple[str, ...] | None = None,
) -> dict[str, object]:
    resolved_keys = keys if keys is not None else KEYS_BY_DEPTH[depth]
    return {
        "version": "1.0",
        "target_job": "BACKEND",
        "analysis_depth": depth.value,
        "guardrail_codes": list(GUARDRAILS_BY_DEPTH[depth]),
        "criteria": [
            {
                "key": key,
                "analysis_depth": depth.value,
                "title": f"{key} title",
                "description": f"{key} description",
                "allowed_evidence_types": list(EVIDENCE_TYPES_BY_DEPTH[depth]),
                "allow_user_claims": key == "CLAIM_ACTIVITY_LINK",
                "allowed_judgments": [f"{key} allowed judgment"],
                "forbidden_judgments": [f"{key} forbidden judgment"],
            }
            for key in resolved_keys
        ],
    }


def write_layer(
    base_dir: Path,
    depth: AnalysisDepth,
    layer: dict[str, object] | None = None,
) -> None:
    content = layer if layer is not None else build_layer(depth)
    (base_dir / FILENAMES_BY_DEPTH[depth]).write_text(
        yaml.safe_dump(content, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def write_layers_through(base_dir: Path, depth: AnalysisDepth) -> None:
    for layer_depth in DEPTH_PREFIXES[depth]:
        write_layer(base_dir, layer_depth)


def criterion_keys(criteria_set: object) -> tuple[str, ...]:
    return tuple(item.key for item in criteria_set.criteria)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("requested_depth", "expected_keys"),
    [
        (AnalysisDepth.P0, P0_KEYS),
        (AnalysisDepth.P1, P0_KEYS + P1_KEYS),
        (AnalysisDepth.P2, P0_KEYS + P1_KEYS + P2_KEYS),
    ],
)
def test_loads_cumulative_backend_criteria(
    requested_depth: AnalysisDepth,
    expected_keys: tuple[str, ...],
) -> None:
    criteria_set = CriteriaLoader().load("BACKEND", requested_depth.value)

    assert criteria_set.version == "1.0"
    assert criteria_set.target_job == "BACKEND"
    assert criteria_set.analysis_depth is requested_depth
    assert criterion_keys(criteria_set) == expected_keys


def test_p2_criteria_are_ordered_p0_then_p1_then_p2() -> None:
    criteria_set = CriteriaLoader().load("BACKEND", "P2")

    assert tuple(item.analysis_depth for item in criteria_set.criteria) == (
        (AnalysisDepth.P0,) * len(P0_KEYS)
        + (AnalysisDepth.P1,) * len(P1_KEYS)
        + (AnalysisDepth.P2,) * len(P2_KEYS)
    )


def test_repeated_load_is_deterministic() -> None:
    loader = CriteriaLoader()

    assert loader.load("BACKEND", "P2") == loader.load("BACKEND", "P2")


def test_p1_load_does_not_require_p2_file(tmp_path: Path) -> None:
    write_layers_through(tmp_path, AnalysisDepth.P1)

    criteria_set = CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P1")

    assert criterion_keys(criteria_set) == P0_KEYS + P1_KEYS


def test_p2_has_each_required_key_exactly_once() -> None:
    keys = criterion_keys(CriteriaLoader().load("BACKEND", "P2"))

    assert len(keys) == len(set(keys))
    assert set(keys) == set(P0_KEYS + P1_KEYS + P2_KEYS)


@pytest.mark.parametrize(
    ("depth", "expected_types"),
    [
        (
            AnalysisDepth.P0,
            {InternalEvidenceType.GITHUB_STATIC, InternalEvidenceType.BACKEND_DERIVED},
        ),
        (
            AnalysisDepth.P1,
            {InternalEvidenceType.GITHUB_ACTIVITY, InternalEvidenceType.BACKEND_DERIVED},
        ),
        (
            AnalysisDepth.P2,
            {InternalEvidenceType.CODE_EVIDENCE, InternalEvidenceType.BACKEND_DERIVED},
        ),
    ],
)
def test_each_layer_uses_only_depth_allowed_evidence_types(
    depth: AnalysisDepth,
    expected_types: set[InternalEvidenceType],
) -> None:
    criteria_set = CriteriaLoader().load("BACKEND", depth.value)
    depth_criteria = [item for item in criteria_set.criteria if item.analysis_depth is depth]

    assert depth_criteria
    assert all(set(item.allowed_evidence_types) == expected_types for item in depth_criteria)


def test_only_claim_activity_link_allows_user_claims() -> None:
    criteria_set = CriteriaLoader().load("BACKEND", "P2")
    claim_enabled_keys = {item.key for item in criteria_set.criteria if item.allow_user_claims}

    assert claim_enabled_keys == {"CLAIM_ACTIVITY_LINK"}


@pytest.mark.parametrize("depth", list(AnalysisDepth))
def test_loads_required_guardrails(depth: AnalysisDepth) -> None:
    criteria_set = CriteriaLoader().load("BACKEND", depth.value)
    expected = {
        CriteriaGuardrailCode(code)
        for layer_depth in DEPTH_PREFIXES[depth]
        for code in GUARDRAILS_BY_DEPTH[layer_depth]
    }

    assert set(criteria_set.guardrail_codes) == expected
    assert len(criteria_set.guardrail_codes) == len(set(criteria_set.guardrail_codes))


def test_p1_guardrails_forbid_activity_volume_inferences() -> None:
    guardrails = set(CriteriaLoader().load("BACKEND", "P1").guardrail_codes)

    assert CriteriaGuardrailCode.ACTIVITY_VOLUME_AS_SKILL in guardrails
    assert CriteriaGuardrailCode.ACTIVITY_VOLUME_AS_CONTRIBUTION in guardrails
    assert CriteriaGuardrailCode.ACTIVITY_ABSENCE_AS_NON_CONTRIBUTION in guardrails


def test_p2_guardrails_forbid_repository_wide_generalization() -> None:
    guardrails = set(CriteriaLoader().load("BACKEND", "P2").guardrail_codes)

    assert CriteriaGuardrailCode.REPOSITORY_WIDE_GENERALIZATION in guardrails
    assert CriteriaGuardrailCode.CODE_EXECUTION in guardrails


@pytest.mark.parametrize(
    ("target_job", "analysis_depth"),
    [
        ("FRONTEND", "P0"),
        ("BACKEND", "P3"),
        ("../backend", "P0"),
        ("BACKEND", "../P2"),
    ],
)
def test_rejects_unsupported_criteria_combination(
    target_job: str,
    analysis_depth: str,
) -> None:
    with pytest.raises(UnsupportedCriteriaError):
        CriteriaLoader().load(target_job, analysis_depth)


@pytest.mark.parametrize("missing_depth", list(AnalysisDepth))
def test_raises_distinct_error_when_required_layer_file_is_missing(
    tmp_path: Path,
    missing_depth: AnalysisDepth,
) -> None:
    for depth in AnalysisDepth:
        if depth is not missing_depth:
            write_layer(tmp_path, depth)

    requested_depth = AnalysisDepth.P0 if missing_depth is AnalysisDepth.P0 else missing_depth
    with pytest.raises(CriteriaFileNotFoundError):
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", requested_depth.value)


@pytest.mark.parametrize("depth", list(AnalysisDepth))
def test_raises_distinct_error_for_invalid_yaml(tmp_path: Path, depth: AnalysisDepth) -> None:
    write_layers_through(tmp_path, depth)
    (tmp_path / FILENAMES_BY_DEPTH[depth]).write_text("criteria: [\n", encoding="utf-8")

    with pytest.raises(CriteriaParseError):
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", depth.value)


def test_rejects_missing_required_field(tmp_path: Path) -> None:
    layer = build_layer(AnalysisDepth.P0)
    del layer["version"]
    write_layer(tmp_path, AnalysisDepth.P0, layer)

    with pytest.raises(CriteriaValidationError):
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P0")


def test_rejects_unknown_field(tmp_path: Path) -> None:
    layer = build_layer(AnalysisDepth.P0)
    layer["unknown_field"] = "rejected"
    write_layer(tmp_path, AnalysisDepth.P0, layer)

    with pytest.raises(CriteriaValidationError):
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P0")


def test_rejects_empty_criteria_list(tmp_path: Path) -> None:
    layer = build_layer(AnalysisDepth.P0)
    layer["criteria"] = []
    write_layer(tmp_path, AnalysisDepth.P0, layer)

    with pytest.raises(CriteriaValidationError):
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P0")


def test_rejects_duplicate_criteria_keys(tmp_path: Path) -> None:
    layer = build_layer(AnalysisDepth.P0)
    criteria = layer["criteria"]
    assert isinstance(criteria, list)
    criteria.append(deepcopy(criteria[0]))
    write_layer(tmp_path, AnalysisDepth.P0, layer)

    with pytest.raises(CriteriaValidationError, match="criteria layer"):
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P0")


@pytest.mark.parametrize("depth", list(AnalysisDepth))
def test_rejects_missing_required_criteria_key(tmp_path: Path, depth: AnalysisDepth) -> None:
    write_layers_through(tmp_path, depth)
    layer = build_layer(depth, keys=KEYS_BY_DEPTH[depth][:-1])
    write_layer(tmp_path, depth, layer)

    with pytest.raises(CriteriaValidationError) as raised:
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", depth.value)

    assert raised.value.__cause__ is not None
    assert f"missing criteria keys: {KEYS_BY_DEPTH[depth][-1]}" in str(raised.value.__cause__)


def test_rejects_unexpected_criteria_key(tmp_path: Path) -> None:
    layer = build_layer(AnalysisDepth.P1, keys=P1_KEYS + ("CODE_QUALITY",))
    write_layers_through(tmp_path, AnalysisDepth.P1)
    write_layer(tmp_path, AnalysisDepth.P1, layer)

    with pytest.raises(CriteriaValidationError) as raised:
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P1")

    assert raised.value.__cause__ is not None
    assert "unexpected criteria keys: CODE_QUALITY" in str(raised.value.__cause__)


def test_rejects_replaced_required_criteria_key(tmp_path: Path) -> None:
    layer = build_layer(
        AnalysisDepth.P2,
        keys=P2_KEYS[:-1] + ("CODE_QUALITY",),
    )
    write_layers_through(tmp_path, AnalysisDepth.P2)
    write_layer(tmp_path, AnalysisDepth.P2, layer)

    with pytest.raises(CriteriaValidationError) as raised:
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P2")

    validation_error = str(raised.value.__cause__)
    assert "missing criteria keys: TEST_CASE_OBSERVATION" in validation_error
    assert "unexpected criteria keys: CODE_QUALITY" in validation_error


def test_accepts_layer_criteria_in_different_order(tmp_path: Path) -> None:
    reversed_keys = tuple(reversed(P0_KEYS))
    write_layer(
        tmp_path,
        AnalysisDepth.P0,
        build_layer(AnalysisDepth.P0, keys=reversed_keys),
    )

    criteria_set = CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P0")

    assert criterion_keys(criteria_set) == reversed_keys


@pytest.mark.parametrize(
    ("depth", "invalid_type"),
    [
        (AnalysisDepth.P0, "GITHUB_ACTIVITY"),
        (AnalysisDepth.P1, "CODE_EVIDENCE"),
        (AnalysisDepth.P2, "GITHUB_STATIC"),
    ],
)
def test_rejects_evidence_type_not_allowed_at_depth(
    tmp_path: Path,
    depth: AnalysisDepth,
    invalid_type: str,
) -> None:
    write_layers_through(tmp_path, depth)
    layer = build_layer(depth)
    criteria = layer["criteria"]
    assert isinstance(criteria, list)
    criteria[0]["allowed_evidence_types"] = [invalid_type]
    write_layer(tmp_path, depth, layer)

    with pytest.raises(CriteriaValidationError):
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", depth.value)


def test_rejects_user_claims_for_non_claim_link_criterion(tmp_path: Path) -> None:
    write_layers_through(tmp_path, AnalysisDepth.P1)
    layer = build_layer(AnalysisDepth.P1)
    criteria = layer["criteria"]
    assert isinstance(criteria, list)
    criteria[0]["allow_user_claims"] = True
    write_layer(tmp_path, AnalysisDepth.P1, layer)

    with pytest.raises(CriteriaValidationError):
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P1")


def test_rejects_claim_link_without_user_claim_permission(tmp_path: Path) -> None:
    write_layers_through(tmp_path, AnalysisDepth.P1)
    layer = build_layer(AnalysisDepth.P1)
    criteria = layer["criteria"]
    assert isinstance(criteria, list)
    claim_link = next(item for item in criteria if item["key"] == "CLAIM_ACTIVITY_LINK")
    claim_link["allow_user_claims"] = False
    write_layer(tmp_path, AnalysisDepth.P1, layer)

    with pytest.raises(CriteriaValidationError):
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P1")


@pytest.mark.parametrize("depth", list(AnalysisDepth))
def test_rejects_missing_guardrail(tmp_path: Path, depth: AnalysisDepth) -> None:
    write_layers_through(tmp_path, depth)
    layer = build_layer(depth)
    guardrails = layer["guardrail_codes"]
    assert isinstance(guardrails, list)
    guardrails.pop()
    write_layer(tmp_path, depth, layer)

    with pytest.raises(CriteriaValidationError) as raised:
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", depth.value)

    assert "missing guardrail codes" in str(raised.value.__cause__)


def test_rejects_unknown_guardrail(tmp_path: Path) -> None:
    layer = build_layer(AnalysisDepth.P0)
    guardrails = layer["guardrail_codes"]
    assert isinstance(guardrails, list)
    guardrails.append("UNKNOWN_GUARDRAIL")
    write_layer(tmp_path, AnalysisDepth.P0, layer)

    with pytest.raises(CriteriaValidationError):
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P0")


def test_rejects_unexpected_known_guardrail(tmp_path: Path) -> None:
    layer = build_layer(AnalysisDepth.P0)
    guardrails = layer["guardrail_codes"]
    assert isinstance(guardrails, list)
    guardrails.append("CODE_EXECUTION")
    write_layer(tmp_path, AnalysisDepth.P0, layer)

    with pytest.raises(CriteriaValidationError) as raised:
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P0")

    assert "unexpected guardrail codes: CODE_EXECUTION" in str(raised.value.__cause__)


def test_rejects_duplicate_guardrail(tmp_path: Path) -> None:
    layer = build_layer(AnalysisDepth.P0)
    guardrails = layer["guardrail_codes"]
    assert isinstance(guardrails, list)
    guardrails.append(guardrails[0])
    write_layer(tmp_path, AnalysisDepth.P0, layer)

    with pytest.raises(CriteriaValidationError) as raised:
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P0")

    assert "guardrail_codes must not contain duplicates" in str(raised.value.__cause__)


def test_rejects_layer_depth_mismatch(tmp_path: Path) -> None:
    write_layers_through(tmp_path, AnalysisDepth.P1)
    write_layer(tmp_path, AnalysisDepth.P1, build_layer(AnalysisDepth.P0))

    with pytest.raises(CriteriaValidationError):
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P1")


@pytest.mark.parametrize(("field", "value"), [("version", "2.0"), ("target_job", "AI")])
def test_rejects_layer_version_or_job_mismatch(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    layer = build_layer(AnalysisDepth.P0)
    layer[field] = value
    write_layer(tmp_path, AnalysisDepth.P0, layer)

    with pytest.raises(CriteriaValidationError):
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P0")


def test_criteria_models_exclude_scoring_fields() -> None:
    criteria_set = CriteriaLoader().load("BACKEND", "P2")
    serialized = criteria_set.model_dump(mode="json")

    assert "score" not in serialized
    assert "weight" not in serialized
    assert all("score" not in item and "weight" not in item for item in serialized["criteria"])
