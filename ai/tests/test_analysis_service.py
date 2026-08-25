from collections.abc import Sequence

import pytest

from app.core.exceptions import PortfolioAnalysisAssemblyError, ReportPolicyError
from app.criteria import CriteriaLoader, CriteriaSet
from app.domain import (
    AnalysisDepth,
    AnalysisItemType,
    EvidenceConfidence,
    GroundedAnalysisItem,
    InternalEvidence,
    InternalEvidenceType,
    InterviewQuestion,
    InterviewQuestionBatch,
    NormalizedRepositoryContext,
    PortfolioAnalysis,
    PortfolioStatement,
    PortfolioStatementBatch,
    PortfolioStatementType,
    PortfolioSynthesis,
    RepositoryAnalysis,
    RepresentativeProject,
    SnapshotHashAlgorithm,
)
from app.services import PortfolioAnalysisAssembler
from app.validators import PolicyViolation, PolicyViolationCode

_CRITERION_BY_DEPTH = {
    AnalysisDepth.P0: "TECH_STACK_EVIDENCE",
    AnalysisDepth.P1: "ACTIVITY_SCOPE",
    AnalysisDepth.P2: "SNIPPET_SCOPE",
}


class TrackingCriteriaLoader(CriteriaLoader):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, str]] = []

    def load(self, target_job: str, analysis_depth: str) -> CriteriaSet:
        self.calls.append((target_job, analysis_depth))
        return super().load(target_job, analysis_depth)


class MismatchedCriteriaLoader(CriteriaLoader):
    def load(self, target_job: str, analysis_depth: str) -> CriteriaSet:
        requested = AnalysisDepth(analysis_depth)
        wrong_depth = AnalysisDepth.P1 if requested is AnalysisDepth.P0 else AnalysisDepth.P0
        return super().load(target_job, wrong_depth.value)


class TrackingValidator:
    def __init__(self, label: str, events: list[str], fail_at: str | None = None) -> None:
        self._label = label
        self._events = events
        self._fail_at = fail_at

    def validate_references(self, value: object, *args: object) -> None:
        event = f"{self._label}:references:{_repository_name(value)}"
        self._record(event)

    def validate_content(self, value: object, *args: object) -> None:
        event = f"{self._label}:content:{_repository_name(value)}"
        self._record(event)

    def _record(self, event: str) -> None:
        self._events.append(event)
        if event != self._fail_at:
            return
        violation = PolicyViolation(
            code=PolicyViolationCode.UNKNOWN_EVIDENCE_REF,
            message="Injected policy failure.",
            field_path=event,
        )
        raise ReportPolicyError((violation,))


def _repository_name(value: object) -> str:
    if isinstance(value, RepositoryAnalysis):
        return value.repository_full_name
    if isinstance(value, InterviewQuestionBatch):
        return value.questions[0].repository_full_name
    if isinstance(value, PortfolioSynthesis):
        return "portfolio"
    if isinstance(value, PortfolioStatementBatch):
        return "statements"
    raise AssertionError(f"Unexpected validator value: {type(value)!r}")


def make_context(
    index: int,
    depth: AnalysisDepth = AnalysisDepth.P0,
) -> NormalizedRepositoryContext:
    repository = f"git-ddo/repository-{index}"
    p0_id = f"ev_{index * 10 + 1:03d}"
    p1_id = f"ev_{index * 10 + 2:03d}"
    evidence = [
        InternalEvidence(
            evidence_id=p0_id,
            repository_full_name=repository,
            evidence_type=InternalEvidenceType.GITHUB_STATIC,
            analysis_depth=AnalysisDepth.P0,
            key="TECHNOLOGY_DEPENDENCY",
            summary="Spring Boot dependency was observed.",
            source_paths=("build.gradle",),
            technology_names=("Spring Boot",),
        )
    ]
    completed_levels = [AnalysisDepth.P0]
    if depth in {AnalysisDepth.P1, AnalysisDepth.P2}:
        completed_levels.append(AnalysisDepth.P1)
        evidence.append(
            InternalEvidence(
                evidence_id=p1_id,
                repository_full_name=repository,
                evidence_type=InternalEvidenceType.GITHUB_ACTIVITY,
                analysis_depth=AnalysisDepth.P1,
                key="COMMIT_ACTIVITY",
                summary="A commit changed the service path.",
                source_paths=("src/main/java/OrderService.java",),
                commit_sha=f"commit-{index}",
            )
        )
    if depth is AnalysisDepth.P2:
        evidence.append(
            InternalEvidence(
                evidence_id=f"ev_{index * 10 + 3:03d}",
                repository_full_name=repository,
                evidence_type=InternalEvidenceType.CODE_EVIDENCE,
                analysis_depth=AnalysisDepth.P2,
                key="CODE_SNIPPET",
                summary="A bounded code snippet was collected.",
                path="src/main/java/OrderService.java",
                start_line=10,
                end_line=12,
                commit_sha=f"commit-{index}",
                source_evidence_refs=(p1_id,),
            )
        )
        completed_levels.append(AnalysisDepth.P2)

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
        technology_names=("Spring Boot",),
    )


