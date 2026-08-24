import pytest

from app.core.exceptions import InputValidationError, InputViolationCode
from app.domain import (
    AnalysisDepth,
    EvidenceValueType,
    InternalEvidence,
    InternalEvidenceType,
    InternalPortfolioInput,
    InternalRepositoryInput,
    SnapshotHashAlgorithm,
)
from app.validators import AnalysisDepthValidator


def make_evidence(
    evidence_id: str,
    repository: str,
    evidence_type: InternalEvidenceType,
    depth: AnalysisDepth,
    **updates: object,
) -> InternalEvidence:
    values: dict[str, object] = {
        "evidence_id": evidence_id,
        "repository_full_name": repository,
        "evidence_type": evidence_type,
        "analysis_depth": depth,
        "key": "README" if depth is AnalysisDepth.P0 else "COMMIT_SUMMARY",
        "summary": "safe evidence summary",
    }
    if evidence_type is InternalEvidenceType.CODE_EVIDENCE:
        values.update(
            key="CODE_SNIPPET",
            value_type=EvidenceValueType.STRING,
            path="src/main/App.java",
            start_line=1,
            end_line=2,
            commit_sha="abc123",
            source_evidence_refs=("ev_002",),
        )
    if evidence_type is InternalEvidenceType.BACKEND_DERIVED:
        values["derived_from_level"] = depth
    values.update(updates)
    return InternalEvidence(**values)  # type: ignore[arg-type]


def make_repository(
    repository_id: str,
    depth: AnalysisDepth,
    evidence: tuple[InternalEvidence, ...],
    *,
    completed: tuple[AnalysisDepth, ...] | None = None,
    snapshot_algorithm: SnapshotHashAlgorithm | None = SnapshotHashAlgorithm.SHA1,
    snapshot_sha: str | None = "snapshot-sha",
) -> InternalRepositoryInput:
    levels = (
        completed
        or {
            AnalysisDepth.P0: (AnalysisDepth.P0,),
            AnalysisDepth.P1: (AnalysisDepth.P0, AnalysisDepth.P1),
            AnalysisDepth.P2: (AnalysisDepth.P0, AnalysisDepth.P1, AnalysisDepth.P2),
        }[depth]
    )
    return InternalRepositoryInput(
        repository_id=repository_id,
        repository_full_name=f"git-ddo/repo-{repository_id}",
        analysis_depth=depth,
        completed_evidence_levels=levels,
        snapshot_hash_algorithm=snapshot_algorithm,
        snapshot_sha=snapshot_sha,
        evidence=evidence,
    )


def make_portfolio(
    requested: AnalysisDepth,
    repositories: tuple[InternalRepositoryInput, ...],
) -> InternalPortfolioInput:
    return InternalPortfolioInput(
        requested_analysis_depth=requested,
        repositories=repositories,
    )


def make_unchecked_portfolio(
    requested: AnalysisDepth,
    repositories: tuple[InternalRepositoryInput, ...],
) -> InternalPortfolioInput:
    return InternalPortfolioInput.model_construct(
        requested_analysis_depth=requested,
        repositories=repositories,
    )


def codes(error: InputValidationError) -> tuple[InputViolationCode, ...]:
    return tuple(violation.code for violation in error.violations)


def valid_repository(repository_id: str, depth: AnalysisDepth) -> InternalRepositoryInput:
    name = f"git-ddo/repo-{repository_id}"
    static = make_evidence("ev_001", name, InternalEvidenceType.GITHUB_STATIC, AnalysisDepth.P0)
    if depth is AnalysisDepth.P0:
        return make_repository(repository_id, depth, (static,))
    activity = make_evidence("ev_002", name, InternalEvidenceType.GITHUB_ACTIVITY, AnalysisDepth.P1)
    if depth is AnalysisDepth.P1:
        return make_repository(repository_id, depth, (static, activity))
    code = make_evidence("ev_003", name, InternalEvidenceType.CODE_EVIDENCE, AnalysisDepth.P2)
    return make_repository(repository_id, depth, (static, activity, code))


