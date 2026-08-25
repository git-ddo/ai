from collections.abc import Sequence

import pytest

from app.core.exceptions import (
    LLMProviderError,
    LLMServiceError,
    LLMStructuredOutputError,
    PortfolioSynthesisError,
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
    PortfolioSynthesis,
    RepositoryAnalysis,
    RepresentativeProject,
    SnapshotHashAlgorithm,
)
from app.llm import GenerationMetadata, StructuredGeneration
from app.llm.provider import GenerationCall
from app.services import PortfolioSynthesisService


class SequencedProvider:
    def __init__(
        self,
        results: Sequence[StructuredGeneration[PortfolioSynthesis] | LLMProviderError],
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
        response_model: type[PortfolioSynthesis],
    ) -> StructuredGeneration[PortfolioSynthesis]:
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


class FailingCriteriaLoader(CriteriaLoader):
    def load(self, target_job: str, analysis_depth: str) -> CriteriaSet:
        raise CriteriaValidationError("criteria failed")


class MismatchedCriteriaLoader(CriteriaLoader):
    def load(self, target_job: str, analysis_depth: str) -> CriteriaSet:
        return super().load(target_job, AnalysisDepth.P0.value)


def make_context(
    index: int = 1,
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
        completed_levels.append(AnalysisDepth.P2)
        evidence.append(
            InternalEvidence(
                evidence_id=f"ev_{index * 10 + 3:03d}",
                repository_full_name=repository,
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
    overall_summary: GroundedAnalysisItem | None = None,
    representatives: tuple[RepresentativeProject, ...] | None = None,
    gaps: tuple[GroundedAnalysisItem, ...] = (),
) -> PortfolioSynthesis:
    context_items = tuple(contexts)
    first_evidence = context_items[0].evidence[0].evidence_id
    return PortfolioSynthesis(
        overall_summary=overall_summary
        or GroundedAnalysisItem(
            item_type=AnalysisItemType.INTERPRETATION,
            content="공개 근거에서 포트폴리오 설명 요소가 관찰됩니다.",
            confidence=EvidenceConfidence.HIGH,
            evidence_refs=(first_evidence,),
            criterion_keys=("README_READINESS",),
        ),
        representative_projects=representatives
        or tuple(
            RepresentativeProject(
                repository_full_name=context.repository_full_name,
                reason="공개 근거로 프로젝트 목적을 설명할 수 있습니다.",
                confidence=EvidenceConfidence.HIGH,
                evidence_refs=(context.evidence[0].evidence_id,),
            )
            for context in context_items
        ),
        gaps=gaps,
        job_appeal=GroundedAnalysisItem(
            item_type=AnalysisItemType.JOB_APPEAL,
            content="공개 Evidence를 직무 관련 설명에 활용할 수 있습니다.",
            confidence=EvidenceConfidence.HIGH,
            evidence_refs=tuple(context.evidence[0].evidence_id for context in context_items),
            criterion_keys=("README_READINESS",),
        ),
        limitations=("공개 근거 범위만 분석했습니다.",),
    )


def generation(
    value: PortfolioSynthesis,
    *,
    duration_ms: int = 10,
    attempt_count: int = 1,
) -> StructuredGeneration[PortfolioSynthesis]:
    return StructuredGeneration(
        value=value,
        metadata=GenerationMetadata(
            duration_ms=duration_ms,
            attempt_count=attempt_count,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("depth", list(AnalysisDepth))
async def test_synthesizes_portfolio_at_each_supported_depth(depth: AnalysisDepth) -> None:
    context = make_context(depth=depth)
    analysis = make_analysis(context)
    expected = make_synthesis((context,))
    expected_before = expected.model_dump()
    provider = SequencedProvider([generation(expected, duration_ms=12, attempt_count=2)])

    result = await PortfolioSynthesisService(provider).synthesize((context,), (analysis,))

    assert result.value == expected
    assert result.metadata == GenerationMetadata(duration_ms=12, attempt_count=2)
    assert provider.call_count == 1
    call = provider.calls[0]
    assert call.response_model is PortfolioSynthesis
    assert call.system_prompt != call.user_prompt
    assert "공개 GitHub" in call.system_prompt
    assert f"최대 {depth.value}" in call.user_prompt
    assert expected.model_dump() == expected_before


@pytest.mark.asyncio
@pytest.mark.parametrize("repository_count", [1, 5])
async def test_accepts_one_to_five_repositories(repository_count: int) -> None:
    contexts = tuple(make_context(index=index) for index in range(1, repository_count + 1))
    analyses = tuple(make_analysis(context) for context in contexts)
    expected = make_synthesis(contexts)
    provider = SequencedProvider([generation(expected)])

    result = await PortfolioSynthesisService(provider).synthesize(contexts, analyses)

    assert result.value == expected


@pytest.mark.asyncio
async def test_uses_deepest_cumulative_criteria_for_mixed_depths() -> None:
    contexts = (
        make_context(1, AnalysisDepth.P0),
        make_context(2, AnalysisDepth.P1),
        make_context(3, AnalysisDepth.P2),
    )
    analyses = tuple(make_analysis(context) for context in contexts)
    provider = SequencedProvider([generation(make_synthesis(contexts))])

    await PortfolioSynthesisService(provider).synthesize(contexts, analyses)

    prompt = provider.calls[0].user_prompt
    assert "README_READINESS" in prompt
    assert "ACTIVITY_SCOPE" in prompt
    assert "SNIPPET_SCOPE" in prompt
    assert "최대 P2" in prompt


@pytest.mark.asyncio
async def test_does_not_mutate_inputs() -> None:
    contexts = (make_context(),)
    analyses = (make_analysis(contexts[0]),)
    context_before = contexts[0].model_dump()
    analysis_before = analyses[0].model_dump()
    provider = SequencedProvider([generation(make_synthesis(contexts))])

    await PortfolioSynthesisService(provider).synthesize(contexts, analyses)

    assert contexts[0].model_dump() == context_before
    assert analyses[0].model_dump() == analysis_before


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
async def test_rejects_input_count_outside_one_to_five(
    contexts: tuple[NormalizedRepositoryContext, ...],
    analyses: tuple[RepositoryAnalysis, ...],
    message: str,
) -> None:
    provider = SequencedProvider([generation(make_synthesis((make_context(),)))])

    with pytest.raises(PortfolioSynthesisError, match=message):
        await PortfolioSynthesisService(provider).synthesize(contexts, analyses)

    assert provider.call_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("duplicate_input", ["contexts", "analyses"])
async def test_rejects_duplicate_repository_names(duplicate_input: str) -> None:
    context = make_context()
    analysis = make_analysis(context)
    contexts = (context, context) if duplicate_input == "contexts" else (context,)
    analyses = (analysis, analysis) if duplicate_input == "analyses" else (analysis,)
    provider = SequencedProvider([generation(make_synthesis((context,)))])

    with pytest.raises(PortfolioSynthesisError, match="duplicate repository"):
        await PortfolioSynthesisService(provider).synthesize(contexts, analyses)

    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_rejects_repository_set_mismatch() -> None:
    context = make_context(1)
    analysis = make_analysis(make_context(2))
    provider = SequencedProvider([generation(make_synthesis((context,)))])

    with pytest.raises(PortfolioSynthesisError, match="same repositories"):
        await PortfolioSynthesisService(provider).synthesize((context,), (analysis,))

    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_propagates_criteria_loader_failure_without_provider_call() -> None:
    context = make_context()
    provider = SequencedProvider([generation(make_synthesis((context,)))])

    with pytest.raises(CriteriaValidationError, match="criteria failed"):
        await PortfolioSynthesisService(
            provider,
            criteria_loader=FailingCriteriaLoader(),
        ).synthesize((context,), (make_analysis(context),))

    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_rejects_loaded_criteria_depth_mismatch_without_provider_call() -> None:
    context = make_context(depth=AnalysisDepth.P1)
    provider = SequencedProvider([generation(make_synthesis((context,)))])

    with pytest.raises(PortfolioSynthesisError, match="maximum depth"):
        await PortfolioSynthesisService(
            provider,
            criteria_loader=MismatchedCriteriaLoader(),
        ).synthesize((context,), (make_analysis(context),))

    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_regenerates_once_after_reference_policy_failure() -> None:
    context = make_context()
    invalid = make_synthesis(
        (context,),
        overall_summary=GroundedAnalysisItem(
            item_type=AnalysisItemType.INTERPRETATION,
            content="근거가 연결된 요약입니다.",
            confidence=EvidenceConfidence.HIGH,
            evidence_refs=("ev_999",),
            criterion_keys=("README_READINESS",),
        ),
    )
    corrected = make_synthesis((context,))
    provider = SequencedProvider([generation(invalid), generation(corrected)])

    result = await PortfolioSynthesisService(provider).synthesize(
        (context,),
        (make_analysis(context),),
    )

    assert result.value == corrected
    assert provider.call_count == 2
    assert "UNKNOWN_EVIDENCE_REF" in provider.calls[1].user_prompt


@pytest.mark.asyncio
async def test_regenerates_after_cross_repository_representative_reference() -> None:
    contexts = (make_context(1), make_context(2))
    analyses = tuple(make_analysis(context) for context in contexts)
    invalid = make_synthesis(
        contexts,
        representatives=(
            RepresentativeProject(
                repository_full_name=contexts[0].repository_full_name,
                reason="공개 근거를 대표 프로젝트 설명에 활용할 수 있습니다.",
                confidence=EvidenceConfidence.HIGH,
                evidence_refs=(contexts[1].evidence[0].evidence_id,),
            ),
        ),
    )
    provider = SequencedProvider([generation(invalid), generation(make_synthesis(contexts))])

    await PortfolioSynthesisService(provider).synthesize(contexts, analyses)

    assert "CROSS_REPOSITORY_REF" in provider.calls[1].user_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("invalid_item", "expected_code"),
    [
        (
            GroundedAnalysisItem(
                item_type=AnalysisItemType.INTERPRETATION,
                content="민감한 첫 응답 문장",
                confidence=EvidenceConfidence.HIGH,
                evidence_refs=("ev_011",),
                criterion_keys=("README_READINESS",),
                technology_names=("Redis",),
            ),
            "UNKNOWN_TECHNOLOGY",
        ),
        (
            GroundedAnalysisItem(
                item_type=AnalysisItemType.INTERPRETATION,
                content="프로젝트 전체 코드 품질이 우수합니다.",
                confidence=EvidenceConfidence.HIGH,
                evidence_refs=("ev_011",),
                criterion_keys=("README_READINESS",),
            ),
            "P0_SCOPE_VIOLATION",
        ),
    ],
)
async def test_regenerates_after_grounding_or_content_policy_failure(
    invalid_item: GroundedAnalysisItem,
    expected_code: str,
) -> None:
    context = make_context()
    invalid = make_synthesis((context,), overall_summary=invalid_item)
    corrected = make_synthesis((context,))
    provider = SequencedProvider(
        [
            generation(invalid, duration_ms=11, attempt_count=2),
            generation(corrected, duration_ms=19, attempt_count=3),
        ]
    )

    result = await PortfolioSynthesisService(provider).synthesize(
        (context,),
        (make_analysis(context),),
    )

    assert result.metadata == GenerationMetadata(duration_ms=30, attempt_count=5)
    correction_prompt = provider.calls[1].user_prompt
    assert expected_code in correction_prompt
    assert invalid_item.content not in correction_prompt
    assert "field_path" not in correction_prompt
    assert "Portfolio item uses technology outside referenced repositories." not in (
        correction_prompt
    )


@pytest.mark.asyncio
async def test_regenerates_after_missing_gap_lacks_derived_evidence() -> None:
    context = make_context()
    missing_gap = GroundedAnalysisItem(
        item_type=AnalysisItemType.INTERPRETATION,
        content="테스트가 누락되어 보완해야 합니다.",
        confidence=EvidenceConfidence.MEDIUM,
        evidence_refs=(context.evidence[0].evidence_id,),
        criterion_keys=("TEST_PRESENCE",),
    )
    provider = SequencedProvider(
        [
            generation(make_synthesis((context,), gaps=(missing_gap,))),
            generation(make_synthesis((context,))),
        ]
    )

    await PortfolioSynthesisService(provider).synthesize(
        (context,),
        (make_analysis(context),),
    )

    assert "MISSING_DERIVED_EVIDENCE" in provider.calls[1].user_prompt


@pytest.mark.asyncio
async def test_raises_second_policy_error_without_third_generation() -> None:
    context = make_context()
    invalid_item = GroundedAnalysisItem(
        item_type=AnalysisItemType.INTERPRETATION,
        content="근거가 연결된 요약입니다.",
        confidence=EvidenceConfidence.HIGH,
        evidence_refs=("ev_999",),
        criterion_keys=("README_READINESS",),
    )
    invalid = make_synthesis((context,), overall_summary=invalid_item)
    provider = SequencedProvider([generation(invalid), generation(invalid)])

    with pytest.raises(ReportPolicyError) as exc_info:
        await PortfolioSynthesisService(provider).synthesize(
            (context,),
            (make_analysis(context),),
        )

    assert provider.call_count == 2
    assert exc_info.value.violations[0].field_path == "overall_summary.evidence_refs[0]"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_error",
    [
        LLMServiceError("provider failed", retryable=True, attempt_count=2),
        LLMStructuredOutputError("structured output failed"),
    ],
)
async def test_propagates_initial_provider_error_without_policy_regeneration(
    provider_error: LLMProviderError,
) -> None:
    context = make_context()
    provider = SequencedProvider([provider_error])

    with pytest.raises(type(provider_error)):
        await PortfolioSynthesisService(provider).synthesize(
            (context,),
            (make_analysis(context),),
        )

    assert provider.call_count == 1


@pytest.mark.asyncio
async def test_propagates_provider_error_during_policy_regeneration() -> None:
    context = make_context()
    invalid_item = GroundedAnalysisItem(
        item_type=AnalysisItemType.INTERPRETATION,
        content="근거가 연결된 요약입니다.",
        confidence=EvidenceConfidence.HIGH,
        evidence_refs=("ev_999",),
        criterion_keys=("README_READINESS",),
    )
    invalid = make_synthesis((context,), overall_summary=invalid_item)
    provider_error = LLMServiceError("provider failed", retryable=True, attempt_count=2)
    provider = SequencedProvider([generation(invalid), provider_error])

    with pytest.raises(LLMServiceError, match="provider failed"):
        await PortfolioSynthesisService(provider).synthesize(
            (context,),
            (make_analysis(context),),
        )

    assert provider.call_count == 2
