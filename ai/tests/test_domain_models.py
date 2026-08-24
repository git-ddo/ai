from collections.abc import Callable

import pytest
from pydantic import ValidationError

from app.domain import (
    AnalysisDepth,
    AnalysisItemType,
    EvidenceConfidence,
    EvidenceValueType,
    GroundedAnalysisItem,
    InternalEvidence,
    InternalEvidenceType,
    InternalGenerationRecord,
    InternalGenerationStage,
    InternalPortfolioInput,
    InternalPortfolioReport,
    InternalRepositoryInput,
    InternalUserClaim,
    InterviewQuestion,
    InterviewQuestionBatch,
    NormalizedRepositoryContext,
    PortfolioAnalysis,
    PortfolioStatement,
    PortfolioStatementType,
    RecommendationPriority,
    RepositoryAnalysis,
    RepresentativeProject,
    SnapshotHashAlgorithm,
)


def make_evidence(
    *,
    evidence_id: str = "ev_001",
    repository_full_name: str = "git-ddo/backend",
    evidence_type: InternalEvidenceType | str = InternalEvidenceType.GITHUB_STATIC,
    analysis_depth: AnalysisDepth | str = AnalysisDepth.P0,
    key: str = "README_INTRODUCTION_OBSERVED",
    summary: str = "README에서 프로젝트 소개가 관찰되었습니다.",
    value_type: EvidenceValueType | str = EvidenceValueType.STRING,
    source_paths: tuple[str, ...] = ("README.md",),
    technology_names: tuple[str, ...] = (),
    path: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    commit_sha: str | None = None,
    pull_request_number: int | None = None,
    source_evidence_refs: tuple[str, ...] = (),
    derived_from_level: AnalysisDepth | str | None = None,
) -> InternalEvidence:
    return InternalEvidence(
        evidence_id=evidence_id,
        repository_full_name=repository_full_name,
        evidence_type=evidence_type,
        analysis_depth=analysis_depth,
        key=key,
        summary=summary,
        value_type=value_type,
        source_paths=source_paths,
        technology_names=technology_names,
        path=path,
        start_line=start_line,
        end_line=end_line,
        commit_sha=commit_sha,
        pull_request_number=pull_request_number,
        source_evidence_refs=source_evidence_refs,
        derived_from_level=derived_from_level,
    )


def make_claim(
    *,
    claim_id: str = "claim_001",
    repository_full_name: str = "git-ddo/backend",
    related_evidence_refs: tuple[str, ...] = (),
) -> InternalUserClaim:
    return InternalUserClaim(
        claim_id=claim_id,
        repository_full_name=repository_full_name,
        statement="사용자는 인증 API를 담당했다고 진술했습니다.",
        related_evidence_refs=related_evidence_refs,
    )


def make_repository_input(
    *,
    repository_id: str = "1",
    repository_full_name: str = "git-ddo/backend",
    analysis_depth: AnalysisDepth = AnalysisDepth.P0,
    completed_evidence_levels: tuple[AnalysisDepth, ...] = (AnalysisDepth.P0,),
    snapshot_hash_algorithm: SnapshotHashAlgorithm | None = None,
    snapshot_sha: str | None = None,
    evidence: tuple[InternalEvidence, ...] | None = None,
    user_claims: tuple[InternalUserClaim, ...] | None = None,
) -> InternalRepositoryInput:
    resolved_evidence = (
        evidence
        if evidence is not None
        else (make_evidence(repository_full_name=repository_full_name),)
    )
    resolved_claims = (
        user_claims
        if user_claims is not None
        else (make_claim(repository_full_name=repository_full_name),)
    )
    return InternalRepositoryInput(
        repository_id=repository_id,
        repository_full_name=repository_full_name,
        description="GitDdo backend",
        analysis_depth=analysis_depth,
        completed_evidence_levels=completed_evidence_levels,
        snapshot_hash_algorithm=snapshot_hash_algorithm,
        snapshot_sha=snapshot_sha,
        evidence=resolved_evidence,
        user_claims=resolved_claims,
    )


def make_interpretation(
    *,
    content: str = "공개 README에서 프로젝트 목적을 설명할 수 있습니다.",
    evidence_refs: tuple[str, ...] = ("ev_001",),
    claim_refs: tuple[str, ...] = (),
) -> GroundedAnalysisItem:
    return GroundedAnalysisItem(
        item_type=AnalysisItemType.INTERPRETATION,
        content=content,
        confidence=EvidenceConfidence.HIGH,
        evidence_refs=evidence_refs,
        claim_refs=claim_refs,
    )


def make_portfolio_repository_input(index: int) -> InternalRepositoryInput:
    repository_full_name = f"git-ddo/repo-{index}"
    return make_repository_input(
        repository_id=str(index),
        repository_full_name=repository_full_name,
        evidence=(
            make_evidence(
                evidence_id=f"ev_{index:03d}",
                repository_full_name=repository_full_name,
            ),
        ),
        user_claims=(
            make_claim(
                claim_id=f"claim_{index:03d}",
                repository_full_name=repository_full_name,
            ),
        ),
    )


def make_activity_evidence(
    *,
    evidence_id: str = "ev_002",
    repository_full_name: str = "git-ddo/backend",
    key: str = "COMMIT_SUMMARY",
    commit_sha: str | None = "abc123",
    pull_request_number: int | None = None,
    source_evidence_refs: tuple[str, ...] = (),
) -> InternalEvidence:
    return make_evidence(
        evidence_id=evidence_id,
        repository_full_name=repository_full_name,
        evidence_type=InternalEvidenceType.GITHUB_ACTIVITY,
        analysis_depth=AnalysisDepth.P1,
        key=key,
        commit_sha=commit_sha,
        pull_request_number=pull_request_number,
        source_evidence_refs=source_evidence_refs,
    )