def evidence_for_depth(context: NormalizedRepositoryContext) -> InternalEvidence:
    return next(
        evidence
        for evidence in context.evidence
        if evidence.analysis_depth is context.analysis_depth
    )


def make_analysis(context: NormalizedRepositoryContext) -> RepositoryAnalysis:
    evidence = context.evidence[0]
    return RepositoryAnalysis(
        repository_full_name=context.repository_full_name,
        summary=GroundedAnalysisItem(
            item_type=AnalysisItemType.INTERPRETATION,
            content="공개 설정에서 Spring Boot 의존성이 관찰되었습니다.",
            confidence=EvidenceConfidence.HIGH,
            evidence_refs=(evidence.evidence_id,),
            criterion_keys=("TECH_STACK_EVIDENCE",),
            technology_names=("Spring Boot",),
            file_paths=("build.gradle",),
        ),
    )


def make_synthesis(
    contexts: Sequence[NormalizedRepositoryContext],
    *,
    representative_name: str | None = None,
) -> PortfolioSynthesis:
    context_items = tuple(contexts)
    evidence_id = context_items[0].evidence[0].evidence_id
    return PortfolioSynthesis(
        overall_summary=GroundedAnalysisItem(
            item_type=AnalysisItemType.INTERPRETATION,
            content="공개 근거에서 포트폴리오 설명 요소가 관찰됩니다.",
            confidence=EvidenceConfidence.HIGH,
            evidence_refs=(evidence_id,),
            criterion_keys=("README_READINESS",),
        ),
        representative_projects=(
            RepresentativeProject(
                repository_full_name=(representative_name or context_items[0].repository_full_name),
                reason="공개 근거로 프로젝트 목적을 설명할 수 있습니다.",
                confidence=EvidenceConfidence.HIGH,
                evidence_refs=(evidence_id,),
            ),
        ),
        job_appeal=GroundedAnalysisItem(
            item_type=AnalysisItemType.JOB_APPEAL,
            content="공개 근거를 백엔드 직무 설명에 활용할 수 있습니다.",
            confidence=EvidenceConfidence.HIGH,
            evidence_refs=(evidence_id,),
            criterion_keys=("README_READINESS",),
        ),
        limitations=("공개 근거 범위만 분석했습니다.",),
    )


def make_interview_batch(
    context: NormalizedRepositoryContext,
    *labels: str,
) -> InterviewQuestionBatch:
    evidence = evidence_for_depth(context)
    paths = (
        ("build.gradle",)
        if context.analysis_depth is AnalysisDepth.P0
        else ("src/main/java/OrderService.java",)
    )
    technologies = ("Spring Boot",) if context.analysis_depth is AnalysisDepth.P0 else ()
    return InterviewQuestionBatch(
        questions=tuple(
            InterviewQuestion(
                repository_full_name=context.repository_full_name,
                question=f"{label} 근거를 어떻게 설명하시겠습니까?",
                intent="공개 근거를 프로젝트 설명과 연결하는 방식을 확인합니다.",
                answer_guide=("수집 범위와 확인된 사실을 구분해 설명합니다.",),
                evidence_refs=(evidence.evidence_id,),
                criterion_keys=(_CRITERION_BY_DEPTH[context.analysis_depth],),
                technology_names=technologies,
                file_paths=paths,
            )
            for label in labels
        )
    )


