import pytest

from app.core.exceptions import InputValidationError, InputViolationCode
from app.domain import (
    AnalysisDepth,
    EvidenceValueType,
    InternalEvidence,
    InternalEvidenceType,
    InternalPortfolioInput,
    InternalRepositoryInput,
    InternalUserClaim,
    SnapshotHashAlgorithm,
)
from app.validators import EvidenceReferenceValidator


def make_static(
    evidence_id: str,
    repository: str,
    *,
    source_refs: tuple[str, ...] = (),
) -> InternalEvidence:
    return InternalEvidence(
        evidence_id=evidence_id,
        repository_full_name=repository,
        evidence_type=InternalEvidenceType.GITHUB_STATIC,
        analysis_depth=AnalysisDepth.P0,
        key="README",
        summary="README metadata was observed.",
        source_evidence_refs=source_refs,
    )


def make_activity(
    evidence_id: str,
    repository: str,
    *,
    source_refs: tuple[str, ...] = (),
) -> InternalEvidence:
    return InternalEvidence(
        evidence_id=evidence_id,
        repository_full_name=repository,
        evidence_type=InternalEvidenceType.GITHUB_ACTIVITY,
        analysis_depth=AnalysisDepth.P1,
        key="COMMIT_SUMMARY",
        summary="A commit was observed.",
        commit_sha="abc123",
        source_evidence_refs=source_refs,
    )


def make_code(
    evidence_id: str,
    repository: str,
    *,
    source_refs: tuple[str, ...],
    summary: str = "sensitive snippet content",
) -> InternalEvidence:
    return InternalEvidence(
        evidence_id=evidence_id,
        repository_full_name=repository,
        evidence_type=InternalEvidenceType.CODE_EVIDENCE,
        analysis_depth=AnalysisDepth.P2,
        key="CODE_SNIPPET",
        summary=summary,
        value_type=EvidenceValueType.STRING,
        path="src/main/App.java",
        start_line=1,
        end_line=3,
        commit_sha="abc123",
        source_evidence_refs=source_refs,
    )


def make_claim(
    claim_id: str,
    repository: str,
    *,
    refs: tuple[str, ...] = (),
    statement: str = "sensitive user statement",
) -> InternalUserClaim:
    return InternalUserClaim(
        claim_id=claim_id,
        repository_full_name=repository,
        statement=statement,
        related_evidence_refs=refs,
    )


def make_repository(
    repository_id: str,
    repository_name: str,
    depth: AnalysisDepth,
    evidence: tuple[InternalEvidence, ...],
    *,
    claims: tuple[InternalUserClaim, ...] = (),
) -> InternalRepositoryInput:
    completed = {
        AnalysisDepth.P0: (AnalysisDepth.P0,),
        AnalysisDepth.P1: (AnalysisDepth.P0, AnalysisDepth.P1),
        AnalysisDepth.P2: (AnalysisDepth.P0, AnalysisDepth.P1, AnalysisDepth.P2),
    }[depth]
    return InternalRepositoryInput(
        repository_id=repository_id,
        repository_full_name=repository_name,
        analysis_depth=depth,
        completed_evidence_levels=completed,
        snapshot_hash_algorithm=SnapshotHashAlgorithm.SHA1,
        snapshot_sha=f"snapshot-{repository_id}",
        evidence=evidence,
        user_claims=claims,
    )


def make_portfolio(
    repositories: tuple[InternalRepositoryInput, ...],
    *,
    requested: AnalysisDepth = AnalysisDepth.P2,
) -> InternalPortfolioInput:
    return InternalPortfolioInput(
        requested_analysis_depth=requested,
        repositories=repositories,
    )


def violation_codes(error: InputValidationError) -> tuple[InputViolationCode, ...]:
    return tuple(violation.code for violation in error.violations)


def test_accepts_valid_mixed_depth_portfolio() -> None:
    p0 = make_repository(
        "1", "git-ddo/p0", AnalysisDepth.P0, (make_static("ev_001", "git-ddo/p0"),)
    )
    p1 = make_repository(
        "2",
        "git-ddo/p1",
        AnalysisDepth.P1,
        (make_static("ev_002", "git-ddo/p1"), make_activity("ev_003", "git-ddo/p1")),
        claims=(make_claim("claim_001", "git-ddo/p1", refs=("ev_003",)),),
    )
    p2 = make_repository(
        "3",
        "git-ddo/p2",
        AnalysisDepth.P2,
        (
            make_static("ev_004", "git-ddo/p2"),
            make_activity("ev_005", "git-ddo/p2"),
            make_code("ev_006", "git-ddo/p2", source_refs=("ev_005",)),
        ),
    )

    assert EvidenceReferenceValidator().validate(make_portfolio((p0, p1, p2))) is None


