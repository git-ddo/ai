from collections.abc import Sequence

import pytest

from app.core.exceptions import (
    LLMProviderError,
    LLMServiceError,
    LLMStructuredOutputError,
    PortfolioStatementGenerationError,
    ReportPolicyError,
)
from app.criteria import CriteriaLoader, CriteriaSet, CriteriaValidationError
from app.domain import (
    AnalysisDepth,
    AnalysisItemType,
    EvidenceConfidence,
    GroundedAnalysisItem,
    InternalEvidence,
    InternalEvidenceType,
    NormalizedRepositoryContext,
    PortfolioStatement,
    PortfolioStatementBatch,
    PortfolioStatementType,
    PortfolioSynthesis,
    RepositoryAnalysis,
    RepresentativeProject,
    SnapshotHashAlgorithm,
)
from app.llm import FakeLLMProvider, GenerationMetadata, StructuredGeneration
from app.llm.provider import GenerationCall
from app.services import PortfolioStatementService
from app.validators import PortfolioStatementPolicyValidator


class SequencedProvider:
    def __init__(
        self,
        results: Sequence[StructuredGeneration[PortfolioStatementBatch] | LLMProviderError],
    ) -> None:
        self._results = list(results)
        self.calls: list[GenerationCall] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[PortfolioStatementBatch],
    ) -> StructuredGeneration[PortfolioStatementBatch]:
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
        if isinstance(result, LLMProviderError):
            raise result
        if not isinstance(result.value, response_model):
            raise AssertionError("Test result does not match the requested response model")
        return result

    async def aclose(self) -> None:
        return None


class TrackingCriteriaLoader(CriteriaLoader):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, str]] = []

    def load(self, target_job: str, analysis_depth: str) -> CriteriaSet:
        self.calls.append((target_job, analysis_depth))
        return super().load(target_job, analysis_depth)


class MismatchedCriteriaLoader(CriteriaLoader):
    def load(self, target_job: str, analysis_depth: str) -> CriteriaSet:
        return super().load(target_job, AnalysisDepth.P0.value)


class FailingCriteriaLoader(CriteriaLoader):
    def load(self, target_job: str, analysis_depth: str) -> CriteriaSet:
        raise CriteriaValidationError("criteria failed")


class TrackingStatementValidator(PortfolioStatementPolicyValidator):
    def __init__(self) -> None:
        self.events: list[str] = []

    def validate_references(
        self,
        batch: PortfolioStatementBatch,
        contexts: Sequence[NormalizedRepositoryContext],
    ) -> None:
        self.events.append("references")
        super().validate_references(batch, contexts)

    def validate_content(
        self,
        batch: PortfolioStatementBatch,
        contexts: Sequence[NormalizedRepositoryContext],
        criteria: CriteriaSet,
    ) -> None:
        self.events.append("content")
        super().validate_content(batch, contexts, criteria)


