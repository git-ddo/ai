import pytest

from app.core.exceptions import ReportPolicyError
from app.criteria import CriteriaLoader
from app.domain import (
    AnalysisDepth,
    AnalysisItemType,
    EvidenceConfidence,
    GroundedAnalysisItem,
    InternalEvidence,
    InternalEvidenceType,
    InternalUserClaim,
    NormalizedRepositoryContext,
    PortfolioSynthesis,
    RecommendationPriority,
    RepresentativeProject,
    SnapshotHashAlgorithm,
)
from app.validators import PolicyViolationCode, PortfolioPolicyValidator


def make_context(
    index: int, depth: AnalysisDepth = AnalysisDepth.P0
) -> NormalizedRepositoryContext:
    repository = f"git-ddo/repo-{index}"
    evidence: list[InternalEvidence] = [
        InternalEvidence(
            evidence_id=f"ev_{index:03d}",
            repository_full_name=repository,
            evidence_type=InternalEvidenceType.GITHUB_STATIC,
            analysis_depth=AnalysisDepth.P0,
            key="TECHNOLOGY_DEPENDENCY",
            summary=f"Framework {index} dependency and README were observed.",
            source_paths=(f"repo-{index}/README.md", f"repo-{index}/build.gradle"),
            technology_names=(f"Framework {index}",),
        )
    ]
    completed_levels = [AnalysisDepth.P0]
    if depth in {AnalysisDepth.P1, AnalysisDepth.P2}:
        completed_levels.append(AnalysisDepth.P1)
        evidence.append(
            InternalEvidence(
                evidence_id=f"ev_{index + 100:03d}",
                repository_full_name=repository,
                evidence_type=InternalEvidenceType.GITHUB_ACTIVITY,
                analysis_depth=AnalysisDepth.P1,
                key="COMMIT_ACTIVITY",
                summary="A commit changed the service path.",
                source_paths=(f"repo-{index}/Service.java",),
                commit_sha=f"commit-{index}",
            )
        )
    if depth is AnalysisDepth.P2:
        completed_levels.append(AnalysisDepth.P2)
        evidence.append(
            InternalEvidence(
                evidence_id=f"ev_{index + 200:03d}",
                repository_full_name=repository,
                evidence_type=InternalEvidenceType.CODE_EVIDENCE,
                analysis_depth=AnalysisDepth.P2,
                key="CODE_SNIPPET",
                summary="if (request == null) throw new IllegalArgumentException();",
                path=f"repo-{index}/Service.java",
                start_line=10,
                end_line=12,
                commit_sha=f"commit-{index}",
                source_evidence_refs=(f"ev_{index + 100:03d}",),
            )
        )

    claim = InternalUserClaim(
        claim_id=f"claim_{index:03d}",
        repository_full_name=repository,
        statement="사용자는 API 구현을 담당했다고 진술했습니다.",
        related_evidence_refs=((f"ev_{index + 100:03d}",) if depth is not AnalysisDepth.P0 else ()),
    )
    return NormalizedRepositoryContext(
        repository_id=str(index),
        repository_full_name=repository,
        analysis_depth=depth,
        completed_evidence_levels=tuple(completed_levels),
        snapshot_hash_algorithm=(
            SnapshotHashAlgorithm.SHA1 if depth is not AnalysisDepth.P0 else None
        ),
        snapshot_sha=f"snapshot-{index}" if depth is not AnalysisDepth.P0 else None,
        evidence=tuple(evidence),
        user_claims=(claim,),
        technology_names=(f"Framework {index}",),
    )


def make_missing_context(index: int = 1) -> NormalizedRepositoryContext:
    context = make_context(index)
    repository = context.repository_full_name
    derived = InternalEvidence(
        evidence_id=f"ev_{index + 300:03d}",
        repository_full_name=repository,
        evidence_type=InternalEvidenceType.BACKEND_DERIVED,
        analysis_depth=AnalysisDepth.P0,
        key="TEST_NOT_OBSERVED",
        summary="Tests were not observed in the collection scope.",
        derived_from_level=AnalysisDepth.P0,
    )
    return context.model_copy(update={"evidence": context.evidence + (derived,)})