@pytest.mark.parametrize(
    ("kind", "expected_code"),
    [
        ("evidence", InputViolationCode.DUPLICATE_EVIDENCE_ID),
        ("claim", InputViolationCode.DUPLICATE_CLAIM_ID),
    ],
)
def test_rejects_analysis_wide_duplicate_identifiers(
    kind: str,
    expected_code: InputViolationCode,
) -> None:
    first = make_repository(
        "1",
        "git-ddo/one",
        AnalysisDepth.P0,
        (make_static("ev_001", "git-ddo/one"),),
        claims=(make_claim("claim_001", "git-ddo/one"),),
    )
    second = make_repository(
        "2",
        "git-ddo/two",
        AnalysisDepth.P0,
        (make_static("ev_001" if kind == "evidence" else "ev_002", "git-ddo/two"),),
        claims=(make_claim("claim_001" if kind == "claim" else "claim_002", "git-ddo/two"),),
    )
    portfolio = InternalPortfolioInput.model_construct(
        requested_analysis_depth=AnalysisDepth.P0,
        repositories=(first, second),
    )

    with pytest.raises(InputValidationError) as raised:
        EvidenceReferenceValidator().validate(portfolio)

    assert expected_code in violation_codes(raised.value)


@pytest.mark.parametrize(
    ("field", "expected_code"),
    [
        ("repository_id", InputViolationCode.DUPLICATE_REPOSITORY_ID),
        ("repository_full_name", InputViolationCode.DUPLICATE_REPOSITORY_NAME),
    ],
)
def test_rejects_duplicate_repository_identifiers(
    field: str,
    expected_code: InputViolationCode,
) -> None:
    first = make_repository(
        "1", "git-ddo/one", AnalysisDepth.P0, (make_static("ev_001", "git-ddo/one"),)
    )
    second = make_repository(
        "2", "git-ddo/two", AnalysisDepth.P0, (make_static("ev_002", "git-ddo/two"),)
    ).model_copy(update={field: getattr(first, field)})
    portfolio = InternalPortfolioInput.model_construct(
        requested_analysis_depth=AnalysisDepth.P0,
        repositories=(first, second),
    )

    with pytest.raises(InputValidationError) as raised:
        EvidenceReferenceValidator().validate(portfolio)

    assert expected_code in violation_codes(raised.value)


def test_rejects_repository_member_ownership_mismatch() -> None:
    evidence = make_static("ev_001", "git-ddo/other")
    claim = make_claim("claim_001", "git-ddo/other")
    valid_repository = make_repository(
        "1",
        "git-ddo/backend",
        AnalysisDepth.P0,
        (make_static("ev_001", "git-ddo/backend"),),
        claims=(make_claim("claim_001", "git-ddo/backend"),),
    )
    repository = valid_repository.model_copy(
        update={"evidence": (evidence,), "user_claims": (claim,)}
    )
    portfolio = InternalPortfolioInput.model_construct(
        requested_analysis_depth=AnalysisDepth.P0,
        repositories=(repository,),
    )

    with pytest.raises(InputValidationError) as raised:
        EvidenceReferenceValidator().validate(portfolio)

    assert violation_codes(raised.value) == (
        InputViolationCode.REPOSITORY_OWNERSHIP_MISMATCH,
        InputViolationCode.REPOSITORY_OWNERSHIP_MISMATCH,
    )


def test_rejects_unknown_source_and_claim_references() -> None:
    repository = make_repository(
        "1",
        "git-ddo/backend",
        AnalysisDepth.P1,
        (
            make_static("ev_001", "git-ddo/backend"),
            make_activity("ev_002", "git-ddo/backend", source_refs=("ev_999",)),
        ),
        claims=(make_claim("claim_001", "git-ddo/backend", refs=("ev_998",)),),
    )

    with pytest.raises(InputValidationError) as raised:
        EvidenceReferenceValidator().validate(
            make_portfolio((repository,), requested=AnalysisDepth.P1)
        )

    assert violation_codes(raised.value) == (
        InputViolationCode.UNKNOWN_SOURCE_EVIDENCE_REF,
        InputViolationCode.UNKNOWN_RELATED_EVIDENCE_REF,
    )


def test_rejects_cross_repository_source_and_claim_references() -> None:
    first = make_repository(
        "1",
        "git-ddo/one",
        AnalysisDepth.P1,
        (make_static("ev_001", "git-ddo/one"), make_activity("ev_002", "git-ddo/one")),
    )
    second = make_repository(
        "2",
        "git-ddo/two",
        AnalysisDepth.P2,
        (
            make_static("ev_003", "git-ddo/two"),
            make_code("ev_004", "git-ddo/two", source_refs=("ev_002",)),
        ),
        claims=(make_claim("claim_001", "git-ddo/two", refs=("ev_001",)),),
    )

    with pytest.raises(InputValidationError) as raised:
        EvidenceReferenceValidator().validate(make_portfolio((first, second)))

    assert violation_codes(raised.value) == (
        InputViolationCode.CROSS_REPOSITORY_REF,
        InputViolationCode.P2_SOURCE_INVALID,
        InputViolationCode.CROSS_REPOSITORY_REF,
    )