def make_context(
    index: int = 1,
    depth: AnalysisDepth = AnalysisDepth.P0,
) -> NormalizedRepositoryContext:
    repository_name = f"git-ddo/repository-{index}"
    p0_id = f"ev_{index * 10 + 1:03d}"
    p1_id = f"ev_{index * 10 + 2:03d}"
    evidence = [
        InternalEvidence(
            evidence_id=p0_id,
            repository_full_name=repository_name,
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
                repository_full_name=repository_name,
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
                repository_full_name=repository_name,
                evidence_type=InternalEvidenceType.CODE_EVIDENCE,
                analysis_depth=AnalysisDepth.P2,
                key="CODE_SNIPPET",
                summary="if (request == null) throw new IllegalArgumentException();",
                path="src/main/java/OrderService.java",
                start_line=10,
                end_line=12,
                commit_sha=f"commit-{index}",
                source_evidence_refs=(p1_id,),
            )
        )

    return NormalizedRepositoryContext(
        repository_id=str(index),
        repository_full_name=repository_name,
        analysis_depth=depth,
        completed_evidence_levels=tuple(completed_levels),
        snapshot_hash_algorithm=(
            SnapshotHashAlgorithm.SHA1 if depth is not AnalysisDepth.P0 else None
        ),
        snapshot_sha=f"snapshot-{index}" if depth is not AnalysisDepth.P0 else None,
        evidence=tuple(evidence),
        technology_names=("Spring Boot",),
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
    first_context = context_items[0]
    first_evidence = first_context.evidence[0].evidence_id
    return PortfolioSynthesis(
        overall_summary=GroundedAnalysisItem(
            item_type=AnalysisItemType.INTERPRETATION,
            content="공개 근거에서 포트폴리오 설명 요소가 관찰됩니다.",
            confidence=EvidenceConfidence.HIGH,
            evidence_refs=(first_evidence,),
            criterion_keys=("README_READINESS",),
        ),
        representative_projects=(
            RepresentativeProject(
                repository_full_name=representative_name or first_context.repository_full_name,
                reason="공개 근거로 프로젝트 목적을 설명할 수 있습니다.",
                confidence=EvidenceConfidence.HIGH,
                evidence_refs=(first_evidence,),
            ),
        ),
        job_appeal=GroundedAnalysisItem(
            item_type=AnalysisItemType.JOB_APPEAL,
            content="공개 Evidence를 직무 관련 설명에 활용할 수 있습니다.",
            confidence=EvidenceConfidence.HIGH,
            evidence_refs=(first_evidence,),
            criterion_keys=("README_READINESS",),
        ),
        limitations=("공개 근거 범위만 분석했습니다.",),
    )


def make_batch(
    context: NormalizedRepositoryContext,
    *,
    content: str = "공개 근거에서 Spring Boot 설정을 확인하고 프로젝트 설명에 활용했습니다.",
    evidence_ref: str | None = None,
    technology_names: tuple[str, ...] = ("Spring Boot",),
    file_paths: tuple[str, ...] = ("build.gradle",),
) -> PortfolioStatementBatch:
    evidence_by_depth = {item.analysis_depth: item for item in context.evidence}
    evidence = evidence_by_depth[context.analysis_depth]
    criterion_by_depth = {
        AnalysisDepth.P0: "TECH_STACK_EVIDENCE",
        AnalysisDepth.P1: "ACTIVITY_SCOPE",
        AnalysisDepth.P2: "SNIPPET_SCOPE",
    }
    resolved_technologies = technology_names if context.analysis_depth is AnalysisDepth.P0 else ()
    resolved_paths = (
        file_paths
        if context.analysis_depth is AnalysisDepth.P0
        else ("src/main/java/OrderService.java",)
    )
    return PortfolioStatementBatch(
        statements=(
            PortfolioStatement(
                statement_type=PortfolioStatementType.PORTFOLIO,
                content=content,
                evidence_refs=(evidence_ref or evidence.evidence_id,),
                criterion_keys=(criterion_by_depth[context.analysis_depth],),
                technology_names=resolved_technologies,
                file_paths=resolved_paths,
            ),
        )
    )


def generation(
    value: PortfolioStatementBatch,
    *,
    duration_ms: int = 10,
    attempt_count: int = 1,
) -> StructuredGeneration[PortfolioStatementBatch]:
    return StructuredGeneration(
        value=value,
        metadata=GenerationMetadata(
            duration_ms=duration_ms,
            attempt_count=attempt_count,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("depth", list(AnalysisDepth))
async def test_generates_statements_at_each_supported_depth(depth: AnalysisDepth) -> None:
    context = make_context(depth=depth)
    analysis = make_analysis(context)
    synthesis = make_synthesis((context,))
    expected = make_batch(context)
    provider = FakeLLMProvider(expected)
    loader = TrackingCriteriaLoader()
    validator = TrackingStatementValidator()

    result = await PortfolioStatementService(
        provider,
        criteria_loader=loader,
        policy_validator=validator,
    ).generate((context,), (analysis,), synthesis, statement_count=9)

    assert result.value is expected
    assert result.metadata == GenerationMetadata(duration_ms=0, attempt_count=1)
    assert provider.call_count == 1
    assert loader.calls == [("BACKEND", depth.value)]
    assert validator.events == ["references", "content"]
    call = provider.calls[0]
    assert call.response_model is PortfolioStatementBatch
    assert "공개 GitHub" in call.system_prompt
    assert "최대 9개" in call.user_prompt
    assert f"최대 {depth.value}" in call.user_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("repository_count", [1, 5])
async def test_accepts_one_to_five_repositories(repository_count: int) -> None:
    contexts = tuple(make_context(index=index) for index in range(1, repository_count + 1))
    analyses = tuple(make_analysis(context) for context in contexts)
    expected = make_batch(contexts[0])
    provider = FakeLLMProvider(expected)

    result = await PortfolioStatementService(provider).generate(
        contexts,
        analyses,
        make_synthesis(contexts),
    )

    assert result.value is expected


@pytest.mark.asyncio
async def test_uses_deepest_criteria_for_mixed_repository_depths() -> None:
    contexts = (
        make_context(1, AnalysisDepth.P0),
        make_context(2, AnalysisDepth.P1),
        make_context(3, AnalysisDepth.P2),
    )
    analyses = tuple(make_analysis(context) for context in contexts)
    loader = TrackingCriteriaLoader()
    provider = FakeLLMProvider(make_batch(contexts[2]))

    await PortfolioStatementService(provider, criteria_loader=loader).generate(
        contexts,
        analyses,
        make_synthesis(contexts),
    )

    assert loader.calls == [("BACKEND", "P2")]
    prompt = provider.calls[0].user_prompt
    assert "README_READINESS" in prompt
    assert "ACTIVITY_SCOPE" in prompt
    assert "SNIPPET_SCOPE" in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("contexts", "analyses", "message"),
    [
        ((), (make_analysis(make_context()),), "one to five repository contexts"),
        (
            tuple(make_context(index=index) for index in range(1, 7)),
            (make_analysis(make_context()),),
            "one to five repository contexts",
        ),
        ((make_context(),), (), "one to five repository analyses"),
        (
            (make_context(),),
            tuple(make_analysis(make_context(index=index)) for index in range(1, 7)),
            "one to five repository analyses",
        ),
    ],
)
async def test_rejects_repository_count_outside_one_to_five(
    contexts: tuple[NormalizedRepositoryContext, ...],
    analyses: tuple[RepositoryAnalysis, ...],
    message: str,
) -> None:
    valid_context = make_context()
    provider = FakeLLMProvider(make_batch(valid_context))

    with pytest.raises(PortfolioStatementGenerationError, match=message):
        await PortfolioStatementService(provider).generate(
            contexts,
            analyses,
            make_synthesis((valid_context,)),
        )

    assert provider.call_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("duplicate_input", ["contexts", "analyses"])
async def test_rejects_duplicate_repository_names(duplicate_input: str) -> None:
    context = make_context()
    analysis = make_analysis(context)
    contexts = (context, context) if duplicate_input == "contexts" else (context,)
    analyses = (analysis, analysis) if duplicate_input == "analyses" else (analysis,)
    provider = FakeLLMProvider(make_batch(context))

    with pytest.raises(PortfolioStatementGenerationError, match="duplicate repository"):
        await PortfolioStatementService(provider).generate(
            contexts,
            analyses,
            make_synthesis((context,)),
        )

    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_rejects_repository_set_mismatch() -> None:
    context = make_context(1)
    provider = FakeLLMProvider(make_batch(context))

    with pytest.raises(PortfolioStatementGenerationError, match="same repositories"):
        await PortfolioStatementService(provider).generate(
            (context,),
            (make_analysis(make_context(2)),),
            make_synthesis((context,)),
        )

    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_rejects_unknown_representative_repository() -> None:
    context = make_context()
    provider = FakeLLMProvider(make_batch(context))

    with pytest.raises(PortfolioStatementGenerationError, match="unknown representative"):
        await PortfolioStatementService(provider).generate(
            (context,),
            (make_analysis(context),),
            make_synthesis((context,), representative_name="git-ddo/unknown"),
        )

    assert provider.call_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("statement_count", [0, 16, True, 1.0, "6"])
async def test_rejects_invalid_statement_count_before_provider_call(
    statement_count: object,
) -> None:
    context = make_context()
    provider = FakeLLMProvider(make_batch(context))

    with pytest.raises(PortfolioStatementGenerationError, match="one and fifteen"):
        await PortfolioStatementService(provider).generate(
            (context,),
            (make_analysis(context),),
            make_synthesis((context,)),
            statement_count=statement_count,  # type: ignore[arg-type]
        )

    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_rejects_loaded_criteria_depth_mismatch_before_provider_call() -> None:
    context = make_context(depth=AnalysisDepth.P1)
    provider = FakeLLMProvider(make_batch(context))

    with pytest.raises(PortfolioStatementGenerationError, match="maximum depth"):
        await PortfolioStatementService(
            provider,
            criteria_loader=MismatchedCriteriaLoader(),
        ).generate((context,), (make_analysis(context),), make_synthesis((context,)))

    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_propagates_criteria_loader_error_without_provider_call() -> None:
    context = make_context()
    provider = FakeLLMProvider(make_batch(context))

    with pytest.raises(CriteriaValidationError, match="criteria failed"):
        await PortfolioStatementService(
            provider,
            criteria_loader=FailingCriteriaLoader(),
        ).generate((context,), (make_analysis(context),), make_synthesis((context,)))

    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_regenerates_once_after_policy_failure_and_combines_metadata() -> None:
    context = make_context()
    sensitive_previous_content = "이전 문장의 민감한 원문"
    invalid = make_batch(
        context,
        content=sensitive_previous_content,
        technology_names=("Redis",),
    )
    corrected = make_batch(context)
    provider = SequencedProvider(
        [
            generation(invalid, duration_ms=11, attempt_count=2),
            generation(corrected, duration_ms=19, attempt_count=3),
        ]
    )

    result = await PortfolioStatementService(provider).generate(
        (context,),
        (make_analysis(context),),
        make_synthesis((context,)),
    )

    assert result.value is corrected
    assert result.metadata == GenerationMetadata(duration_ms=30, attempt_count=5)
    assert provider.call_count == 2
    correction_prompt = provider.calls[1].user_prompt
    assert "UNKNOWN_TECHNOLOGY" in correction_prompt
    assert sensitive_previous_content not in correction_prompt
    assert "field_path" not in correction_prompt
    assert "Portfolio item uses technology outside referenced repositories." not in (
        correction_prompt
    )


@pytest.mark.asyncio
async def test_correction_prompt_deduplicates_codes_in_first_seen_order() -> None:
    context = make_context()
    first = make_batch(context, technology_names=("Redis",)).statements[0]
    second = PortfolioStatement(
        statement_type=PortfolioStatementType.RESUME,
        content="공개 근거를 이력서 문장에 활용했습니다.",
        evidence_refs=(context.evidence[0].evidence_id,),
        criterion_keys=("TECH_STACK_EVIDENCE",),
        technology_names=("MongoDB",),
        file_paths=("unknown/path.py",),
    )
    invalid = PortfolioStatementBatch(statements=(first, second))
    provider = SequencedProvider([generation(invalid), generation(make_batch(context))])

    await PortfolioStatementService(provider).generate(
        (context,),
        (make_analysis(context),),
        make_synthesis((context,)),
    )

    correction_prompt = provider.calls[1].user_prompt
    assert correction_prompt.count("- UNKNOWN_TECHNOLOGY") == 1
    assert correction_prompt.index("- UNKNOWN_TECHNOLOGY") < correction_prompt.index(
        "- UNKNOWN_FILE_PATH"
    )


@pytest.mark.asyncio
async def test_second_policy_failure_is_propagated_without_third_generation() -> None:
    context = make_context()
    first = make_batch(context, evidence_ref="ev_999")
    second = make_batch(context, evidence_ref="ev_998")
    provider = SequencedProvider([generation(first), generation(second)])

    with pytest.raises(ReportPolicyError) as exc_info:
        await PortfolioStatementService(provider).generate(
            (context,),
            (make_analysis(context),),
            make_synthesis((context,)),
        )

    assert provider.call_count == 2
    assert exc_info.value.violations[0].code.value == "UNKNOWN_EVIDENCE_REF"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_error",
    [
        LLMServiceError(
            "service unavailable",
            retryable=True,
            attempt_count=2,
            status_code=503,
        ),
        LLMStructuredOutputError("structured output invalid"),
    ],
)
async def test_first_provider_error_is_propagated_without_policy_regeneration(
    provider_error: LLMProviderError,
) -> None:
    context = make_context()
    provider = SequencedProvider([provider_error])

    with pytest.raises(type(provider_error)):
        await PortfolioStatementService(provider).generate(
            (context,),
            (make_analysis(context),),
            make_synthesis((context,)),
        )

    assert provider.call_count == 1


@pytest.mark.asyncio
async def test_second_provider_error_is_propagated_without_extra_call() -> None:
    context = make_context()
    provider_error = LLMServiceError(
        "service unavailable",
        retryable=True,
        attempt_count=1,
        status_code=503,
    )
    provider = SequencedProvider(
        [
            generation(make_batch(context, evidence_ref="ev_999")),
            provider_error,
        ]
    )

    with pytest.raises(LLMServiceError):
        await PortfolioStatementService(provider).generate(
            (context,),
            (make_analysis(context),),
            make_synthesis((context,)),
        )

    assert provider.call_count == 2


@pytest.mark.asyncio
async def test_generation_does_not_mutate_or_reorder_inputs_or_batch() -> None:
    contexts = (make_context(2), make_context(1))
    analyses = tuple(make_analysis(context) for context in reversed(contexts))
    synthesis = make_synthesis(contexts)
    batch = make_batch(contexts[0])
    provider = FakeLLMProvider(batch)
    contexts_before = tuple(item.model_dump(mode="python") for item in contexts)
    analyses_before = tuple(item.model_dump(mode="python") for item in analyses)
    synthesis_before = synthesis.model_dump(mode="python")

    result = await PortfolioStatementService(provider).generate(
        contexts,
        analyses,
        synthesis,
    )

    assert tuple(item.model_dump(mode="python") for item in contexts) == contexts_before
    assert tuple(item.model_dump(mode="python") for item in analyses) == analyses_before
    assert synthesis.model_dump(mode="python") == synthesis_before
    assert result.value is batch