@pytest.mark.parametrize(
    ("requested", "depths"),
    [
        (AnalysisDepth.P0, (AnalysisDepth.P0,)),
        (AnalysisDepth.P1, (AnalysisDepth.P0, AnalysisDepth.P1)),
        (AnalysisDepth.P2, (AnalysisDepth.P0, AnalysisDepth.P1, AnalysisDepth.P2)),
    ],
)
def test_accepts_supported_requested_and_repository_depths(
    requested: AnalysisDepth,
    depths: tuple[AnalysisDepth, ...],
) -> None:
    repositories: list[InternalRepositoryInput] = []
    next_evidence = 1
    for index, depth in enumerate(depths, start=1):
        repository = valid_repository(str(index), depth)
        remapped = tuple(
            evidence.model_copy(update={"evidence_id": f"ev_{next_evidence + offset:03d}"})
            for offset, evidence in enumerate(repository.evidence)
        )
        next_evidence += len(remapped)
        repositories.append(repository.model_copy(update={"evidence": remapped}))

    portfolio = make_portfolio(requested, tuple(repositories))

    assert AnalysisDepthValidator().validate(portfolio) is None


def test_rejects_repository_depth_above_requested_maximum() -> None:
    repository = valid_repository("1", AnalysisDepth.P2)
    portfolio = make_portfolio(AnalysisDepth.P1, (repository,))

    with pytest.raises(InputValidationError) as raised:
        AnalysisDepthValidator().validate(portfolio)

    assert InputViolationCode.DEPTH_EXCEEDS_REQUESTED in codes(raised.value)


@pytest.mark.parametrize(
    "levels",
    [
        (AnalysisDepth.P1, AnalysisDepth.P0),
        (AnalysisDepth.P0, AnalysisDepth.P0),
        (AnalysisDepth.P0, AnalysisDepth.P2),
    ],
)
def test_rejects_invalid_completed_level_prefix(levels: tuple[AnalysisDepth, ...]) -> None:
    repository = valid_repository("1", AnalysisDepth.P1).model_copy(
        update={"completed_evidence_levels": levels}
    )

    with pytest.raises(InputValidationError) as raised:
        AnalysisDepthValidator().validate(make_unchecked_portfolio(AnalysisDepth.P2, (repository,)))

    assert InputViolationCode.COMPLETED_LEVELS_INVALID in codes(raised.value)


def test_rejects_evidence_depth_not_completed() -> None:
    repository = valid_repository("1", AnalysisDepth.P1).model_copy(
        update={"completed_evidence_levels": (AnalysisDepth.P0,)}
    )

    with pytest.raises(InputValidationError) as raised:
        AnalysisDepthValidator().validate(make_unchecked_portfolio(AnalysisDepth.P1, (repository,)))

    assert InputViolationCode.EVIDENCE_DEPTH_NOT_COMPLETED in codes(raised.value)


def test_rejects_completed_level_without_corresponding_evidence() -> None:
    repository = valid_repository("1", AnalysisDepth.P1)
    repository = repository.model_copy(update={"evidence": (repository.evidence[0],)})

    with pytest.raises(InputValidationError) as raised:
        AnalysisDepthValidator().validate(make_unchecked_portfolio(AnalysisDepth.P1, (repository,)))

    assert InputViolationCode.COMPLETED_LEVELS_INVALID in codes(raised.value)


def test_rejects_evidence_type_depth_mismatch() -> None:
    repository = valid_repository("1", AnalysisDepth.P1)
    invalid = repository.evidence[1].model_copy(update={"analysis_depth": AnalysisDepth.P0})
    repository = repository.model_copy(update={"evidence": (repository.evidence[0], invalid)})

    with pytest.raises(InputValidationError) as raised:
        AnalysisDepthValidator().validate(make_unchecked_portfolio(AnalysisDepth.P1, (repository,)))

    assert InputViolationCode.EVIDENCE_TYPE_DEPTH_MISMATCH in codes(raised.value)