def make_code_evidence(
    *,
    evidence_id: str = "ev_003",
    repository_full_name: str = "git-ddo/backend",
    source_evidence_refs: tuple[str, ...] = ("ev_002",),
    path: str | None = "src/AuthFilter.java",
    start_line: int | None = 5,
    end_line: int | None = 9,
    commit_sha: str | None = "abc123",
    value_type: EvidenceValueType | str = EvidenceValueType.STRING,
    summary: str = 'public boolean matches(String path) { return path.startsWith("/api"); }',
) -> InternalEvidence:
    return make_evidence(
        evidence_id=evidence_id,
        repository_full_name=repository_full_name,
        evidence_type=InternalEvidenceType.CODE_EVIDENCE,
        analysis_depth=AnalysisDepth.P2,
        key="CODE_SNIPPET",
        summary=summary,
        value_type=value_type,
        source_paths=(),
        path=path,
        start_line=start_line,
        end_line=end_line,
        commit_sha=commit_sha,
        source_evidence_refs=source_evidence_refs,
    )


def make_observation() -> GroundedAnalysisItem:
    return GroundedAnalysisItem(
        item_type=AnalysisItemType.OBSERVATION,
        content="README에서 프로젝트 소개 항목이 관찰되었습니다.",
        confidence=EvidenceConfidence.HIGH,
        evidence_refs=("ev_001",),
    )


def make_recommendation() -> GroundedAnalysisItem:
    return GroundedAnalysisItem(
        item_type=AnalysisItemType.RECOMMENDATION,
        content="백엔드가 미관찰로 도출한 실행 방법을 README에 보완하세요.",
        confidence=EvidenceConfidence.HIGH,
        evidence_refs=("ev_002",),
        priority=RecommendationPriority.HIGH,
    )


def make_job_appeal() -> GroundedAnalysisItem:
    return GroundedAnalysisItem(
        item_type=AnalysisItemType.JOB_APPEAL,
        content="Spring Boot 의존성이 공개 설정에서 확인됩니다.",
        confidence=EvidenceConfidence.HIGH,
        evidence_refs=("ev_001",),
    )


def make_repository_analysis(
    *,
    repository_full_name: str = "git-ddo/backend",
) -> RepositoryAnalysis:
    return RepositoryAnalysis(
        repository_full_name=repository_full_name,
        summary=make_interpretation(),
        observations=(make_observation(),),
        strengths=(make_interpretation(),),
        recommendations=(make_recommendation(),),
        limitations=("P0에서는 코드와 설계 품질을 판단하지 않습니다.",),
    )


def make_interview_question(
    *,
    repository_full_name: str = "git-ddo/backend",
    question: str = "README에 표시된 Spring Boot를 선택한 이유는 무엇인가요?",
) -> InterviewQuestion:
    return InterviewQuestion(
        repository_full_name=repository_full_name,
        question=question,
        intent="공개 기술 근거를 자신의 설명과 연결하는지 확인합니다.",
        answer_guide=("기술 선택 배경을 사용자 경험과 구분해 설명합니다.",),
        follow_up_questions=(),
        evidence_refs=("ev_001",),
        claim_refs=("claim_001",),
    )


def make_portfolio_analysis(
    *,
    repository_analyses: tuple[RepositoryAnalysis, ...] | None = None,
    interview_questions: tuple[InterviewQuestion, ...] | None = None,
) -> PortfolioAnalysis:
    analyses = (
        repository_analyses if repository_analyses is not None else (make_repository_analysis(),)
    )
    representative_name = analyses[0].repository_full_name if analyses else "git-ddo/backend"
    resolved_interview_questions = (
        interview_questions
        if interview_questions is not None
        else (make_interview_question(repository_full_name=representative_name),)
    )
    return PortfolioAnalysis(
        overall_summary=make_interpretation(
            content="공개 P0 근거에서 백엔드 프로젝트 설명 요소가 관찰됩니다."
        ),
        repository_analyses=analyses,
        representative_projects=(
            RepresentativeProject(
                repository_full_name=representative_name,
                reason="README와 기술 설정 근거를 함께 설명할 수 있습니다.",
                confidence=EvidenceConfidence.HIGH,
                evidence_refs=("ev_001",),
            ),
        ),
        job_appeal=(make_job_appeal(),),
        recommendations=(make_recommendation(),),
        interview_questions=resolved_interview_questions,
        portfolio_statements=(
            PortfolioStatement(
                statement_type=PortfolioStatementType.PORTFOLIO,
                content="Spring Boot 기반 백엔드 프로젝트를 구성했습니다.",
                evidence_refs=("ev_001",),
                claim_refs=("claim_001",),
            ),
        ),
        limitations=("공개 P0 근거만 사용한 분석입니다.",),
    )


def make_generation_records(
    analysis: PortfolioAnalysis,
) -> tuple[InternalGenerationRecord, ...]:
    repository_records = tuple(
        InternalGenerationRecord(
            stage=InternalGenerationStage.REPOSITORY,
            repository_full_name=repository.repository_full_name,
            duration_ms=10,
            attempt_count=1,
        )
        for repository in analysis.repository_analyses
    )
    portfolio_record = InternalGenerationRecord(
        stage=InternalGenerationStage.PORTFOLIO,
        duration_ms=20,
        attempt_count=1,
    )
    interview_records = tuple(
        InternalGenerationRecord(
            stage=InternalGenerationStage.INTERVIEW,
            repository_full_name=repository_full_name,
            duration_ms=10,
            attempt_count=1,
        )
        for repository_full_name in dict.fromkeys(
            question.repository_full_name for question in analysis.interview_questions
        )
    )
    return repository_records + (portfolio_record,) + interview_records


def test_creates_valid_p0_repository_input() -> None:
    repository = make_repository_input()

    assert repository.analysis_depth is AnalysisDepth.P0
    assert repository.evidence[0].evidence_type is InternalEvidenceType.GITHUB_STATIC
    assert repository.user_claims[0].claim_id == "claim_001"


