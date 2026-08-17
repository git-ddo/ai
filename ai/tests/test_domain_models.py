from collections.abc import Callable

import pytest
from pydantic import ValidationError

from app.domain import (
    AnalysisDepth,
    AnalysisItemType,
    EvidenceConfidence,
    GroundedAnalysisItem,
    InternalEvidence,
    InternalEvidenceType,
    InternalRepositoryInput,
    InternalUserClaim,
    InterviewQuestion,
    PortfolioAnalysis,
    PortfolioStatement,
    PortfolioStatementType,
    RecommendationPriority,
    RepositoryAnalysis,
    RepresentativeProject,
)


def make_evidence(
    *,
    evidence_id: str = "ev_001",
    repository_full_name: str = "git-ddo/backend",
    evidence_type: InternalEvidenceType | str = InternalEvidenceType.GITHUB_STATIC,
) -> InternalEvidence:
    return InternalEvidence(
        evidence_id=evidence_id,
        repository_full_name=repository_full_name,
        evidence_type=evidence_type,
        key="README_INTRODUCTION_OBSERVED",
        summary="README에서 프로젝트 소개가 관찰되었습니다.",
        source_paths=("README.md",),
    )


def make_claim(
    *,
    claim_id: str = "claim_001",
    repository_full_name: str = "git-ddo/backend",
) -> InternalUserClaim:
    return InternalUserClaim(
        claim_id=claim_id,
        repository_full_name=repository_full_name,
        statement="사용자는 인증 API를 담당했다고 진술했습니다.",
    )


def make_repository_input(
    *,
    repository_id: int = 1,
    repository_full_name: str = "git-ddo/backend",
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
        analysis_depth=AnalysisDepth.P0,
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


def make_portfolio_analysis(
    *,
    repository_analyses: tuple[RepositoryAnalysis, ...] | None = None,
) -> PortfolioAnalysis:
    analyses = (
        repository_analyses if repository_analyses is not None else (make_repository_analysis(),)
    )
    representative_name = analyses[0].repository_full_name if analyses else "git-ddo/backend"
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
        interview_questions=(
            InterviewQuestion(
                repository_full_name=representative_name,
                question="README에 표시된 Spring Boot를 선택한 이유는 무엇인가요?",
                intent="공개 기술 근거를 자신의 설명과 연결하는지 확인합니다.",
                answer_guide=("기술 선택 배경을 사용자 경험과 구분해 설명합니다.",),
                follow_up_questions=(),
                evidence_refs=("ev_001",),
                claim_refs=("claim_001",),
            ),
        ),
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


def test_creates_valid_p0_repository_input() -> None:
    repository = make_repository_input()

    assert repository.analysis_depth is AnalysisDepth.P0
    assert repository.evidence[0].evidence_type is InternalEvidenceType.GITHUB_STATIC
    assert repository.user_claims[0].claim_id == "claim_001"


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


def test_rejects_analysis_depth_other_than_p0() -> None:
    with pytest.raises(ValidationError):
        InternalRepositoryInput(
            repository_id=1,
            repository_full_name="git-ddo/backend",
            analysis_depth="P1",
            evidence=(make_evidence(),),
        )


def test_rejects_evidence_type_not_allowed_in_p0() -> None:
    with pytest.raises(ValidationError):
        make_evidence(evidence_type="GITHUB_ACTIVITY")


def test_rejects_empty_evidence_collection() -> None:
    with pytest.raises(ValidationError):
        InternalRepositoryInput(
            repository_id=1,
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
        InternalEvidence,
        InternalUserClaim,
        RepositoryAnalysis,
        PortfolioAnalysis,
        InterviewQuestion,
        PortfolioStatement,
    )

    for model_type in model_types:
        assert forbidden_fields.isdisjoint(model_type.model_fields)