def make_statement_batch(
    context: NormalizedRepositoryContext,
    *statement_types: PortfolioStatementType,
) -> PortfolioStatementBatch:
    evidence = evidence_for_depth(context)
    paths = (
        ("build.gradle",)
        if context.analysis_depth is AnalysisDepth.P0
        else ("src/main/java/OrderService.java",)
    )
    technologies = ("Spring Boot",) if context.analysis_depth is AnalysisDepth.P0 else ()
    return PortfolioStatementBatch(
        statements=tuple(
            PortfolioStatement(
                statement_type=statement_type,
                content=f"{statement_type.value} 공개 근거를 프로젝트 설명에 활용했습니다.",
                evidence_refs=(evidence.evidence_id,),
                criterion_keys=(_CRITERION_BY_DEPTH[context.analysis_depth],),
                technology_names=technologies,
                file_paths=paths,
            )
            for statement_type in statement_types
        )
    )


def default_statement_batch(context: NormalizedRepositoryContext) -> PortfolioStatementBatch:
    return make_statement_batch(context, PortfolioStatementType.PORTFOLIO)


def assemble_valid(
    contexts: Sequence[NormalizedRepositoryContext],
    *,
    analyses: Sequence[RepositoryAnalysis] | None = None,
    interview_batches: Sequence[InterviewQuestionBatch] = (),
    statement_batch: PortfolioStatementBatch | None = None,
    assembler: PortfolioAnalysisAssembler | None = None,
) -> PortfolioAnalysis:
    context_items = tuple(contexts)
    return (assembler or PortfolioAnalysisAssembler()).assemble(
        context_items,
        analyses or tuple(make_analysis(context) for context in context_items),
        make_synthesis(context_items),
        interview_batches,
        statement_batch or default_statement_batch(context_items[0]),
    )


@pytest.mark.parametrize("repository_count", [1, 5])
def test_assembles_one_to_five_repositories(repository_count: int) -> None:
    contexts = tuple(make_context(index) for index in range(1, repository_count + 1))

    result = assemble_valid(contexts)

    assert isinstance(result, PortfolioAnalysis)
    assert tuple(item.repository_full_name for item in result.repository_analyses) == tuple(
        context.repository_full_name for context in contexts
    )


def test_assembles_mixed_depth_repositories() -> None:
    contexts = (
        make_context(1, AnalysisDepth.P0),
        make_context(2, AnalysisDepth.P1),
        make_context(3, AnalysisDepth.P2),
    )
    batches = tuple(
        make_interview_batch(context, context.analysis_depth.value) for context in contexts
    )

    result = assemble_valid(
        contexts,
        interview_batches=batches,
        statement_batch=default_statement_batch(contexts[-1]),
    )

    assert len(result.repository_analyses) == 3
    assert len(result.interview_questions) == 3


def test_orders_analyses_and_interviews_by_context_and_preserves_inner_order() -> None:
    contexts = (make_context(1), make_context(2), make_context(3))
    analyses = tuple(reversed(tuple(make_analysis(context) for context in contexts)))
    batches = (
        make_interview_batch(contexts[2], "third-a", "third-b"),
        make_interview_batch(contexts[0], "first-a", "first-b"),
    )

    result = assemble_valid(contexts, analyses=analyses, interview_batches=batches)

    assert [item.repository_full_name for item in result.repository_analyses] == [
        context.repository_full_name for context in contexts
    ]
    assert [question.question.split()[0] for question in result.interview_questions] == [
        "first-a",
        "first-b",
        "third-a",
        "third-b",
    ]


def test_preserves_statement_order_and_allows_no_interview_batches() -> None:
    context = make_context(1)
    batch = make_statement_batch(
        context,
        PortfolioStatementType.INTERVIEW,
        PortfolioStatementType.RESUME,
        PortfolioStatementType.PORTFOLIO,
    )

    result = assemble_valid((context,), statement_batch=batch)

    assert result.interview_questions == ()
    assert result.portfolio_statements == batch.statements


def test_does_not_mutate_inputs() -> None:
    contexts = (make_context(1), make_context(2))
    analyses = tuple(reversed(tuple(make_analysis(context) for context in contexts)))
    batches = (make_interview_batch(contexts[1], "second"),)
    statements = default_statement_batch(contexts[0])
    before = (
        tuple(context.model_dump() for context in contexts),
        tuple(analysis.model_dump() for analysis in analyses),
        tuple(batch.model_dump() for batch in batches),
        statements.model_dump(),
    )

    assemble_valid(
        contexts,
        analyses=analyses,
        interview_batches=batches,
        statement_batch=statements,
    )

    after = (
        tuple(context.model_dump() for context in contexts),
        tuple(analysis.model_dump() for analysis in analyses),
        tuple(batch.model_dump() for batch in batches),
        statements.model_dump(),
    )
    assert after == before


