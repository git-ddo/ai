import asyncio
from collections.abc import Sequence

import pytest
from pydantic import BaseModel, ValidationError

from app.core.exceptions import (
    InputValidationError,
    InputViolation,
    InputViolationCode,
    LLMTimeoutError,
    PortfolioReportDeadlineError,
)
from app.domain import (
    AnalysisDepth,
    AnalysisItemType,
    EvidenceConfidence,
    GroundedAnalysisItem,
    InternalEvidence,
    InternalEvidenceType,
    InternalGenerationStage,
    InternalPortfolioInput,
    InternalPortfolioReport,
    InternalRepositoryInput,
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
from app.llm import GenerationMetadata, LLMProvider, StructuredGeneration
from app.llm.provider import GenerationCall
from app.services import PortfolioAnalysisAssembler, PortfolioReportService
from app.services.normalization_service import NormalizationError, NormalizationService
from app.validators import AnalysisDepthValidator, EvidenceReferenceValidator

_CRITERION_BY_DEPTH = {
    AnalysisDepth.P0: "TECH_STACK_EVIDENCE",
    AnalysisDepth.P1: "ACTIVITY_SCOPE",
    AnalysisDepth.P2: "SNIPPET_SCOPE",
}


class SequencedProvider:
    def __init__(
        self,
        results: Sequence[BaseModel | BaseException],
        metadata: Sequence[GenerationMetadata] | None = None,
    ) -> None:
        self._results = list(results)
        self._metadata = list(metadata or ())
        self.calls: list[GenerationCall] = []
        self.closed = False

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
    ) -> StructuredGeneration[BaseModel]:
        self.calls.append(
            GenerationCall(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=response_model,
            )
        )
        if not self._results:
            raise AssertionError("Provider was called more times than expected")
        result = self._results.pop(0)
        if isinstance(result, BaseException):
            raise result
        if not isinstance(result, response_model):
            raise AssertionError("Provider result does not match requested response model")
        metadata = (
            self._metadata.pop(0)
            if self._metadata
            else GenerationMetadata(duration_ms=0, attempt_count=1)
        )
        return StructuredGeneration(value=result, metadata=metadata)

    async def aclose(self) -> None:
        self.closed = True


class StageControl:
    def __init__(
        self,
        *,
        fail_at: str | None = None,
        failure: BaseException | None = None,
        hang_at: str | None = None,
    ) -> None:
        self.events: list[str] = []
        self.fail_at = fail_at
        self.failure = failure or RuntimeError("injected pipeline failure")
        self.hang_at = hang_at

    def record(self, event: str) -> None:
        self.events.append(event)
        if event == self.fail_at:
            raise self.failure

    async def record_async(self, event: str) -> None:
        self.record(event)
        if event == self.hang_at:
            await asyncio.Event().wait()


class TrackingEvidenceValidator(EvidenceReferenceValidator):
    def __init__(self, control: StageControl) -> None:
        self._control = control

    def validate(self, portfolio: InternalPortfolioInput) -> None:
        self._control.record("evidence")
        super().validate(portfolio)


class TrackingDepthValidator(AnalysisDepthValidator):
    def __init__(self, control: StageControl) -> None:
        self._control = control

    def validate(self, portfolio: InternalPortfolioInput) -> None:
        self._control.record("depth")
        super().validate(portfolio)


class TrackingNormalizationService(NormalizationService):
    def __init__(self, control: StageControl) -> None:
        super().__init__()
        self._control = control

    def normalize(self, repository: InternalRepositoryInput) -> NormalizedRepositoryContext:
        self._control.record(f"normalize:{repository.repository_full_name}")
        return super().normalize(repository)


class FakeRepositoryService:
    def __init__(self, control: StageControl) -> None:
        self._control = control

    async def analyze(
        self,
        context: NormalizedRepositoryContext,
        portfolio_contexts: Sequence[NormalizedRepositoryContext],
    ) -> StructuredGeneration[RepositoryAnalysis]:
        await self._control.record_async(f"repository:{context.repository_full_name}")
        index = int(context.repository_id)
        return StructuredGeneration(
            value=make_analysis(context),
            metadata=GenerationMetadata(duration_ms=10 + index, attempt_count=index),
        )


class FakePortfolioService:
    def __init__(self, control: StageControl) -> None:
        self._control = control

    async def synthesize(
        self,
        contexts: Sequence[NormalizedRepositoryContext],
        repository_analyses: Sequence[RepositoryAnalysis],
    ) -> StructuredGeneration[PortfolioSynthesis]:
        await self._control.record_async("portfolio")
        return StructuredGeneration(
            value=make_synthesis(contexts),
            metadata=GenerationMetadata(duration_ms=20, attempt_count=2),
        )