def make_item(
    *,
    item_type: AnalysisItemType = AnalysisItemType.INTERPRETATION,
    content: str = "공개 근거에서 포트폴리오 설명 요소가 관찰됩니다.",
    evidence_refs: tuple[str, ...] = ("ev_001",),
    claim_refs: tuple[str, ...] = (),
    criterion_keys: tuple[str, ...] = ("README_READINESS",),
    technology_names: tuple[str, ...] = (),
    file_paths: tuple[str, ...] = (),
) -> GroundedAnalysisItem:
    return GroundedAnalysisItem(
        item_type=item_type,
        content=content,
        confidence=EvidenceConfidence.HIGH,
        evidence_refs=evidence_refs,
        claim_refs=claim_refs,
        criterion_keys=criterion_keys,
        technology_names=technology_names,
        file_paths=file_paths,
        priority=(
            RecommendationPriority.HIGH if item_type is AnalysisItemType.RECOMMENDATION else None
        ),
    )


def make_representative(
    index: int = 1,
    *,
    repository_full_name: str | None = None,
    evidence_refs: tuple[str, ...] | None = None,
    claim_refs: tuple[str, ...] = (),
    reason: str = "공개 근거로 프로젝트 목적을 설명할 수 있습니다.",
) -> RepresentativeProject:
    return RepresentativeProject(
        repository_full_name=repository_full_name or f"git-ddo/repo-{index}",
        reason=reason,
        confidence=EvidenceConfidence.HIGH,
        evidence_refs=evidence_refs if evidence_refs is not None else (f"ev_{index:03d}",),
        claim_refs=claim_refs,
    )


def make_synthesis(
    *,
    overall_summary: GroundedAnalysisItem | None = None,
    representatives: tuple[RepresentativeProject, ...] | None = None,
    strengths: tuple[GroundedAnalysisItem, ...] = (),
    gaps: tuple[GroundedAnalysisItem, ...] = (),
    next_actions: tuple[GroundedAnalysisItem, ...] = (),
    job_appeal: GroundedAnalysisItem | None = None,
    limitations: tuple[str, ...] = ("공개 근거 범위만 분석했습니다.",),
) -> PortfolioSynthesis:
    return PortfolioSynthesis(
        overall_summary=overall_summary or make_item(),
        representative_projects=representatives or (make_representative(),),
        strengths=strengths,
        gaps=gaps,
        next_actions=next_actions,
        job_appeal=job_appeal
        or make_item(
            item_type=AnalysisItemType.JOB_APPEAL,
            content="공개 Evidence를 직무 관련 설명에 활용할 수 있습니다.",
        ),
        limitations=limitations,
    )


def validate_all(
    synthesis: PortfolioSynthesis,
    contexts: tuple[NormalizedRepositoryContext, ...],
    depth: AnalysisDepth,
) -> None:
    validator = PortfolioPolicyValidator()
    validator.validate_references(synthesis, contexts)
    validator.validate_content(
        synthesis,
        contexts,
        CriteriaLoader().load("BACKEND", depth.value),
    )


def violation_codes(error: ReportPolicyError) -> set[PolicyViolationCode]:
    return {violation.code for violation in error.violations}


@pytest.mark.parametrize("repository_count", [1, 5])
def test_accepts_valid_p0_synthesis_for_one_to_five_repositories(
    repository_count: int,
) -> None:
    contexts = tuple(make_context(index) for index in range(1, repository_count + 1))
    evidence_refs = tuple(f"ev_{index:03d}" for index in range(1, repository_count + 1))
    representatives = tuple(make_representative(index) for index in range(1, repository_count + 1))
    synthesis = make_synthesis(
        overall_summary=make_item(evidence_refs=evidence_refs),
        representatives=representatives,
        job_appeal=make_item(
            item_type=AnalysisItemType.JOB_APPEAL,
            evidence_refs=evidence_refs,
        ),
    )

    assert validate_all(synthesis, contexts, AnalysisDepth.P0) is None


def test_accepts_mixed_p0_p1_p2_synthesis() -> None:
    contexts = (
        make_context(1, AnalysisDepth.P0),
        make_context(2, AnalysisDepth.P1),
        make_context(3, AnalysisDepth.P2),
    )
    synthesis = make_synthesis(
        overall_summary=make_item(
            evidence_refs=("ev_001", "ev_102", "ev_203"),
            criterion_keys=("README_READINESS", "ACTIVITY_SCOPE", "SNIPPET_SCOPE"),
        ),
        representatives=tuple(make_representative(index) for index in range(1, 4)),
        strengths=(
            make_item(
                evidence_refs=("ev_203",),
                criterion_keys=("SNIPPET_SCOPE",),
                content="제공된 코드 구간에서 입력 검증 사례가 관찰됩니다.",
                file_paths=("repo-3/Service.java",),
            ),
        ),
    )

    assert validate_all(synthesis, contexts, AnalysisDepth.P2) is None