@pytest.mark.parametrize(
    ("derived_level", "expected_code"),
    [
        (None, InputViolationCode.EVIDENCE_TYPE_DEPTH_MISMATCH),
        (AnalysisDepth.P2, InputViolationCode.UPWARD_DEPTH_DERIVATION),
        (AnalysisDepth.P0, InputViolationCode.EVIDENCE_TYPE_DEPTH_MISMATCH),
    ],
)
def test_rejects_invalid_backend_derived_depth(
    derived_level: AnalysisDepth | None,
    expected_code: InputViolationCode,
) -> None:
    name = "git-ddo/repo-1"
    evidence = make_evidence(
        "ev_001",
        name,
        InternalEvidenceType.BACKEND_DERIVED,
        AnalysisDepth.P1,
    ).model_copy(update={"derived_from_level": derived_level})
    valid_evidence = make_evidence(
        "ev_001",
        name,
        InternalEvidenceType.BACKEND_DERIVED,
        AnalysisDepth.P1,
    )
    repository = make_repository("1", AnalysisDepth.P1, (valid_evidence,)).model_copy(
        update={"evidence": (evidence,)}
    )

    with pytest.raises(InputValidationError) as raised:
        AnalysisDepthValidator().validate(make_unchecked_portfolio(AnalysisDepth.P2, (repository,)))

    assert expected_code in codes(raised.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("key", "OTHER_CODE"),
        ("value_type", EvidenceValueType.INTEGER),
        ("path", None),
        ("start_line", None),
        ("end_line", None),
        ("end_line", 0),
        ("commit_sha", None),
        ("source_evidence_refs", ()),
    ],
)
def test_rejects_invalid_p2_metadata(field: str, value: object) -> None:
    repository = valid_repository("1", AnalysisDepth.P2)
    code = repository.evidence[-1].model_copy(update={field: value})
    repository = repository.model_copy(update={"evidence": repository.evidence[:-1] + (code,)})

    with pytest.raises(InputValidationError) as raised:
        AnalysisDepthValidator().validate(make_unchecked_portfolio(AnalysisDepth.P2, (repository,)))

    assert InputViolationCode.P2_METADATA_INVALID in codes(raised.value)


def test_rejects_line_range_on_non_code_evidence() -> None:
    repository = valid_repository("1", AnalysisDepth.P0)
    static = repository.evidence[0].model_copy(update={"start_line": 1, "end_line": 2})
    repository = repository.model_copy(update={"evidence": (static,)})

    with pytest.raises(InputValidationError) as raised:
        AnalysisDepthValidator().validate(make_unchecked_portfolio(AnalysisDepth.P0, (repository,)))

    assert InputViolationCode.P2_METADATA_INVALID in codes(raised.value)


@pytest.mark.parametrize(
    ("algorithm", "sha"),
    [
        (None, None),
        (SnapshotHashAlgorithm.SHA1, None),
        (None, "snapshot-sha"),
    ],
)
def test_rejects_missing_or_partial_snapshot(
    algorithm: SnapshotHashAlgorithm | None,
    sha: str | None,
) -> None:
    repository = valid_repository("1", AnalysisDepth.P0).model_copy(
        update={"snapshot_hash_algorithm": algorithm, "snapshot_sha": sha}
    )

    with pytest.raises(InputValidationError) as raised:
        AnalysisDepthValidator().validate(make_unchecked_portfolio(AnalysisDepth.P0, (repository,)))

    assert InputViolationCode.SNAPSHOT_REQUIRED in codes(raised.value)


def test_depth_error_does_not_expose_snippet_content() -> None:
    secret = "private-code-snippet"
    repository = valid_repository("1", AnalysisDepth.P2)
    invalid = repository.evidence[-1].model_copy(update={"key": "INVALID", "summary": secret})
    repository = repository.model_copy(update={"evidence": repository.evidence[:-1] + (invalid,)})

    with pytest.raises(InputValidationError) as raised:
        AnalysisDepthValidator().validate(make_portfolio(AnalysisDepth.P2, (repository,)))

    assert secret not in str(raised.value)