def test_exposes_p0_p1_p2_depths_and_all_evidence_types() -> None:
    assert tuple(depth.value for depth in AnalysisDepth) == ("P0", "P1", "P2")
    assert {evidence_type.value for evidence_type in InternalEvidenceType} == {
        "GITHUB_STATIC",
        "GITHUB_ACTIVITY",
        "CODE_EVIDENCE",
        "BACKEND_DERIVED",
    }


@pytest.mark.parametrize("repository_id", ["1", "123456789"])
def test_accepts_positive_numeric_repository_id_strings(repository_id: str) -> None:
    repository = make_repository_input(repository_id=repository_id)

    assert repository.repository_id == repository_id


@pytest.mark.parametrize("repository_id", [1, "", "0", "-1", "repo-123", "001"])
def test_rejects_invalid_repository_id_values(repository_id: object) -> None:
    with pytest.raises(ValidationError):
        make_repository_input(repository_id=repository_id)  # type: ignore[arg-type]


def test_creates_valid_p0_backend_derived_evidence() -> None:
    evidence = make_evidence(
        evidence_type=InternalEvidenceType.BACKEND_DERIVED,
        derived_from_level=AnalysisDepth.P0,
    )

    assert evidence.derived_from_level is AnalysisDepth.P0


@pytest.mark.parametrize("analysis_depth", [AnalysisDepth.P1, AnalysisDepth.P2])
def test_creates_valid_deeper_backend_derived_evidence(
    analysis_depth: AnalysisDepth,
) -> None:
    evidence = make_evidence(
        evidence_type=InternalEvidenceType.BACKEND_DERIVED,
        analysis_depth=analysis_depth,
        derived_from_level=analysis_depth,
    )

    assert evidence.derived_from_level is analysis_depth


def test_creates_valid_p1_commit_evidence() -> None:
    evidence = make_activity_evidence()

    assert evidence.analysis_depth is AnalysisDepth.P1
    assert evidence.commit_sha == "abc123"


def test_creates_valid_p1_pull_request_evidence() -> None:
    evidence = make_activity_evidence(
        evidence_id="ev_004",
        key="PULL_REQUEST",
        commit_sha="def456",
        pull_request_number=12,
    )

    assert evidence.pull_request_number == 12


def test_creates_valid_p1_changed_files_evidence() -> None:
    evidence = make_activity_evidence(
        evidence_id="ev_003",
        key="CHANGED_FILES",
        source_evidence_refs=("ev_002",),
    )

    assert evidence.source_evidence_refs == ("ev_002",)


def test_creates_valid_p2_code_evidence() -> None:
    evidence = make_code_evidence()

    assert evidence.analysis_depth is AnalysisDepth.P2
    assert evidence.path == "src/AuthFilter.java"
    assert (evidence.start_line, evidence.end_line) == (5, 9)
    assert evidence.source_evidence_refs == ("ev_002",)


def test_creates_valid_p1_repository_input() -> None:
    repository = make_repository_input(
        analysis_depth=AnalysisDepth.P1,
        completed_evidence_levels=(AnalysisDepth.P0, AnalysisDepth.P1),
        snapshot_hash_algorithm=SnapshotHashAlgorithm.SHA1,
        snapshot_sha="commit-sha",
        evidence=(make_activity_evidence(),),
    )

    assert repository.completed_evidence_levels == (AnalysisDepth.P0, AnalysisDepth.P1)


def test_creates_valid_p2_repository_input_with_p1_source() -> None:
    repository = make_repository_input(
        analysis_depth=AnalysisDepth.P2,
        completed_evidence_levels=(AnalysisDepth.P0, AnalysisDepth.P1, AnalysisDepth.P2),
        snapshot_hash_algorithm=SnapshotHashAlgorithm.SHA1,
        snapshot_sha="commit-sha",
        evidence=(make_activity_evidence(), make_code_evidence()),
    )

    assert repository.analysis_depth is AnalysisDepth.P2


def test_creates_portfolio_with_mixed_repository_depths() -> None:
    p0_repository = make_repository_input(
        repository_id="1",
        repository_full_name="git-ddo/p0",
        evidence=(make_evidence(evidence_id="ev_001", repository_full_name="git-ddo/p0"),),
        user_claims=(make_claim(claim_id="claim_001", repository_full_name="git-ddo/p0"),),
    )
    p1_repository = make_repository_input(
        repository_id="2",
        repository_full_name="git-ddo/p1",
        analysis_depth=AnalysisDepth.P1,
        completed_evidence_levels=(AnalysisDepth.P0, AnalysisDepth.P1),
        snapshot_hash_algorithm=SnapshotHashAlgorithm.SHA1,
        snapshot_sha="p1-snapshot",
        evidence=(make_activity_evidence(evidence_id="ev_002", repository_full_name="git-ddo/p1"),),
        user_claims=(make_claim(claim_id="claim_002", repository_full_name="git-ddo/p1"),),
    )
    p2_repository = make_repository_input(
        repository_id="3",
        repository_full_name="git-ddo/p2",
        analysis_depth=AnalysisDepth.P2,
        completed_evidence_levels=(AnalysisDepth.P0, AnalysisDepth.P1, AnalysisDepth.P2),
        snapshot_hash_algorithm=SnapshotHashAlgorithm.SHA256,
        snapshot_sha="p2-snapshot",
        evidence=(
            make_activity_evidence(evidence_id="ev_003", repository_full_name="git-ddo/p2"),
            make_code_evidence(
                evidence_id="ev_004",
                repository_full_name="git-ddo/p2",
                source_evidence_refs=("ev_003",),
            ),
        ),
        user_claims=(make_claim(claim_id="claim_003", repository_full_name="git-ddo/p2"),),
    )

    portfolio = InternalPortfolioInput(repositories=(p0_repository, p1_repository, p2_repository))

    assert tuple(repository.analysis_depth for repository in portfolio.repositories) == (
        AnalysisDepth.P0,
        AnalysisDepth.P1,
        AnalysisDepth.P2,
    )