def test_mixed_depth_item_uses_shallowest_referenced_repository_policy() -> None:
    contexts = (
        make_context(1, AnalysisDepth.P0),
        make_context(2, AnalysisDepth.P2),
    )
    synthesis = make_synthesis(
        overall_summary=make_item(
            evidence_refs=("ev_001", "ev_202"),
            criterion_keys=("README_READINESS", "SNIPPET_SCOPE"),
            content="코드 품질이 우수합니다.",
        ),
        representatives=(make_representative(1), make_representative(2)),
    )

    with pytest.raises(ReportPolicyError) as exc_info:
        PortfolioPolicyValidator().validate_content(
            synthesis,
            contexts,
            CriteriaLoader().load("BACKEND", "P2"),
        )

    assert PolicyViolationCode.P0_SCOPE_VIOLATION in violation_codes(exc_info.value)


def test_representative_reason_uses_shallowest_referenced_evidence_policy() -> None:
    context = make_context(1, AnalysisDepth.P2)
    synthesis = make_synthesis(
        representatives=(
            make_representative(
                1,
                evidence_refs=("ev_001", "ev_201"),
                reason="코드 품질이 우수합니다.",
            ),
        )
    )

    with pytest.raises(ReportPolicyError) as exc_info:
        PortfolioPolicyValidator().validate_content(
            synthesis,
            (context,),
            CriteriaLoader().load("BACKEND", "P2"),
        )

    assert PolicyViolationCode.P0_SCOPE_VIOLATION in violation_codes(exc_info.value)


def test_validation_does_not_mutate_synthesis() -> None:
    context = make_context(1)
    synthesis = make_synthesis()
    before = synthesis.model_dump()

    validate_all(synthesis, (context,), AnalysisDepth.P0)

    assert synthesis.model_dump() == before


@pytest.mark.parametrize(
    ("field", "unknown_ref", "expected_code"),
    [
        ("evidence", "ev_999", PolicyViolationCode.UNKNOWN_EVIDENCE_REF),
        ("claim", "claim_999", PolicyViolationCode.UNKNOWN_CLAIM_REF),
    ],
)
def test_rejects_unknown_global_references(
    field: str,
    unknown_ref: str,
    expected_code: PolicyViolationCode,
) -> None:
    item = make_item(
        evidence_refs=((unknown_ref,) if field == "evidence" else ("ev_001",)),
        claim_refs=((unknown_ref,) if field == "claim" else ()),
    )

    with pytest.raises(ReportPolicyError) as exc_info:
        PortfolioPolicyValidator().validate_references(
            make_synthesis(overall_summary=item),
            (make_context(1),),
        )

    assert expected_code in violation_codes(exc_info.value)


def test_rejects_unknown_representative_repository() -> None:
    synthesis = make_synthesis(
        representatives=(make_representative(repository_full_name="git-ddo/unknown"),)
    )

    with pytest.raises(ReportPolicyError) as exc_info:
        PortfolioPolicyValidator().validate_references(synthesis, (make_context(1),))

    assert exc_info.value.violations[0].field_path == (
        "representative_projects[0].repository_full_name"
    )


@pytest.mark.parametrize("reference_type", ["evidence", "claim"])
def test_rejects_representative_reference_from_another_repository(
    reference_type: str,
) -> None:
    contexts = (make_context(1), make_context(2))
    project = make_representative(
        1,
        evidence_refs=(("ev_002",) if reference_type == "evidence" else ()),
        claim_refs=(("claim_002",) if reference_type == "claim" else ()),
    )

    with pytest.raises(ReportPolicyError) as exc_info:
        PortfolioPolicyValidator().validate_references(
            make_synthesis(representatives=(project,)),
            contexts,
        )

    assert PolicyViolationCode.CROSS_REPOSITORY_REF in violation_codes(exc_info.value)


def test_allows_global_items_to_reference_multiple_repositories() -> None:
    contexts = (make_context(1), make_context(2))
    references = ("ev_001", "ev_002")
    synthesis = make_synthesis(
        overall_summary=make_item(evidence_refs=references),
        representatives=(make_representative(1), make_representative(2)),
        job_appeal=make_item(
            item_type=AnalysisItemType.JOB_APPEAL,
            evidence_refs=references,
        ),
    )

    assert PortfolioPolicyValidator().validate_references(synthesis, contexts) is None