def test_rejects_self_reference() -> None:
    valid_activity = make_activity("ev_001", "git-ddo/backend")
    repository = make_repository("1", "git-ddo/backend", AnalysisDepth.P1, (valid_activity,))
    activity = valid_activity.model_copy(update={"source_evidence_refs": ("ev_001",)})
    repository = repository.model_copy(update={"evidence": (activity,)})

    with pytest.raises(InputValidationError) as raised:
        EvidenceReferenceValidator().validate(
            make_portfolio((repository,), requested=AnalysisDepth.P1)
        )

    assert InputViolationCode.REFERENCE_CYCLE in violation_codes(raised.value)


def test_rejects_indirect_reference_cycle() -> None:
    first = make_activity("ev_001", "git-ddo/backend", source_refs=("ev_002",))
    second = make_activity("ev_002", "git-ddo/backend", source_refs=("ev_001",))
    repository = make_repository("1", "git-ddo/backend", AnalysisDepth.P1, (first, second))

    with pytest.raises(InputValidationError) as raised:
        EvidenceReferenceValidator().validate(
            make_portfolio((repository,), requested=AnalysisDepth.P1)
        )

    assert violation_codes(raised.value) == (InputViolationCode.REFERENCE_CYCLE,)


def test_resolves_forward_reference_independent_of_input_order() -> None:
    code = make_code("ev_002", "git-ddo/backend", source_refs=("ev_001",))
    activity = make_activity("ev_001", "git-ddo/backend")
    repository = make_repository("1", "git-ddo/backend", AnalysisDepth.P2, (code, activity))

    assert EvidenceReferenceValidator().validate(make_portfolio((repository,))) is None


def test_accepts_p2_source_derived_from_p1() -> None:
    derived = InternalEvidence(
        evidence_id="ev_001",
        repository_full_name="git-ddo/backend",
        evidence_type=InternalEvidenceType.BACKEND_DERIVED,
        analysis_depth=AnalysisDepth.P1,
        key="ACTIVITY_SUMMARY",
        summary="Activity summary was derived by the backend.",
        derived_from_level=AnalysisDepth.P1,
    )
    code = make_code("ev_002", "git-ddo/backend", source_refs=("ev_001",))
    repository = make_repository("1", "git-ddo/backend", AnalysisDepth.P2, (derived, code))

    assert EvidenceReferenceValidator().validate(make_portfolio((repository,))) is None


def test_allows_empty_claim_related_evidence_refs() -> None:
    repository = make_repository(
        "1",
        "git-ddo/backend",
        AnalysisDepth.P0,
        (make_static("ev_001", "git-ddo/backend"),),
        claims=(make_claim("claim_001", "git-ddo/backend"),),
    )

    assert (
        EvidenceReferenceValidator().validate(
            make_portfolio((repository,), requested=AnalysisDepth.P0)
        )
        is None
    )


def test_rejects_p2_with_only_p0_source() -> None:
    static = make_static("ev_001", "git-ddo/backend")
    code = make_code("ev_002", "git-ddo/backend", source_refs=("ev_001",))
    repository = make_repository("1", "git-ddo/backend", AnalysisDepth.P2, (static, code))

    with pytest.raises(InputValidationError) as raised:
        EvidenceReferenceValidator().validate(make_portfolio((repository,)))

    assert InputViolationCode.P2_SOURCE_INVALID in violation_codes(raised.value)


def test_collects_violations_without_exposing_untrusted_content() -> None:
    secret_summary = "repository-secret-snippet"
    secret_claim = "user-secret-statement"
    evidence = make_activity(
        "ev_001",
        "git-ddo/backend",
        source_refs=("ev_999",),
    ).model_copy(update={"summary": secret_summary})
    repository = make_repository(
        "1",
        "git-ddo/backend",
        AnalysisDepth.P1,
        (evidence,),
        claims=(
            make_claim("claim_001", "git-ddo/backend", refs=("ev_998",), statement=secret_claim),
        ),
    )

    with pytest.raises(InputValidationError) as raised:
        EvidenceReferenceValidator().validate(
            make_portfolio((repository,), requested=AnalysisDepth.P1)
        )

    rendered = str(raised.value)
    assert secret_summary not in rendered
    assert secret_claim not in rendered
    assert [violation.field_path for violation in raised.value.violations] == [
        "repositories[0].evidence[0].source_evidence_refs[0]",
        "repositories[0].user_claims[0].related_evidence_refs[0]",
    ]
