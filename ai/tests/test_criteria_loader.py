from pathlib import Path

import pytest

from app.criteria import (
    CriteriaFileNotFoundError,
    CriteriaLoader,
    CriteriaParseError,
    CriteriaValidationError,
    UnsupportedCriteriaError,
)

VALID_CRITERIA_YAML = """\
version: "1.0"
target_job: BACKEND
analysis_depth: P0
criteria:
  - key: README_READINESS
    title: README 준비도
    description: README에서 공개적으로 확인되는 항목을 해석한다.
    allowed_evidence_types:
      - GITHUB_STATIC
      - BACKEND_DERIVED
    allowed_judgments:
      - README 항목의 관찰 여부
    forbidden_judgments:
      - 사용자의 문서 작성 역량
"""


def write_backend_criteria(base_dir: Path, content: str) -> None:
    (base_dir / "backend.yaml").write_text(content, encoding="utf-8")


def test_loads_backend_p0_criteria() -> None:
    criteria_set = CriteriaLoader().load("BACKEND", "P0")

    assert criteria_set.version == "1.0"
    assert criteria_set.target_job == "BACKEND"
    assert criteria_set.analysis_depth == "P0"
    assert [criterion.key for criterion in criteria_set.criteria] == [
        "README_READINESS",
        "TECH_STACK_EVIDENCE",
        "TEST_PRESENCE",
        "DOCKER_CONFIGURATION",
        "GITHUB_ACTIONS_CONFIGURATION",
    ]
    assert all(
        set(criterion.allowed_evidence_types) <= {"GITHUB_STATIC", "BACKEND_DERIVED"}
        for criterion in criteria_set.criteria
    )


@pytest.mark.parametrize(
    ("target_job", "analysis_depth"),
    [
        ("FRONTEND", "P0"),
        ("BACKEND", "P1"),
        ("BACKEND", "P2"),
        ("../backend", "P0"),
    ],
)
def test_rejects_unsupported_criteria_combination(
    target_job: str,
    analysis_depth: str,
) -> None:
    with pytest.raises(UnsupportedCriteriaError):
        CriteriaLoader().load(target_job, analysis_depth)


def test_raises_distinct_error_when_criteria_file_is_missing(tmp_path: Path) -> None:
    with pytest.raises(CriteriaFileNotFoundError):
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P0")


def test_raises_distinct_error_for_invalid_yaml(tmp_path: Path) -> None:
    write_backend_criteria(tmp_path, "criteria: [\n")

    with pytest.raises(CriteriaParseError):
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P0")


def test_rejects_missing_required_field(tmp_path: Path) -> None:
    write_backend_criteria(
        tmp_path,
        VALID_CRITERIA_YAML.replace('version: "1.0"\n', ""),
    )

    with pytest.raises(CriteriaValidationError):
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P0")


def test_rejects_unknown_field(tmp_path: Path) -> None:
    write_backend_criteria(
        tmp_path,
        VALID_CRITERIA_YAML.replace(
            "analysis_depth: P0\n",
            "analysis_depth: P0\nunknown_field: rejected\n",
        ),
    )

    with pytest.raises(CriteriaValidationError):
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P0")


def test_rejects_empty_criteria_list(tmp_path: Path) -> None:
    write_backend_criteria(
        tmp_path,
        """\
version: "1.0"
target_job: BACKEND
analysis_depth: P0
criteria: []
""",
    )

    with pytest.raises(CriteriaValidationError):
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P0")


def test_rejects_duplicate_criteria_keys(tmp_path: Path) -> None:
    duplicate_criterion = VALID_CRITERIA_YAML.split("criteria:\n", maxsplit=1)[1]
    write_backend_criteria(
        tmp_path,
        VALID_CRITERIA_YAML + duplicate_criterion,
    )

    with pytest.raises(CriteriaValidationError):
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P0")


def test_rejects_evidence_type_not_allowed_in_p0(tmp_path: Path) -> None:
    write_backend_criteria(
        tmp_path,
        VALID_CRITERIA_YAML.replace("GITHUB_STATIC", "GITHUB_ACTIVITY"),
    )

    with pytest.raises(CriteriaValidationError):
        CriteriaLoader(base_dir=tmp_path).load("BACKEND", "P0")