class FakeInterviewService:
    def __init__(self, control: StageControl) -> None:
        self._control = control
        self.question_counts: list[int] = []

    async def generate(
        self,
        context: NormalizedRepositoryContext,
        repository_analysis: RepositoryAnalysis,
        portfolio_contexts: Sequence[NormalizedRepositoryContext],
        *,
        question_count: int = 5,
    ) -> StructuredGeneration[InterviewQuestionBatch]:
        await self._control.record_async(f"interview:{context.repository_full_name}")
        self.question_counts.append(question_count)
        index = int(context.repository_id)
        return StructuredGeneration(
            value=make_interview_batch(context, f"question-{index}-a", f"question-{index}-b"),
            metadata=GenerationMetadata(duration_ms=30 + index, attempt_count=index + 1),
        )


class FakeStatementService:
    def __init__(self, control: StageControl) -> None:
        self._control = control
        self.statement_counts: list[int] = []

    async def generate(
        self,
        contexts: Sequence[NormalizedRepositoryContext],
        repository_analyses: Sequence[RepositoryAnalysis],
        synthesis: PortfolioSynthesis,
        *,
        statement_count: int = 6,
    ) -> StructuredGeneration[PortfolioStatementBatch]:
        await self._control.record_async("statement")
        self.statement_counts.append(statement_count)
        return StructuredGeneration(
            value=make_statement_batch(
                tuple(contexts)[-1],
                PortfolioStatementType.INTERVIEW,
                PortfolioStatementType.RESUME,
            ),
            metadata=GenerationMetadata(duration_ms=40, attempt_count=4),
        )


class TrackingAssembler(PortfolioAnalysisAssembler):
    def __init__(self, control: StageControl) -> None:
        super().__init__()
        self._control = control

    def assemble(
        self,
        contexts: Sequence[NormalizedRepositoryContext],
        repository_analyses: Sequence[RepositoryAnalysis],
        synthesis: PortfolioSynthesis,
        interview_batches: Sequence[InterviewQuestionBatch],
        statement_batch: PortfolioStatementBatch,
    ) -> PortfolioAnalysis:
        self._control.record("assembler")
        return super().assemble(
            contexts,
            repository_analyses,
            synthesis,
            interview_batches,
            statement_batch,
        )


def make_repository_input(
    index: int,
    depth: AnalysisDepth = AnalysisDepth.P0,
) -> InternalRepositoryInput:
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
        completed_levels.append(AnalysisDepth.P2)
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

    return InternalRepositoryInput(
        repository_id=str(index),
        repository_full_name=repository,
        analysis_depth=depth,
        completed_evidence_levels=tuple(completed_levels),
        snapshot_hash_algorithm=SnapshotHashAlgorithm.SHA1,
        snapshot_sha=f"snapshot-{index}",
        evidence=tuple(evidence),
    )


def make_portfolio_input(
    depths: Sequence[AnalysisDepth] = (AnalysisDepth.P0,),
    *,
    requested_depth: AnalysisDepth | None = None,
) -> InternalPortfolioInput:
    depth_items = tuple(depths)
    return InternalPortfolioInput(
        requested_analysis_depth=requested_depth or max_depth(depth_items),
        repositories=tuple(
            make_repository_input(index, depth) for index, depth in enumerate(depth_items, start=1)
        ),
    )


def max_depth(depths: Sequence[AnalysisDepth]) -> AnalysisDepth:
    ranks = {AnalysisDepth.P0: 0, AnalysisDepth.P1: 1, AnalysisDepth.P2: 2}
    return max(depths, key=ranks.__getitem__)


def normalize(portfolio: InternalPortfolioInput) -> tuple[NormalizedRepositoryContext, ...]:
    service = NormalizationService()
    return tuple(service.normalize(repository) for repository in portfolio.repositories)


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
                repository_full_name=context_items[0].repository_full_name,
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