@pytest.mark.parametrize("count", [0, 6])
def test_rejects_invalid_context_count(count: int) -> None:
    contexts = tuple(make_context(index) for index in range(1, count + 1))
    fallback = make_context(9)

    with pytest.raises(PortfolioAnalysisAssemblyError, match="repository contexts"):
        PortfolioAnalysisAssembler().assemble(
            contexts,
            (make_analysis(fallback),),
            make_synthesis((fallback,)),
            (),
            default_statement_batch(fallback),
        )


@pytest.mark.parametrize("count", [0, 6])
def test_rejects_invalid_analysis_count(count: int) -> None:
    context = make_context(1)
    analyses = tuple(make_analysis(make_context(index)) for index in range(2, count + 2))

    with pytest.raises(PortfolioAnalysisAssemblyError, match="repository analyses"):
        PortfolioAnalysisAssembler().assemble(
            (context,),
            analyses,
            make_synthesis((context,)),
            (),
            default_statement_batch(context),
        )


def test_rejects_duplicate_context_repository() -> None:
    context = make_context(1)

    with pytest.raises(PortfolioAnalysisAssemblyError, match="duplicate repository"):
        PortfolioAnalysisAssembler().assemble(
            (context, context),
            (make_analysis(context),),
            make_synthesis((context,)),
            (),
            default_statement_batch(context),
        )


def test_rejects_duplicate_analysis_repository() -> None:
    context = make_context(1)
    analysis = make_analysis(context)

    with pytest.raises(PortfolioAnalysisAssemblyError, match="duplicate repository"):
        PortfolioAnalysisAssembler().assemble(
            (context,),
            (analysis, analysis),
            make_synthesis((context,)),
            (),
            default_statement_batch(context),
        )


def test_rejects_context_analysis_repository_mismatch() -> None:
    context = make_context(1)

    with pytest.raises(PortfolioAnalysisAssemblyError, match="same repositories"):
        PortfolioAnalysisAssembler().assemble(
            (context,),
            (make_analysis(make_context(2)),),
            make_synthesis((context,)),
            (),
            default_statement_batch(context),
        )


def test_rejects_unknown_representative_repository_before_validation() -> None:
    context = make_context(1)

    with pytest.raises(PortfolioAnalysisAssemblyError, match="representative"):
        PortfolioAnalysisAssembler().assemble(
            (context,),
            (make_analysis(context),),
            make_synthesis((context,), representative_name="git-ddo/unknown"),
            (),
            default_statement_batch(context),
        )


def test_rejects_unknown_interview_repository() -> None:
    context = make_context(1)
    unknown = make_context(2)

    with pytest.raises(PortfolioAnalysisAssemblyError, match="unknown repository"):
        PortfolioAnalysisAssembler().assemble(
            (context,),
            (make_analysis(context),),
            make_synthesis((context,)),
            (make_interview_batch(unknown, "unknown"),),
            default_statement_batch(context),
        )


def test_rejects_duplicate_interview_repository() -> None:
    context = make_context(1)

    with pytest.raises(PortfolioAnalysisAssemblyError, match="duplicate interview"):
        PortfolioAnalysisAssembler().assemble(
            (context,),
            (make_analysis(context),),
            make_synthesis((context,)),
            (
                make_interview_batch(context, "first"),
                make_interview_batch(context, "second"),
            ),
            default_statement_batch(context),
        )


def test_rejects_six_interview_batches() -> None:
    context = make_context(1)
    batches = tuple(make_interview_batch(context, f"batch-{index}") for index in range(6))

    with pytest.raises(PortfolioAnalysisAssemblyError, match="zero to five"):
        PortfolioAnalysisAssembler().assemble(
            (context,),
            (make_analysis(context),),
            make_synthesis((context,)),
            batches,
            default_statement_batch(context),
        )


def test_rejects_missing_statement_batch() -> None:
    context = make_context(1)

    with pytest.raises(PortfolioAnalysisAssemblyError, match="statement batch"):
        PortfolioAnalysisAssembler().assemble(
            (context,),
            (make_analysis(context),),
            make_synthesis((context,)),
            (),
            None,  # type: ignore[arg-type]
        )