def test_rejects_unknown_criterion() -> None:
    synthesis = make_synthesis(overall_summary=make_item(criterion_keys=("UNKNOWN_CRITERION",)))

    with pytest.raises(ReportPolicyError) as exc_info:
        PortfolioPolicyValidator().validate_content(
            synthesis,
            (make_context(1),),
            CriteriaLoader().load("BACKEND", "P0"),
        )

    assert PolicyViolationCode.UNKNOWN_CRITERION in violation_codes(exc_info.value)


@pytest.mark.parametrize(
    ("context_depth", "criterion_key", "criteria_depth", "expected_code"),
    [
        (
            AnalysisDepth.P0,
            "ACTIVITY_SCOPE",
            AnalysisDepth.P1,
            PolicyViolationCode.P0_SCOPE_VIOLATION,
        ),
        (
            AnalysisDepth.P1,
            "SNIPPET_SCOPE",
            AnalysisDepth.P2,
            PolicyViolationCode.P1_SCOPE_VIOLATION,
        ),
    ],
)
def test_rejects_criterion_above_repository_depth(
    context_depth: AnalysisDepth,
    criterion_key: str,
    criteria_depth: AnalysisDepth,
    expected_code: PolicyViolationCode,
) -> None:
    context = make_context(1, context_depth)
    synthesis = make_synthesis(overall_summary=make_item(criterion_keys=(criterion_key,)))

    with pytest.raises(ReportPolicyError) as exc_info:
        PortfolioPolicyValidator().validate_content(
            synthesis,
            (context,),
            CriteriaLoader().load("BACKEND", criteria_depth.value),
        )

    assert expected_code in violation_codes(exc_info.value)


def test_accepts_p2_evidence_with_p2_criterion() -> None:
    context = make_context(1, AnalysisDepth.P2)
    synthesis = make_synthesis(
        strengths=(
            make_item(
                evidence_refs=("ev_201",),
                criterion_keys=("SNIPPET_SCOPE",),
                content="제공된 코드 구간에서 입력 처리 사례가 관찰됩니다.",
                file_paths=("repo-1/Service.java",),
            ),
        )
    )

    assert validate_all(synthesis, (context,), AnalysisDepth.P2) is None


def test_rejects_evidence_type_and_criterion_mismatch() -> None:
    context = make_context(1, AnalysisDepth.P1)
    synthesis = make_synthesis(
        overall_summary=make_item(
            evidence_refs=("ev_101",),
            criterion_keys=("README_READINESS",),
        )
    )

    with pytest.raises(ReportPolicyError) as exc_info:
        PortfolioPolicyValidator().validate_content(
            synthesis,
            (context,),
            CriteriaLoader().load("BACKEND", "P1"),
        )

    assert PolicyViolationCode.CRITERIA_EVIDENCE_MISMATCH in violation_codes(exc_info.value)


@pytest.mark.parametrize(
    ("technology_names", "file_paths", "expected_code"),
    [
        (("Unknown",), (), PolicyViolationCode.UNKNOWN_TECHNOLOGY),
        ((), ("unknown/path.py",), PolicyViolationCode.UNKNOWN_FILE_PATH),
    ],
)
def test_rejects_unknown_grounding_metadata(
    technology_names: tuple[str, ...],
    file_paths: tuple[str, ...],
    expected_code: PolicyViolationCode,
) -> None:
    synthesis = make_synthesis(
        overall_summary=make_item(
            technology_names=technology_names,
            file_paths=file_paths,
        )
    )

    with pytest.raises(ReportPolicyError) as exc_info:
        PortfolioPolicyValidator().validate_content(
            synthesis,
            (make_context(1),),
            CriteriaLoader().load("BACKEND", "P0"),
        )

    assert expected_code in violation_codes(exc_info.value)


@pytest.mark.parametrize(
    ("technology_names", "file_paths", "expected_code"),
    [
        (("Framework 2",), (), PolicyViolationCode.UNKNOWN_TECHNOLOGY),
        ((), ("repo-2/README.md",), PolicyViolationCode.UNKNOWN_FILE_PATH),
    ],
)
def test_rejects_metadata_from_unreferenced_repository(
    technology_names: tuple[str, ...],
    file_paths: tuple[str, ...],
    expected_code: PolicyViolationCode,
) -> None:
    contexts = (make_context(1), make_context(2))
    synthesis = make_synthesis(
        overall_summary=make_item(
            evidence_refs=("ev_001",),
            technology_names=technology_names,
            file_paths=file_paths,
        ),
        representatives=(make_representative(1), make_representative(2)),
    )

    with pytest.raises(ReportPolicyError) as exc_info:
        PortfolioPolicyValidator().validate_content(
            synthesis,
            contexts,
            CriteriaLoader().load("BACKEND", "P0"),
        )

    assert expected_code in violation_codes(exc_info.value)