def evidence_for_depth(context: NormalizedRepositoryContext) -> InternalEvidence:
    return next(
        evidence
        for evidence in context.evidence
        if evidence.analysis_depth is context.analysis_depth
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


def make_default_service(
    portfolio: InternalPortfolioInput,
    *,
    control: StageControl | None = None,
    deadline_seconds: float = 270.0,
) -> tuple[PortfolioReportService, StageControl, SequencedProvider]:
    resolved_control = control or StageControl()
    provider = SequencedProvider((make_analysis(normalize(portfolio)[0]),))
    service = PortfolioReportService(
        provider,
        normalization_service=TrackingNormalizationService(resolved_control),
        evidence_validator=TrackingEvidenceValidator(resolved_control),
        depth_validator=TrackingDepthValidator(resolved_control),
        analysis_assembler=TrackingAssembler(resolved_control),
        repository_service=FakeRepositoryService(resolved_control),  # type: ignore[arg-type]
        portfolio_service=FakePortfolioService(resolved_control),  # type: ignore[arg-type]
        interview_service=FakeInterviewService(resolved_control),  # type: ignore[arg-type]
        statement_service=FakeStatementService(resolved_control),  # type: ignore[arg-type]
        deadline_seconds=deadline_seconds,
    )
    return service, resolved_control, provider


@pytest.mark.asyncio
async def test_runs_real_services_as_one_internal_smoke_pipeline() -> None:
    portfolio = make_portfolio_input()
    context = normalize(portfolio)[0]
    outputs: list[BaseModel] = [
        make_analysis(context),
        make_synthesis((context,)),
        make_interview_batch(context, "first", "second"),
        make_statement_batch(
            context,
            PortfolioStatementType.RESUME,
            PortfolioStatementType.PORTFOLIO,
        ),
    ]
    metadata = [
        GenerationMetadata(duration_ms=11, attempt_count=1),
        GenerationMetadata(duration_ms=22, attempt_count=2),
        GenerationMetadata(duration_ms=33, attempt_count=3),
        GenerationMetadata(duration_ms=44, attempt_count=4),
    ]
    provider = SequencedProvider(outputs, metadata)

    result = await PortfolioReportService(provider).generate(
        portfolio,
        question_count=2,
        statement_count=2,
    )

    assert isinstance(result, InternalPortfolioReport)
    assert isinstance(result.analysis, PortfolioAnalysis)
    assert [call.response_model for call in provider.calls] == [
        RepositoryAnalysis,
        PortfolioSynthesis,
        InterviewQuestionBatch,
        PortfolioStatementBatch,
    ]
    assert [record.stage for record in result.generation_records] == [
        InternalGenerationStage.REPOSITORY,
        InternalGenerationStage.PORTFOLIO,
        InternalGenerationStage.INTERVIEW,
        InternalGenerationStage.STATEMENT,
    ]
    assert [record.duration_ms for record in result.generation_records] == [11, 22, 33, 44]
    assert [record.attempt_count for record in result.generation_records] == [1, 2, 3, 4]
    assert provider.closed is False


@pytest.mark.asyncio
@pytest.mark.parametrize("repository_count", [1, 5])
async def test_handles_one_to_five_repositories(repository_count: int) -> None:
    portfolio = make_portfolio_input((AnalysisDepth.P0,) * repository_count)
    service, control, _provider = make_default_service(portfolio)

    result = await service.generate(portfolio)

    repository_names = [item.repository_full_name for item in portfolio.repositories]
    assert [item.repository_full_name for item in result.analysis.repository_analyses] == (
        repository_names
    )
    assert [
        question.repository_full_name for question in result.analysis.interview_questions[::2]
    ] == repository_names
    assert [event for event in control.events if event.startswith("repository:")] == [
        f"repository:{name}" for name in repository_names
    ]
    assert [event for event in control.events if event.startswith("interview:")] == [
        f"interview:{name}" for name in repository_names
    ]


@pytest.mark.asyncio
async def test_handles_mixed_p0_p1_p2_depths() -> None:
    portfolio = make_portfolio_input((AnalysisDepth.P0, AnalysisDepth.P1, AnalysisDepth.P2))
    service, _control, _provider = make_default_service(portfolio)

    result = await service.generate(portfolio)

    assert len(result.analysis.repository_analyses) == 3
    assert len(result.analysis.interview_questions) == 6


@pytest.mark.asyncio
async def test_executes_pipeline_in_deterministic_order() -> None:
    portfolio = make_portfolio_input((AnalysisDepth.P0, AnalysisDepth.P0))
    service, control, _provider = make_default_service(portfolio)

    await service.generate(portfolio, question_count=7, statement_count=9)

    assert control.events == [
        "evidence",
        "depth",
        "normalize:git-ddo/repository-1",
        "normalize:git-ddo/repository-2",
        "repository:git-ddo/repository-1",
        "repository:git-ddo/repository-2",
        "portfolio",
        "interview:git-ddo/repository-1",
        "interview:git-ddo/repository-2",
        "statement",
        "assembler",
    ]


@pytest.mark.asyncio
async def test_preserves_input_and_generated_item_order() -> None:
    portfolio = make_portfolio_input((AnalysisDepth.P0, AnalysisDepth.P1))
    before = portfolio.model_dump()
    service, _control, _provider = make_default_service(portfolio)

    result = await service.generate(portfolio)

    assert portfolio.model_dump() == before
    assert [item.repository_full_name for item in result.analysis.repository_analyses] == [
        "git-ddo/repository-1",
        "git-ddo/repository-2",
    ]
    assert [question.question.split()[0] for question in result.analysis.interview_questions] == [
        "question-1-a",
        "question-1-b",
        "question-2-a",
        "question-2-b",
    ]
    assert [statement.statement_type for statement in result.analysis.portfolio_statements] == [
        PortfolioStatementType.INTERVIEW,
        PortfolioStatementType.RESUME,
    ]


@pytest.mark.asyncio
async def test_generation_records_are_complete_ordered_and_grounded() -> None:
    portfolio = make_portfolio_input((AnalysisDepth.P0, AnalysisDepth.P0))
    service, _control, _provider = make_default_service(portfolio)

    result = await service.generate(portfolio)

    assert [record.stage for record in result.generation_records] == [
        InternalGenerationStage.REPOSITORY,
        InternalGenerationStage.REPOSITORY,
        InternalGenerationStage.PORTFOLIO,
        InternalGenerationStage.INTERVIEW,
        InternalGenerationStage.INTERVIEW,
        InternalGenerationStage.STATEMENT,
    ]
    assert [record.repository_full_name for record in result.generation_records] == [
        "git-ddo/repository-1",
        "git-ddo/repository-2",
        None,
        "git-ddo/repository-1",
        "git-ddo/repository-2",
        None,
    ]
    assert [record.duration_ms for record in result.generation_records] == [11, 12, 20, 31, 32, 40]
    assert [record.attempt_count for record in result.generation_records] == [1, 2, 2, 2, 3, 4]


@pytest.mark.asyncio
async def test_passes_requested_generation_counts_to_child_services() -> None:
    portfolio = make_portfolio_input((AnalysisDepth.P0, AnalysisDepth.P0))
    control = StageControl()
    interview_service = FakeInterviewService(control)
    statement_service = FakeStatementService(control)
    provider = SequencedProvider((make_analysis(normalize(portfolio)[0]),))
    service = PortfolioReportService(
        provider,
        normalization_service=TrackingNormalizationService(control),
        evidence_validator=TrackingEvidenceValidator(control),
        depth_validator=TrackingDepthValidator(control),
        analysis_assembler=TrackingAssembler(control),
        repository_service=FakeRepositoryService(control),  # type: ignore[arg-type]
        portfolio_service=FakePortfolioService(control),  # type: ignore[arg-type]
        interview_service=interview_service,  # type: ignore[arg-type]
        statement_service=statement_service,  # type: ignore[arg-type]
    )

    await service.generate(portfolio, question_count=8, statement_count=12)

    assert interview_service.question_counts == [8, 8]
    assert statement_service.statement_counts == [12]


@pytest.mark.asyncio
async def test_input_reference_failure_prevents_normalization_and_generation() -> None:
    portfolio = make_portfolio_input()
    violation = InputViolation(
        InputViolationCode.UNKNOWN_SOURCE_EVIDENCE_REF,
        "Unknown source evidence.",
    )
    failure = InputValidationError((violation,))
    control = StageControl(fail_at="evidence", failure=failure)
    service, _control, provider = make_default_service(portfolio, control=control)

    with pytest.raises(InputValidationError) as error:
        await service.generate(portfolio)

    assert error.value is failure
    assert control.events == ["evidence"]
    assert provider.calls == []


@pytest.mark.asyncio
async def test_depth_failure_prevents_normalization_and_generation() -> None:
    portfolio = make_portfolio_input(
        (AnalysisDepth.P1,),
        requested_depth=AnalysisDepth.P0,
    )
    service, control, provider = make_default_service(portfolio)

    with pytest.raises(InputValidationError):
        await service.generate(portfolio)

    assert control.events == ["evidence", "depth"]
    assert provider.calls == []


@pytest.mark.asyncio
async def test_normalization_failure_prevents_generation() -> None:
    portfolio = make_portfolio_input()
    failure = NormalizationError("normalization failed")
    control = StageControl(
        fail_at="normalize:git-ddo/repository-1",
        failure=failure,
    )
    service, _control, provider = make_default_service(portfolio, control=control)

    with pytest.raises(NormalizationError) as error:
        await service.generate(portfolio)

    assert error.value is failure
    assert control.events == [
        "evidence",
        "depth",
        "normalize:git-ddo/repository-1",
    ]
    assert provider.calls == []


@pytest.mark.parametrize("repository_count", [0, 6])
def test_portfolio_model_rejects_invalid_repository_count(repository_count: int) -> None:
    repositories = tuple(make_repository_input(index) for index in range(1, repository_count + 1))

    with pytest.raises(ValidationError):
        InternalPortfolioInput(
            requested_analysis_depth=AnalysisDepth.P0,
            repositories=repositories,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fail_at",
    [
        "repository:git-ddo/repository-1",
        "portfolio",
        "interview:git-ddo/repository-1",
        "statement",
        "assembler",
    ],
)
async def test_propagates_stage_failure_and_stops_pipeline(fail_at: str) -> None:
    portfolio = make_portfolio_input()
    failure = RuntimeError(f"failure at {fail_at}")
    control = StageControl(fail_at=fail_at, failure=failure)
    service, _control, _provider = make_default_service(portfolio, control=control)

    with pytest.raises(RuntimeError) as error:
        await service.generate(portfolio)

    assert error.value is failure
    assert control.events[-1] == fail_at


@pytest.mark.asyncio
async def test_interview_failure_stops_remaining_repositories_and_statement() -> None:
    portfolio = make_portfolio_input((AnalysisDepth.P0, AnalysisDepth.P0))
    control = StageControl(fail_at="interview:git-ddo/repository-1")
    service, _control, _provider = make_default_service(portfolio, control=control)

    with pytest.raises(RuntimeError):
        await service.generate(portfolio)

    assert "interview:git-ddo/repository-2" not in control.events
    assert "statement" not in control.events
    assert "assembler" not in control.events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hang_at",
    [
        "repository:git-ddo/repository-1",
        "portfolio",
        "interview:git-ddo/repository-1",
        "statement",
    ],
)
async def test_whole_pipeline_deadline_applies_to_each_generation_stage(
    hang_at: str,
) -> None:
    portfolio = make_portfolio_input()
    control = StageControl(hang_at=hang_at)
    service, _control, _provider = make_default_service(
        portfolio,
        control=control,
        deadline_seconds=0.005,
    )

    with pytest.raises(PortfolioReportDeadlineError):
        await service.generate(portfolio)

    assert control.events[-1] == hang_at
    assert "assembler" not in control.events