@pytest.mark.parametrize(
    ("evidence_type", "analysis_depth"),
    [
        (InternalEvidenceType.GITHUB_STATIC, AnalysisDepth.P1),
        (InternalEvidenceType.GITHUB_STATIC, AnalysisDepth.P2),
        (InternalEvidenceType.GITHUB_ACTIVITY, AnalysisDepth.P0),
        (InternalEvidenceType.GITHUB_ACTIVITY, AnalysisDepth.P2),
        (InternalEvidenceType.CODE_EVIDENCE, AnalysisDepth.P0),
        (InternalEvidenceType.CODE_EVIDENCE, AnalysisDepth.P1),
    ],
)
def test_rejects_evidence_type_depth_mismatch(
    evidence_type: InternalEvidenceType,
    analysis_depth: AnalysisDepth,
) -> None:
    with pytest.raises(ValidationError, match="requires analysis depth"):
        make_evidence(
            evidence_type=evidence_type,
            analysis_depth=analysis_depth,
        )


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("path", None),
        ("start_line", None),
        ("end_line", None),
        ("commit_sha", None),
        ("source_evidence_refs", ()),
    ],
)
def test_rejects_p2_code_evidence_missing_required_metadata(
    field_name: str,
    field_value: object,
) -> None:
    values: dict[str, object] = {
        "path": "src/AuthFilter.java",
        "start_line": 5,
        "end_line": 9,
        "commit_sha": "abc123",
        "source_evidence_refs": ("ev_002",),
    }
    values[field_name] = field_value

    with pytest.raises(ValidationError):
        make_code_evidence(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(("start_line", "end_line"), [(0, 1), (1, 0), (10, 9)])
def test_rejects_invalid_p2_line_range(start_line: int, end_line: int) -> None:
    with pytest.raises(ValidationError):
        make_code_evidence(start_line=start_line, end_line=end_line)


def test_rejects_non_string_p2_value_type() -> None:
    with pytest.raises(ValidationError, match="requires STRING value_type"):
        make_code_evidence(value_type=EvidenceValueType.INTEGER)


def test_rejects_blank_p2_snippet_value() -> None:
    with pytest.raises(ValidationError):
        make_code_evidence(summary="   ")


def test_rejects_duplicate_source_evidence_refs() -> None:
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        make_activity_evidence(source_evidence_refs=("ev_001", "ev_001"))


def test_rejects_invalid_source_evidence_ref_format() -> None:
    with pytest.raises(ValidationError):
        make_activity_evidence(source_evidence_refs=("invalid",))


def test_rejects_self_source_evidence_ref() -> None:
    with pytest.raises(ValidationError, match="must not reference itself"):
        make_activity_evidence(evidence_id="ev_002", source_evidence_refs=("ev_002",))


def test_rejects_duplicate_claim_related_evidence_refs() -> None:
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        make_claim(related_evidence_refs=("ev_001", "ev_001"))


def test_rejects_invalid_claim_related_evidence_ref_format() -> None:
    with pytest.raises(ValidationError):
        make_claim(related_evidence_refs=("invalid",))


def test_rejects_non_positive_pull_request_number() -> None:
    with pytest.raises(ValidationError):
        make_activity_evidence(pull_request_number=0)


def test_domain_model_defers_missing_reference_check_to_reference_validator() -> None:
    evidence = make_activity_evidence(source_evidence_refs=("ev_999",))
    claim = make_claim(related_evidence_refs=("ev_998",))

    assert evidence.source_evidence_refs == ("ev_999",)
    assert claim.related_evidence_refs == ("ev_998",)


@pytest.mark.parametrize(
    "completed_evidence_levels",
    [
        (AnalysisDepth.P1,),
        (AnalysisDepth.P2,),
        (AnalysisDepth.P0, AnalysisDepth.P2),
        (AnalysisDepth.P1, AnalysisDepth.P0),
        (AnalysisDepth.P0, AnalysisDepth.P0),
    ],
)
def test_rejects_non_prefix_completed_evidence_levels(
    completed_evidence_levels: tuple[AnalysisDepth, ...],
) -> None:
    with pytest.raises(ValidationError, match="ordered P0-to-analysis_depth prefix"):
        make_repository_input(completed_evidence_levels=completed_evidence_levels)


def test_rejects_analysis_depth_not_matching_completed_evidence_levels() -> None:
    with pytest.raises(ValidationError, match="ordered P0-to-analysis_depth prefix"):
        make_repository_input(
            analysis_depth=AnalysisDepth.P1,
            completed_evidence_levels=(AnalysisDepth.P0,),
            snapshot_hash_algorithm=SnapshotHashAlgorithm.SHA1,
            snapshot_sha="commit-sha",
        )


def test_rejects_evidence_depth_not_declared_by_repository() -> None:
    with pytest.raises(ValidationError, match="evidence depth must be included"):
        make_repository_input(evidence=(make_activity_evidence(),))


def test_rejects_p1_repository_without_snapshot_metadata() -> None:
    with pytest.raises(ValidationError, match="requires snapshot metadata"):
        make_repository_input(
            analysis_depth=AnalysisDepth.P1,
            completed_evidence_levels=(AnalysisDepth.P0, AnalysisDepth.P1),
            evidence=(make_activity_evidence(),),
        )


def test_rejects_partial_snapshot_metadata() -> None:
    with pytest.raises(ValidationError, match="must be provided together"):
        make_repository_input(
            snapshot_hash_algorithm=SnapshotHashAlgorithm.SHA1,
        )


def test_rejects_backend_derived_evidence_without_matching_derived_level() -> None:
    with pytest.raises(ValidationError, match="requires derived_from_level"):
        make_evidence(evidence_type=InternalEvidenceType.BACKEND_DERIVED)

    with pytest.raises(ValidationError, match="must match analysis_depth"):
        make_evidence(
            evidence_type=InternalEvidenceType.BACKEND_DERIVED,
            analysis_depth=AnalysisDepth.P1,
            derived_from_level=AnalysisDepth.P0,
        )


def test_rejects_derived_level_on_non_derived_evidence() -> None:
    with pytest.raises(ValidationError, match="only allowed for BACKEND_DERIVED"):
        make_evidence(derived_from_level=AnalysisDepth.P0)


def test_creates_evidence_with_explicit_technology_names() -> None:
    evidence = make_evidence(technology_names=("Spring Boot", "PostgreSQL"))

    assert evidence.technology_names == ("Spring Boot", "PostgreSQL")


def test_rejects_blank_technology_name() -> None:
    with pytest.raises(ValidationError):
        make_evidence(technology_names=("   ",))


def test_creates_normalized_repository_context() -> None:
    evidence = make_evidence(technology_names=("Spring Boot",))
    context = NormalizedRepositoryContext(
        repository_id="1",
        repository_full_name="git-ddo/backend",
        description="GitDdo backend",
        analysis_depth=AnalysisDepth.P0,
        evidence=(evidence,),
        user_claims=(make_claim(),),
        technology_names=("Spring Boot",),
    )

    assert context.evidence == (evidence,)
    assert context.technology_names == ("Spring Boot",)


def test_normalized_context_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        NormalizedRepositoryContext(
            repository_id="1",
            repository_full_name="git-ddo/backend",
            analysis_depth=AnalysisDepth.P0,
            evidence=(make_evidence(),),
            contract_version="1.0",
        )


def test_normalized_context_is_frozen() -> None:
    context = NormalizedRepositoryContext(
        repository_id="1",
        repository_full_name="git-ddo/backend",
        analysis_depth=AnalysisDepth.P0,
        evidence=(make_evidence(),),
    )

    with pytest.raises(ValidationError, match="Instance is frozen"):
        context.description = "변경할 수 없습니다."  # type: ignore[misc]


def test_normalized_context_rejects_empty_evidence() -> None:
    with pytest.raises(ValidationError):
        NormalizedRepositoryContext(
            repository_id="1",
            repository_full_name="git-ddo/backend",
            analysis_depth=AnalysisDepth.P0,
            evidence=(),
        )


def test_normalized_context_rejects_duplicate_evidence_ids() -> None:
    with pytest.raises(ValidationError, match="evidence IDs must be unique"):
        NormalizedRepositoryContext(
            repository_id="1",
            repository_full_name="git-ddo/backend",
            analysis_depth=AnalysisDepth.P0,
            evidence=(make_evidence(), make_evidence()),
        )


def test_normalized_context_rejects_duplicate_claim_ids() -> None:
    with pytest.raises(ValidationError, match="claim IDs must be unique"):
        NormalizedRepositoryContext(
            repository_id="1",
            repository_full_name="git-ddo/backend",
            analysis_depth=AnalysisDepth.P0,
            evidence=(make_evidence(),),
            user_claims=(make_claim(), make_claim()),
        )


def test_normalized_context_rejects_evidence_from_another_repository() -> None:
    with pytest.raises(ValidationError, match="evidence must belong"):
        NormalizedRepositoryContext(
            repository_id="1",
            repository_full_name="git-ddo/backend",
            analysis_depth=AnalysisDepth.P0,
            evidence=(make_evidence(repository_full_name="git-ddo/frontend"),),
        )


def test_normalized_context_rejects_claim_from_another_repository() -> None:
    with pytest.raises(ValidationError, match="user claims must belong"):
        NormalizedRepositoryContext(
            repository_id="1",
            repository_full_name="git-ddo/backend",
            analysis_depth=AnalysisDepth.P0,
            evidence=(make_evidence(),),
            user_claims=(make_claim(repository_full_name="git-ddo/frontend"),),
        )


def test_creates_valid_repository_analysis() -> None:
    analysis = make_repository_analysis()

    assert analysis.summary.item_type is AnalysisItemType.INTERPRETATION
    assert analysis.observations[0].item_type is AnalysisItemType.OBSERVATION
    assert analysis.recommendations[0].priority is RecommendationPriority.HIGH


def test_creates_valid_portfolio_analysis() -> None:
    analysis = make_portfolio_analysis()

    assert len(analysis.repository_analyses) == 1
    assert analysis.job_appeal[0].item_type is AnalysisItemType.JOB_APPEAL
    assert analysis.portfolio_statements[0].evidence_refs == ("ev_001",)


def test_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        InternalEvidence(
            evidence_id="ev_001",
            repository_full_name="git-ddo/backend",
            evidence_type=InternalEvidenceType.GITHUB_STATIC,
            key="README_OBSERVED",
            summary="README가 관찰되었습니다.",
            source_paths=("README.md",),
            contract_version="1.0",
        )


@pytest.mark.parametrize(
    ("factory", "kwargs"),
    [
        (make_evidence, {"repository_full_name": "   "}),
        (make_claim, {"repository_full_name": "   "}),
    ],
)
def test_rejects_blank_strings(
    factory: Callable[..., object],
    kwargs: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        factory(**kwargs)


def test_models_are_frozen() -> None:
    evidence = make_evidence()

    with pytest.raises(ValidationError, match="Instance is frozen"):
        evidence.summary = "변경할 수 없습니다."  # type: ignore[misc]


def test_rejects_unknown_analysis_depth() -> None:
    with pytest.raises(ValidationError):
        InternalRepositoryInput(
            repository_id="1",
            repository_full_name="git-ddo/backend",
            analysis_depth="P3",
            evidence=(make_evidence(),),
        )


def test_rejects_activity_evidence_without_p1_depth() -> None:
    with pytest.raises(ValidationError):
        make_evidence(evidence_type="GITHUB_ACTIVITY")


def test_rejects_empty_evidence_collection() -> None:
    with pytest.raises(ValidationError):
        InternalRepositoryInput(
            repository_id="1",
            repository_full_name="git-ddo/backend",
            analysis_depth=AnalysisDepth.P0,
            evidence=(),
        )


def test_rejects_duplicate_evidence_ids() -> None:
    with pytest.raises(ValidationError, match="evidence IDs must be unique"):
        make_repository_input(evidence=(make_evidence(), make_evidence()))


def test_rejects_duplicate_claim_ids() -> None:
    with pytest.raises(ValidationError, match="claim IDs must be unique"):
        make_repository_input(user_claims=(make_claim(), make_claim()))


def test_rejects_evidence_from_another_repository() -> None:
    with pytest.raises(ValidationError, match="evidence must belong"):
        make_repository_input(evidence=(make_evidence(repository_full_name="git-ddo/frontend"),))


def test_rejects_claim_from_another_repository() -> None:
    with pytest.raises(ValidationError, match="user claims must belong"):
        make_repository_input(user_claims=(make_claim(repository_full_name="git-ddo/frontend"),))


@pytest.mark.parametrize(
    "item_type",
    [
        AnalysisItemType.OBSERVATION,
        AnalysisItemType.RECOMMENDATION,
        AnalysisItemType.JOB_APPEAL,
    ],
)
def test_evidence_required_item_types_reject_missing_evidence(
    item_type: AnalysisItemType,
) -> None:
    with pytest.raises(ValidationError, match="requires at least one evidence ref"):
        GroundedAnalysisItem(
            item_type=item_type,
            content="근거가 필요한 항목입니다.",
            confidence=EvidenceConfidence.NOT_VERIFIABLE,
            claim_refs=("claim_001",),
            priority=(
                RecommendationPriority.HIGH
                if item_type is AnalysisItemType.RECOMMENDATION
                else None
            ),
        )


def test_interpretation_rejects_missing_references() -> None:
    with pytest.raises(ValidationError, match="requires an evidence or claim ref"):
        GroundedAnalysisItem(
            item_type=AnalysisItemType.INTERPRETATION,
            content="참조가 없는 해석입니다.",
            confidence=EvidenceConfidence.NOT_VERIFIABLE,
        )


def test_recommendation_requires_priority() -> None:
    with pytest.raises(ValidationError, match="requires a priority"):
        GroundedAnalysisItem(
            item_type=AnalysisItemType.RECOMMENDATION,
            content="우선순위가 없는 추천입니다.",
            confidence=EvidenceConfidence.HIGH,
            evidence_refs=("ev_001",),
        )


def test_interview_question_rejects_missing_references() -> None:
    with pytest.raises(ValidationError, match="requires an evidence or claim ref"):
        InterviewQuestion(
            repository_full_name="git-ddo/backend",
            question="프로젝트를 설명해 주세요.",
            intent="프로젝트 이해도를 확인합니다.",
            answer_guide=("공개 근거를 기준으로 설명합니다.",),
        )


def test_portfolio_statement_rejects_missing_references() -> None:
    with pytest.raises(ValidationError, match="requires an evidence or claim ref"):
        PortfolioStatement(
            statement_type=PortfolioStatementType.RESUME,
            content="근거 없는 포트폴리오 문장입니다.",
        )


@pytest.mark.parametrize("repository_count", [0, 6])
def test_rejects_repository_analysis_count_outside_one_to_five(
    repository_count: int,
) -> None:
    analyses = tuple(
        make_repository_analysis(repository_full_name=f"git-ddo/repo-{index}")
        for index in range(repository_count)
    )

    with pytest.raises(ValidationError):
        make_portfolio_analysis(repository_analyses=analyses)


def test_rejects_duplicate_repository_analysis_names() -> None:
    analyses = (make_repository_analysis(), make_repository_analysis())

    with pytest.raises(ValidationError, match="repository analysis names must be unique"):
        make_portfolio_analysis(repository_analyses=analyses)


@pytest.mark.parametrize("repository_count", [1, 5])
def test_creates_internal_portfolio_input_with_one_to_five_repositories(
    repository_count: int,
) -> None:
    repositories = tuple(
        make_portfolio_repository_input(index) for index in range(1, repository_count + 1)
    )

    portfolio_input = InternalPortfolioInput(repositories=repositories)

    assert portfolio_input.repositories == repositories


@pytest.mark.parametrize("repository_count", [0, 6])
def test_rejects_internal_portfolio_input_outside_repository_limit(
    repository_count: int,
) -> None:
    repositories = tuple(
        make_portfolio_repository_input(index) for index in range(1, repository_count + 1)
    )

    with pytest.raises(ValidationError):
        InternalPortfolioInput(repositories=repositories)


def test_internal_portfolio_input_rejects_duplicate_repository_id() -> None:
    repositories = (
        make_portfolio_repository_input(1),
        make_repository_input(
            repository_id="1",
            repository_full_name="git-ddo/other",
            evidence=(make_evidence(evidence_id="ev_002", repository_full_name="git-ddo/other"),),
            user_claims=(make_claim(claim_id="claim_002", repository_full_name="git-ddo/other"),),
        ),
    )

    with pytest.raises(ValidationError, match="duplicate repository ID"):
        InternalPortfolioInput(repositories=repositories)


def test_internal_portfolio_input_rejects_duplicate_repository_full_name() -> None:
    repositories = (
        make_portfolio_repository_input(1),
        make_repository_input(
            repository_id="2",
            repository_full_name="git-ddo/repo-1",
            evidence=(make_evidence(evidence_id="ev_002", repository_full_name="git-ddo/repo-1"),),
            user_claims=(make_claim(claim_id="claim_002", repository_full_name="git-ddo/repo-1"),),
        ),
    )

    with pytest.raises(ValidationError, match="duplicate repository full name"):
        InternalPortfolioInput(repositories=repositories)


def test_internal_portfolio_input_rejects_evidence_id_reused_across_repositories() -> None:
    first = make_portfolio_repository_input(1)
    second_name = "git-ddo/repo-2"
    second = make_repository_input(
        repository_id="2",
        repository_full_name=second_name,
        evidence=(make_evidence(evidence_id="ev_001", repository_full_name=second_name),),
        user_claims=(make_claim(claim_id="claim_002", repository_full_name=second_name),),
    )

    with pytest.raises(ValidationError, match="duplicate evidence ID across repositories"):
        InternalPortfolioInput(repositories=(first, second))


def test_internal_portfolio_input_rejects_claim_id_reused_across_repositories() -> None:
    first = make_portfolio_repository_input(1)
    second_name = "git-ddo/repo-2"
    second = make_repository_input(
        repository_id="2",
        repository_full_name=second_name,
        evidence=(make_evidence(evidence_id="ev_002", repository_full_name=second_name),),
        user_claims=(make_claim(claim_id="claim_001", repository_full_name=second_name),),
    )

    with pytest.raises(ValidationError, match="duplicate claim ID across repositories"):
        InternalPortfolioInput(repositories=(first, second))


def test_internal_portfolio_input_keeps_same_evidence_content_with_distinct_ids() -> None:
    repositories = tuple(make_portfolio_repository_input(index) for index in (1, 2))

    portfolio_input = InternalPortfolioInput(repositories=repositories)

    assert tuple(
        repository.evidence[0].evidence_id for repository in portfolio_input.repositories
    ) == ("ev_001", "ev_002")
    assert portfolio_input.repositories[0].evidence[0].summary == (
        portfolio_input.repositories[1].evidence[0].summary
    )


def test_internal_portfolio_input_preserves_repository_order() -> None:
    repositories = tuple(make_portfolio_repository_input(index) for index in (3, 1, 2))

    portfolio_input = InternalPortfolioInput(repositories=repositories)

    assert tuple(repository.repository_id for repository in portfolio_input.repositories) == (
        "3",
        "1",
        "2",
    )


def test_internal_portfolio_input_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        InternalPortfolioInput(
            repositories=(make_portfolio_repository_input(1),),
            contract_version="1.0",
        )


def test_internal_portfolio_input_is_frozen() -> None:
    portfolio_input = InternalPortfolioInput(repositories=(make_portfolio_repository_input(1),))

    with pytest.raises(ValidationError, match="Instance is frozen"):
        portfolio_input.repositories = ()  # type: ignore[misc]


@pytest.mark.parametrize("question_count", [1, 10])
def test_creates_interview_question_batch_with_one_to_ten_questions(
    question_count: int,
) -> None:
    questions = tuple(
        make_interview_question(question=f"백엔드 질문 {index}") for index in range(question_count)
    )

    batch = InterviewQuestionBatch(questions=questions)

    assert batch.questions == questions


@pytest.mark.parametrize("question_count", [0, 11])
def test_rejects_interview_question_batch_outside_question_limit(
    question_count: int,
) -> None:
    questions = tuple(
        make_interview_question(question=f"백엔드 질문 {index}") for index in range(question_count)
    )

    with pytest.raises(ValidationError):
        InterviewQuestionBatch(questions=questions)


def test_interview_question_batch_rejects_multiple_repositories() -> None:
    questions = (
        make_interview_question(repository_full_name="git-ddo/backend"),
        make_interview_question(
            repository_full_name="git-ddo/other",
            question="다른 저장소에 관한 질문입니다.",
        ),
    )

    with pytest.raises(ValidationError, match="must reference one repository"):
        InterviewQuestionBatch(questions=questions)


@pytest.mark.parametrize(
    "duplicate_question",
    [
        "Spring Boot 질문",
        "  Spring Boot 질문  ",
        "SPRING BOOT 질문",
    ],
)
def test_interview_question_batch_rejects_duplicate_question_text(
    duplicate_question: str,
) -> None:
    questions = (
        make_interview_question(question="Spring Boot 질문"),
        make_interview_question(question=duplicate_question),
    )

    with pytest.raises(ValidationError, match="interview questions must be unique"):
        InterviewQuestionBatch(questions=questions)


def test_interview_question_batch_preserves_question_order() -> None:
    questions = tuple(
        make_interview_question(question=question) for question in ("세 번째", "첫 번째", "두 번째")
    )

    batch = InterviewQuestionBatch(questions=questions)

    assert tuple(question.question for question in batch.questions) == (
        "세 번째",
        "첫 번째",
        "두 번째",
    )


def test_interview_question_batch_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        InterviewQuestionBatch(
            questions=(make_interview_question(),),
            analysis_id="not-an-internal-field",
        )


@pytest.mark.parametrize(
    "stage",
    [InternalGenerationStage.REPOSITORY, InternalGenerationStage.INTERVIEW],
)
def test_repository_scoped_generation_record_requires_repository_name(
    stage: InternalGenerationStage,
) -> None:
    with pytest.raises(ValidationError, match="requires a repository full name"):
        InternalGenerationRecord(stage=stage, duration_ms=0, attempt_count=1)


def test_portfolio_generation_record_rejects_repository_name() -> None:
    with pytest.raises(ValidationError, match="must not reference a repository"):
        InternalGenerationRecord(
            stage=InternalGenerationStage.PORTFOLIO,
            repository_full_name="git-ddo/backend",
            duration_ms=0,
            attempt_count=1,
        )


@pytest.mark.parametrize(
    ("duration_ms", "attempt_count"),
    [(-1, 1), (0, 0), (0, -1)],
)
def test_generation_record_rejects_invalid_metrics(
    duration_ms: int,
    attempt_count: int,
) -> None:
    with pytest.raises(ValidationError):
        InternalGenerationRecord(
            stage=InternalGenerationStage.PORTFOLIO,
            duration_ms=duration_ms,
            attempt_count=attempt_count,
        )


def test_creates_valid_internal_generation_records() -> None:
    repository_record = InternalGenerationRecord(
        stage=InternalGenerationStage.REPOSITORY,
        repository_full_name="git-ddo/backend",
        duration_ms=12,
        attempt_count=2,
    )
    portfolio_record = InternalGenerationRecord(
        stage=InternalGenerationStage.PORTFOLIO,
        duration_ms=20,
        attempt_count=1,
    )

    assert repository_record.repository_full_name == "git-ddo/backend"
    assert portfolio_record.repository_full_name is None


@pytest.mark.parametrize("repository_count", [1, 5])
def test_creates_internal_portfolio_report_for_one_to_five_repositories(
    repository_count: int,
) -> None:
    analyses = tuple(
        make_repository_analysis(repository_full_name=f"git-ddo/repo-{index}")
        for index in range(1, repository_count + 1)
    )
    analysis = make_portfolio_analysis(repository_analyses=analyses)
    records = make_generation_records(analysis)

    report = InternalPortfolioReport(analysis=analysis, generation_records=records)

    assert report.analysis is analysis
    assert report.generation_records == records


def test_internal_portfolio_report_rejects_empty_generation_records() -> None:
    with pytest.raises(ValidationError):
        InternalPortfolioReport(
            analysis=make_portfolio_analysis(),
            generation_records=(),
        )


def test_internal_portfolio_report_requires_one_portfolio_record() -> None:
    analysis = make_portfolio_analysis()
    records = tuple(
        record
        for record in make_generation_records(analysis)
        if record.stage is not InternalGenerationStage.PORTFOLIO
    )

    with pytest.raises(ValidationError, match="exactly one PORTFOLIO"):
        InternalPortfolioReport(analysis=analysis, generation_records=records)


def test_internal_portfolio_report_rejects_duplicate_portfolio_records() -> None:
    analysis = make_portfolio_analysis()
    records = make_generation_records(analysis)
    portfolio_record = next(
        record for record in records if record.stage is InternalGenerationStage.PORTFOLIO
    )

    with pytest.raises(ValidationError, match="exactly one PORTFOLIO"):
        InternalPortfolioReport(
            analysis=analysis,
            generation_records=records + (portfolio_record,),
        )


def test_internal_portfolio_report_rejects_missing_repository_record() -> None:
    analysis = make_portfolio_analysis()
    records = tuple(
        record
        for record in make_generation_records(analysis)
        if record.stage is not InternalGenerationStage.REPOSITORY
    )

    with pytest.raises(ValidationError, match="must match all analyzed repositories"):
        InternalPortfolioReport(analysis=analysis, generation_records=records)


def test_internal_portfolio_report_rejects_unanalyzed_repository_record() -> None:
    analysis = make_portfolio_analysis()
    unexpected_record = InternalGenerationRecord(
        stage=InternalGenerationStage.REPOSITORY,
        repository_full_name="git-ddo/other",
        duration_ms=10,
        attempt_count=1,
    )

    with pytest.raises(ValidationError, match="must match all analyzed repositories"):
        InternalPortfolioReport(
            analysis=analysis,
            generation_records=make_generation_records(analysis) + (unexpected_record,),
        )


def test_internal_portfolio_report_rejects_duplicate_repository_record() -> None:
    analysis = make_portfolio_analysis()
    records = make_generation_records(analysis)
    repository_record = next(
        record for record in records if record.stage is InternalGenerationStage.REPOSITORY
    )

    with pytest.raises(ValidationError, match="duplicate REPOSITORY"):
        InternalPortfolioReport(
            analysis=analysis,
            generation_records=records + (repository_record,),
        )


def test_internal_portfolio_report_rejects_duplicate_interview_record() -> None:
    analysis = make_portfolio_analysis()
    records = make_generation_records(analysis)
    interview_record = next(
        record for record in records if record.stage is InternalGenerationStage.INTERVIEW
    )

    with pytest.raises(ValidationError, match="duplicate INTERVIEW"):
        InternalPortfolioReport(
            analysis=analysis,
            generation_records=records + (interview_record,),
        )


def test_internal_portfolio_report_requires_record_for_interview_questions() -> None:
    analysis = make_portfolio_analysis()
    records = tuple(
        record
        for record in make_generation_records(analysis)
        if record.stage is not InternalGenerationStage.INTERVIEW
    )

    with pytest.raises(ValidationError, match="must match repositories with interview questions"):
        InternalPortfolioReport(analysis=analysis, generation_records=records)


def test_internal_portfolio_report_rejects_interview_record_without_questions() -> None:
    analysis = make_portfolio_analysis(interview_questions=())
    unexpected_record = InternalGenerationRecord(
        stage=InternalGenerationStage.INTERVIEW,
        repository_full_name=analysis.repository_analyses[0].repository_full_name,
        duration_ms=10,
        attempt_count=1,
    )

    with pytest.raises(ValidationError, match="must match repositories with interview questions"):
        InternalPortfolioReport(
            analysis=analysis,
            generation_records=make_generation_records(analysis) + (unexpected_record,),
        )


def test_internal_portfolio_report_rejects_unknown_fields() -> None:
    analysis = make_portfolio_analysis()

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        InternalPortfolioReport(
            analysis=analysis,
            generation_records=make_generation_records(analysis),
            contract_version="1.0",
        )


def test_internal_portfolio_report_is_frozen() -> None:
    analysis = make_portfolio_analysis()
    report = InternalPortfolioReport(
        analysis=analysis,
        generation_records=make_generation_records(analysis),
    )

    with pytest.raises(ValidationError, match="Instance is frozen"):
        report.generation_records = ()  # type: ignore[misc]


def test_internal_models_do_not_expose_scoring_or_http_contract_fields() -> None:
    forbidden_fields = {
        "contract_version",
        "schema_version",
        "analysis_id",
        "score",
        "weight",
        "contribution_rate",
        "employment_probability",
        "career_level_satisfied",
    }
    model_types = (
        InternalRepositoryInput,
        InternalPortfolioInput,
        InternalEvidence,
        InternalUserClaim,
        NormalizedRepositoryContext,
        RepositoryAnalysis,
        PortfolioAnalysis,
        InterviewQuestion,
        InterviewQuestionBatch,
        PortfolioStatement,
        InternalGenerationRecord,
        InternalPortfolioReport,
    )

    for model_type in model_types:
        assert forbidden_fields.isdisjoint(model_type.model_fields)