def test_accepts_metadata_from_each_referenced_repository() -> None:
    contexts = (make_context(1), make_context(2))
    synthesis = make_synthesis(
        overall_summary=make_item(
            evidence_refs=("ev_001", "ev_002"),
            technology_names=("Framework 1", "Framework 2"),
            file_paths=("repo-1/README.md", "repo-2/README.md"),
        ),
        representatives=(make_representative(1), make_representative(2)),
    )

    assert validate_all(synthesis, contexts, AnalysisDepth.P0) is None


@pytest.mark.parametrize(
    ("depth", "criterion_key", "evidence_ref", "content", "expected_code"),
    [
        (
            AnalysisDepth.P0,
            "README_READINESS",
            "ev_001",
            "프로젝트 전체 코드 품질이 우수합니다.",
            PolicyViolationCode.P0_SCOPE_VIOLATION,
        ),
        (
            AnalysisDepth.P1,
            "ACTIVITY_SCOPE",
            "ev_101",
            "커밋 활동량이 많아 사용자의 기여도가 높습니다.",
            PolicyViolationCode.CONTRIBUTION_ASSERTION,
        ),
        (
            AnalysisDepth.P2,
            "SNIPPET_SCOPE",
            "ev_201",
            "이 snippet으로 프로젝트 전체 아키텍처가 우수함을 확인했습니다.",
            PolicyViolationCode.REPOSITORY_WIDE_GENERALIZATION,
        ),
    ],
)
def test_rejects_depth_specific_content_violation(
    depth: AnalysisDepth,
    criterion_key: str,
    evidence_ref: str,
    content: str,
    expected_code: PolicyViolationCode,
) -> None:
    context = make_context(1, depth)
    synthesis = make_synthesis(
        overall_summary=make_item(
            evidence_refs=(evidence_ref,),
            criterion_keys=(criterion_key,),
            content=content,
        )
    )

    with pytest.raises(ReportPolicyError) as exc_info:
        PortfolioPolicyValidator().validate_content(
            synthesis,
            (context,),
            CriteriaLoader().load("BACKEND", depth.value),
        )

    assert expected_code in violation_codes(exc_info.value)


@pytest.mark.parametrize(
    ("content", "expected_code"),
    [
        (
            "지원자의 개발 역량이 뛰어나 합격 가능성이 높습니다.",
            PolicyViolationCode.USER_ABILITY_ASSERTION,
        ),
        (
            "사용자가 직접 구현한 사실이 GitHub에서 확인되었습니다.",
            PolicyViolationCode.CONTRIBUTION_ASSERTION,
        ),
    ],
)
def test_rejects_common_content_violation(
    content: str,
    expected_code: PolicyViolationCode,
) -> None:
    synthesis = make_synthesis(overall_summary=make_item(content=content))

    with pytest.raises(ReportPolicyError) as exc_info:
        PortfolioPolicyValidator().validate_content(
            synthesis,
            (make_context(1),),
            CriteriaLoader().load("BACKEND", "P0"),
        )

    assert expected_code in violation_codes(exc_info.value)


def test_rejects_claim_only_content_without_attribution() -> None:
    context = make_context(1, AnalysisDepth.P1)
    synthesis = make_synthesis(
        overall_summary=make_item(
            content="인증 API를 담당했습니다.",
            evidence_refs=(),
            claim_refs=("claim_001",),
            criterion_keys=("CLAIM_ACTIVITY_LINK",),
        )
    )

    with pytest.raises(ReportPolicyError) as exc_info:
        PortfolioPolicyValidator().validate_content(
            synthesis,
            (context,),
            CriteriaLoader().load("BACKEND", "P1"),
        )

    assert PolicyViolationCode.USER_CLAIM_AS_FACT in violation_codes(exc_info.value)