@pytest.mark.asyncio
async def test_successful_pipeline_completes_within_deadline() -> None:
    portfolio = make_portfolio_input()
    service, _control, _provider = make_default_service(portfolio, deadline_seconds=1.0)

    result = await service.generate(portfolio)

    assert isinstance(result, InternalPortfolioReport)


@pytest.mark.asyncio
async def test_provider_timeout_is_not_converted_to_whole_pipeline_timeout() -> None:
    portfolio = make_portfolio_input()
    failure = LLMTimeoutError(
        "provider timeout",
        retryable=True,
        attempt_count=3,
    )
    control = StageControl(
        fail_at="repository:git-ddo/repository-1",
        failure=failure,
    )
    service, _control, _provider = make_default_service(portfolio, control=control)

    with pytest.raises(LLMTimeoutError) as error:
        await service.generate(portfolio)

    assert error.value is failure


@pytest.mark.asyncio
async def test_external_cancellation_is_not_swallowed() -> None:
    portfolio = make_portfolio_input()
    cancellation = asyncio.CancelledError()
    control = StageControl(
        fail_at="repository:git-ddo/repository-1",
        failure=cancellation,
    )
    service, _control, _provider = make_default_service(portfolio, control=control)

    with pytest.raises(asyncio.CancelledError):
        await service.generate(portfolio)


@pytest.mark.parametrize(
    "deadline",
    [True, False, 0, -1, 300.1, float("inf"), float("nan"), "270"],
)
def test_rejects_invalid_deadline(deadline: object) -> None:
    provider = SequencedProvider((make_analysis(normalize(make_portfolio_input())[0]),))

    with pytest.raises(ValueError, match="deadline"):
        PortfolioReportService(provider, deadline_seconds=deadline)  # type: ignore[arg-type]


def test_accepts_deadline_upper_boundary() -> None:
    provider = SequencedProvider((make_analysis(normalize(make_portfolio_input())[0]),))

    service = PortfolioReportService(provider, deadline_seconds=300)

    assert isinstance(service, PortfolioReportService)


def test_report_service_depends_on_provider_protocol_not_gemini() -> None:
    provider: LLMProvider = SequencedProvider(
        (make_analysis(normalize(make_portfolio_input())[0]),)
    )

    service = PortfolioReportService(provider)

    assert isinstance(service, PortfolioReportService)
