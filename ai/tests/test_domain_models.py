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
)


def make_evidence(
    *,
    evidence_id: str = "ev_001",
    repository_full_name: str = "git-ddo/backend",
    evidence_type: InternalEvidenceType | str = InternalEvidenceType.GITHUB_STATIC,
    technology_names: tuple[str, ...] = (),
) -> InternalEvidence:
    return InternalEvidence(
        evidence_id=evidence_id,
        repository_full_name=repository_full_name,
        evidence_type=evidence_type,
        key="README_INTRODUCTION_OBSERVED",
        summary="README에서 프로젝트 소개가 관찰되었습니다.",
        source_paths=("README.md",),
        technology_names=technology_names,
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


def make_portfolio_repository_input(index: int) -> InternalRepositoryInput:
    repository_full_name = f"git-ddo/repo-{index}"
    return make_repository_input(
        repository_id=index,
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


def test_creates_evidence_with_explicit_technology_names() -> None:
    evidence = make_evidence(technology_names=("Spring Boot", "PostgreSQL"))

    assert evidence.technology_names == ("Spring Boot", "PostgreSQL")


def test_rejects_blank_technology_name() -> None:
    with pytest.raises(ValidationError):
        make_evidence(technology_names=("   ",))


def test_creates_normalized_repository_context() -> None:
    evidence = make_evidence(technology_names=("Spring Boot",))
    context = NormalizedRepositoryContext(
        repository_id=1,
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
            repository_id=1,
            repository_full_name="git-ddo/backend",
            analysis_depth=AnalysisDepth.P0,
            evidence=(make_evidence(),),
            contract_version="1.0",
        )


def test_normalized_context_is_frozen() -> None:
    context = NormalizedRepositoryContext(
        repository_id=1,
        repository_full_name="git-ddo/backend",
        analysis_depth=AnalysisDepth.P0,
        evidence=(make_evidence(),),
    )

    with pytest.raises(ValidationError, match="Instance is frozen"):
        context.description = "변경할 수 없습니다."  # type: ignore[misc]


def test_normalized_context_rejects_empty_evidence() -> None:
    with pytest.raises(ValidationError):
        NormalizedRepositoryContext(
            repository_id=1,
            repository_full_name="git-ddo/backend",
            analysis_depth=AnalysisDepth.P0,
            evidence=(),
        )


def test_normalized_context_rejects_duplicate_evidence_ids() -> None:
    with pytest.raises(ValidationError, match="evidence IDs must be unique"):
        NormalizedRepositoryContext(
            repository_id=1,
            repository_full_name="git-ddo/backend",
            analysis_depth=AnalysisDepth.P0,
            evidence=(make_evidence(), make_evidence()),
        )


def test_normalized_context_rejects_duplicate_claim_ids() -> None:
    with pytest.raises(ValidationError, match="claim IDs must be unique"):
        NormalizedRepositoryContext(
            repository_id=1,
            repository_full_name="git-ddo/backend",
            analysis_depth=AnalysisDepth.P0,
            evidence=(make_evidence(),),
            user_claims=(make_claim(), make_claim()),
        )


def test_normalized_context_rejects_evidence_from_another_repository() -> None:
    with pytest.raises(ValidationError, match="evidence must belong"):
        NormalizedRepositoryContext(
            repository_id=1,
            repository_full_name="git-ddo/backend",
            analysis_depth=AnalysisDepth.P0,
            evidence=(make_evidence(repository_full_name="git-ddo/frontend"),),
        )


def test_normalized_context_rejects_claim_from_another_repository() -> None:
    with pytest.raises(ValidationError, match="user claims must belong"):
        NormalizedRepositoryContext(
            repository_id=1,
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
            repository_id=1,
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
            repository_id=2,
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
        repository_id=2,
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
        repository_id=2,
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
        3,
        1,
        2,
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