def test_rejects_criteria_depth_mismatch() -> None:
    context = make_context(1)

    with pytest.raises(PortfolioAnalysisAssemblyError, match="criteria depth"):
        assemble_valid(
            (context,),
            assembler=PortfolioAnalysisAssembler(criteria_loader=MismatchedCriteriaLoader()),
        )


def test_loads_per_repository_and_maximum_depth_criteria() -> None:
    contexts = (
        make_context(1, AnalysisDepth.P0),
        make_context(2, AnalysisDepth.P1),
        make_context(3, AnalysisDepth.P2),
    )
    loader = TrackingCriteriaLoader()

    assemble_valid(
        contexts,
        statement_batch=default_statement_batch(contexts[-1]),
        assembler=PortfolioAnalysisAssembler(criteria_loader=loader),
    )

    assert loader.calls == [
        ("BACKEND", "P0"),
        ("BACKEND", "P1"),
        ("BACKEND", "P2"),
        ("BACKEND", "P2"),
    ]


def test_runs_validators_in_deterministic_order() -> None:
    contexts = (make_context(1), make_context(2))
    events: list[str] = []
    assembler = PortfolioAnalysisAssembler(
        repository_validator=TrackingValidator("repository", events),  # type: ignore[arg-type]
        portfolio_validator=TrackingValidator("portfolio", events),  # type: ignore[arg-type]
        interview_validator=TrackingValidator("interview", events),  # type: ignore[arg-type]
        statement_validator=TrackingValidator("statement", events),  # type: ignore[arg-type]
    )

    assemble_valid(
        contexts,
        interview_batches=(
            make_interview_batch(contexts[1], "second"),
            make_interview_batch(contexts[0], "first"),
        ),
        assembler=assembler,
    )

    assert events == [
        "repository:references:git-ddo/repository-1",
        "repository:content:git-ddo/repository-1",
        "repository:references:git-ddo/repository-2",
        "repository:content:git-ddo/repository-2",
        "portfolio:references:portfolio",
        "portfolio:content:portfolio",
        "interview:references:git-ddo/repository-1",
        "interview:content:git-ddo/repository-1",
        "interview:references:git-ddo/repository-2",
        "interview:content:git-ddo/repository-2",
        "statement:references:statements",
        "statement:content:statements",
    ]


@pytest.mark.parametrize(
    "fail_at",
    [
        "repository:references:git-ddo/repository-1",
        "repository:content:git-ddo/repository-1",
        "portfolio:references:portfolio",
        "portfolio:content:portfolio",
        "interview:references:git-ddo/repository-1",
        "interview:content:git-ddo/repository-1",
        "statement:references:statements",
        "statement:content:statements",
    ],
)
def test_propagates_policy_failure_and_stops_validation(fail_at: str) -> None:
    context = make_context(1)
    events: list[str] = []
    assembler = PortfolioAnalysisAssembler(
        repository_validator=TrackingValidator("repository", events, fail_at),  # type: ignore[arg-type]
        portfolio_validator=TrackingValidator("portfolio", events, fail_at),  # type: ignore[arg-type]
        interview_validator=TrackingValidator("interview", events, fail_at),  # type: ignore[arg-type]
        statement_validator=TrackingValidator("statement", events, fail_at),  # type: ignore[arg-type]
    )

    with pytest.raises(ReportPolicyError) as error:
        assemble_valid(
            (context,),
            interview_batches=(make_interview_batch(context, "first"),),
            assembler=assembler,
        )

    assert error.value.violations[0].field_path == fail_at
    assert events[-1] == fail_at


def test_real_statement_reference_policy_error_is_propagated() -> None:
    context = make_context(1)
    invalid_batch = PortfolioStatementBatch(
        statements=(
            PortfolioStatement(
                statement_type=PortfolioStatementType.PORTFOLIO,
                content="공개 근거를 프로젝트 설명에 활용했습니다.",
                evidence_refs=("ev_999",),
                criterion_keys=("TECH_STACK_EVIDENCE",),
            ),
        )
    )

    with pytest.raises(ReportPolicyError) as error:
        assemble_valid((context,), statement_batch=invalid_batch)

    assert error.value.violations[0].code is PolicyViolationCode.UNKNOWN_EVIDENCE_REF


def test_public_constructor_has_no_llm_provider_dependency() -> None:
    assembler = PortfolioAnalysisAssembler()

    assert not hasattr(assembler, "_provider")