def test_rejects_not_observed_as_actual_absence() -> None:
    context = make_missing_context()
    synthesis = make_synthesis(
        gaps=(
            make_item(
                content="테스트가 실제로 존재하지 않습니다.",
                evidence_refs=("ev_301",),
                criterion_keys=("TEST_PRESENCE",),
            ),
        )
    )

    with pytest.raises(ReportPolicyError) as exc_info:
        PortfolioPolicyValidator().validate_content(
            synthesis,
            (context,),
            CriteriaLoader().load("BACKEND", "P0"),
        )

    assert PolicyViolationCode.NOT_OBSERVED_MISUSE in violation_codes(exc_info.value)


@pytest.mark.parametrize("field_name", ["gap", "next_action"])
def test_rejects_missing_item_without_derived_evidence(field_name: str) -> None:
    missing_item = make_item(
        item_type=(
            AnalysisItemType.RECOMMENDATION
            if field_name == "next_action"
            else AnalysisItemType.INTERPRETATION
        ),
        content="테스트가 누락되어 보완해야 합니다.",
        criterion_keys=("TEST_PRESENCE",),
    )
    synthesis = make_synthesis(
        gaps=((missing_item,) if field_name == "gap" else ()),
        next_actions=((missing_item,) if field_name == "next_action" else ()),
    )

    with pytest.raises(ReportPolicyError) as exc_info:
        PortfolioPolicyValidator().validate_content(
            synthesis,
            (make_context(1),),
            CriteriaLoader().load("BACKEND", "P0"),
        )

    assert PolicyViolationCode.MISSING_DERIVED_EVIDENCE in violation_codes(exc_info.value)


@pytest.mark.parametrize("field_name", ["gap", "next_action"])
def test_accepts_missing_item_with_matching_derived_evidence(field_name: str) -> None:
    context = make_missing_context()
    missing_item = make_item(
        item_type=(
            AnalysisItemType.RECOMMENDATION
            if field_name == "next_action"
            else AnalysisItemType.INTERPRETATION
        ),
        content="분석 범위에서 테스트가 확인되지 않아 보완하는 것이 좋습니다.",
        evidence_refs=("ev_301",),
        criterion_keys=("TEST_PRESENCE",),
    )
    synthesis = make_synthesis(
        gaps=((missing_item,) if field_name == "gap" else ()),
        next_actions=((missing_item,) if field_name == "next_action" else ()),
    )

    assert validate_all(synthesis, (context,), AnalysisDepth.P0) is None


@pytest.mark.parametrize("field_name", ["gap", "next_action"])
def test_rejects_missing_item_with_derived_evidence_from_another_repository(
    field_name: str,
) -> None:
    contexts = (make_context(1), make_missing_context(2))
    missing_item = make_item(
        item_type=(
            AnalysisItemType.RECOMMENDATION
            if field_name == "next_action"
            else AnalysisItemType.INTERPRETATION
        ),
        content="분석 범위에서 테스트가 확인되지 않아 보완하는 것이 좋습니다.",
        evidence_refs=("ev_001", "ev_302"),
        criterion_keys=("TEST_PRESENCE",),
    )
    synthesis = make_synthesis(
        representatives=(make_representative(1), make_representative(2)),
        gaps=((missing_item,) if field_name == "gap" else ()),
        next_actions=((missing_item,) if field_name == "next_action" else ()),
    )

    with pytest.raises(ReportPolicyError) as exc_info:
        PortfolioPolicyValidator().validate_content(
            synthesis,
            contexts,
            CriteriaLoader().load("BACKEND", "P0"),
        )

    assert PolicyViolationCode.MISSING_DERIVED_EVIDENCE in violation_codes(exc_info.value)


def test_collects_multiple_violations_with_field_paths() -> None:
    synthesis = make_synthesis(
        overall_summary=make_item(
            content="지원자의 역량이 우수합니다.",
            evidence_refs=("ev_999",),
            technology_names=("Unknown",),
        )
    )
    validator = PortfolioPolicyValidator()

    with pytest.raises(ReportPolicyError) as reference_error:
        validator.validate_references(synthesis, (make_context(1),))
    with pytest.raises(ReportPolicyError) as content_error:
        validator.validate_content(
            synthesis,
            (make_context(1),),
            CriteriaLoader().load("BACKEND", "P0"),
        )

    assert PolicyViolationCode.UNKNOWN_EVIDENCE_REF in violation_codes(reference_error.value)
    assert {
        PolicyViolationCode.UNKNOWN_TECHNOLOGY,
        PolicyViolationCode.USER_ABILITY_ASSERTION,
    }.issubset(violation_codes(content_error.value))
    assert all(violation.field_path is not None for violation in content_error.value.violations)
