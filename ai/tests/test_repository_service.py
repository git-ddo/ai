from collections.abc import Sequence

import pytest

from app.core.exceptions import (
    LLMProviderError,
    LLMServiceError,
    LLMStructuredOutputError,
    ReportPolicyError,
    RepositoryAnalysisError,
)
from app.criteria import CriteriaLoader, CriteriaSet, CriteriaValidationError
from app.domain import (
    AnalysisDepth,
    AnalysisItemType,
    EvidenceConfidence,
    EvidenceValueType,
    GroundedAnalysisItem,
    InternalEvidence,
    InternalEvidenceType,
    InternalUserClaim,
    NormalizedRepositoryContext,
    RepositoryAnalysis,
    SnapshotHashAlgorithm,
)
from app.llm import GenerationMetadata, StructuredGeneration
from app.llm.provider import GenerationCall
from app.prompts import PromptContextError
from app.services import RepositoryAnalysisService


class SequencedProvider:
    def __init__(
        self,
        results: Sequence[StructuredGeneration[RepositoryAnalysis] | LLMProviderError],
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
        response_model: type[RepositoryAnalysis],
    ) -> StructuredGeneration[RepositoryAnalysis]:
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
        return super().load(target_job, AnalysisDepth.P1.value)


def make_context(
    depth: AnalysisDepth = AnalysisDepth.P0,
    *,
    index: int = 1,
    evidence_summary: str = "Spring Boot dependency was observed.",
    claim_statement: str | None = None,
) -> NormalizedRepositoryContext:
    repository_name = f"git-ddo/repository-{index}"
    p0_id = f"ev_{index * 10 + 1:03d}"
    p1_id = f"ev_{index * 10 + 2:03d}"
    p2_id = f"ev_{index * 10 + 3:03d}"
    evidence = [
        InternalEvidence(
            evidence_id=p0_id,
            repository_full_name=repository_name,
            evidence_type=InternalEvidenceType.GITHUB_STATIC,
            analysis_depth=AnalysisDepth.P0,
            key="TECHNOLOGY_DEPENDENCY",
            summary=evidence_summary,
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
                commit_sha="abc123",
            )
        )
    if depth is AnalysisDepth.P2:
        completed_levels.append(AnalysisDepth.P2)
        evidence.append(
            InternalEvidence(
                evidence_id=p2_id,
                repository_full_name=repository_name,
                evidence_type=InternalEvidenceType.CODE_EVIDENCE,
                analysis_depth=AnalysisDepth.P2,
                key="CODE_SNIPPET",
                summary="if (request == null) throw new IllegalArgumentException();",
                value_type=EvidenceValueType.STRING,
                path="src/main/java/OrderService.java",
                start_line=10,
                end_line=12,
                commit_sha="abc123",
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
        snapshot_sha="abc123" if depth is not AnalysisDepth.P0 else None,
        evidence=tuple(evidence),
        user_claims=(
            (
                InternalUserClaim(
                    claim_id=f"claim_{index:03d}",
                    repository_full_name=repository_name,
                    statement=claim_statement,
                ),
            )
            if claim_statement is not None
            else ()
        ),
        technology_names=("Spring Boot",),
    )


def make_analysis(
    context: NormalizedRepositoryContext,
    *,
    content: str | None = None,
    evidence_ref: str | None = None,
    technology_names: tuple[str, ...] | None = None,
    observations: tuple[GroundedAnalysisItem, ...] = (),
) -> RepositoryAnalysis:
    evidence_by_depth = {item.analysis_depth: item for item in context.evidence}
    selected_evidence = evidence_by_depth[context.analysis_depth]
    criterion_by_depth = {
        AnalysisDepth.P0: "TECH_STACK_EVIDENCE",
        AnalysisDepth.P1: "ACTIVITY_SCOPE",
        AnalysisDepth.P2: "INPUT_VALIDATION_OBSERVATION",
    }
    content_by_depth = {
        AnalysisDepth.P0: "공개 설정에서 Spring Boot 의존성이 관찰되었습니다.",
        AnalysisDepth.P1: "전달된 커밋에서 Service 경로 변경 활동이 관찰되었습니다.",
        AnalysisDepth.P2: "제공된 snippet 범위에서 null 입력 검증이 관찰됩니다.",
    }
    technologies_by_depth = {
        AnalysisDepth.P0: ("Spring Boot",),
        AnalysisDepth.P1: (),
        AnalysisDepth.P2: (),
    }
    paths_by_depth = {
        AnalysisDepth.P0: ("build.gradle",),
        AnalysisDepth.P1: ("src/main/java/OrderService.java",),
        AnalysisDepth.P2: ("src/main/java/OrderService.java",),
    }
    return RepositoryAnalysis(
        repository_full_name=context.repository_full_name,
        summary=GroundedAnalysisItem(
            item_type=AnalysisItemType.INTERPRETATION,
            content=content or content_by_depth[context.analysis_depth],
            confidence=EvidenceConfidence.HIGH,
            evidence_refs=(evidence_ref or selected_evidence.evidence_id,),
            criterion_keys=(criterion_by_depth[context.analysis_depth],),
            technology_names=(
                technologies_by_depth[context.analysis_depth]
                if technology_names is None
                else technology_names
            ),
            file_paths=paths_by_depth[context.analysis_depth],
        ),
        observations=observations,
    )


def generation(
    value: RepositoryAnalysis,
    *,
    duration_ms: int = 10,
    attempt_count: int = 1,
) -> StructuredGeneration[RepositoryAnalysis]:
    return StructuredGeneration(
        value=value,
        metadata=GenerationMetadata(
            duration_ms=duration_ms,
            attempt_count=attempt_count,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("depth", list(AnalysisDepth))
async def test_analyzes_one_repository_at_each_supported_depth(depth: AnalysisDepth) -> None:
    context = make_context(depth)
    expected = make_analysis(context)
    provider = SequencedProvider([generation(expected, duration_ms=12, attempt_count=2)])

    result = await RepositoryAnalysisService(provider).analyze(context, (context,))

    assert result.value == expected
    assert result.metadata == GenerationMetadata(duration_ms=12, attempt_count=2)
    assert provider.call_count == 1
    call = provider.calls[0]
    assert call.response_model is RepositoryAnalysis
    assert call.system_prompt != call.user_prompt
    assert "공개 GitHub" in call.system_prompt
    assert f"BACKEND × ENTRY × {depth.value}" in call.user_prompt
    expected_criteria = {
        AnalysisDepth.P0: ("README_READINESS",),
        AnalysisDepth.P1: ("README_READINESS", "ACTIVITY_SCOPE"),
        AnalysisDepth.P2: ("README_READINESS", "ACTIVITY_SCOPE", "SNIPPET_SCOPE"),
    }
    assert all(key in call.user_prompt for key in expected_criteria[depth])


@pytest.mark.asyncio
@pytest.mark.parametrize("repository_count", [1, 5])
async def test_accepts_one_to_five_portfolio_contexts(repository_count: int) -> None:
    contexts = tuple(make_context(index=index) for index in range(1, repository_count + 1))
    target = contexts[0]
    provider = SequencedProvider([generation(make_analysis(target))])

    result = await RepositoryAnalysisService(provider).analyze(target, contexts)

    assert result.value.repository_full_name == target.repository_full_name


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "portfolio_contexts", [(), tuple(make_context(index=i) for i in range(1, 7))]
)
async def test_rejects_portfolio_context_count_outside_one_to_five(
    portfolio_contexts: tuple[NormalizedRepositoryContext, ...],
) -> None:
    context = make_context()
    provider = SequencedProvider([generation(make_analysis(context))])

    with pytest.raises(RepositoryAnalysisError, match="one to five"):
        await RepositoryAnalysisService(provider).analyze(context, portfolio_contexts)

    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_rejects_target_context_not_present() -> None:
    target = make_context(index=1)
    other = make_context(index=2)
    provider = SequencedProvider([generation(make_analysis(target))])

    with pytest.raises(RepositoryAnalysisError, match="not present exactly once"):
        await RepositoryAnalysisService(provider).analyze(target, (other,))

    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_rejects_duplicate_repository_context() -> None:
    context = make_context()
    provider = SequencedProvider([generation(make_analysis(context))])

    with pytest.raises(RepositoryAnalysisError, match="duplicate repository"):
        await RepositoryAnalysisService(provider).analyze(context, (context, context))

    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_regenerates_once_after_reference_policy_failure() -> None:
    context = make_context()
    invalid = make_analysis(context, evidence_ref="ev_999")
    corrected = make_analysis(context)
    provider = SequencedProvider([generation(invalid), generation(corrected)])

    result = await RepositoryAnalysisService(provider).analyze(context, (context,))

    assert result.value == corrected
    assert provider.call_count == 2
    assert "UNKNOWN_EVIDENCE_REF" in provider.calls[1].user_prompt


@pytest.mark.asyncio
async def test_regenerates_once_after_content_policy_failure_and_combines_metadata() -> None:
    context = make_context()
    sensitive_previous_content = "이전 응답의 민감한 원문"
    invalid = make_analysis(
        context,
        content=sensitive_previous_content,
        technology_names=("Redis",),
    )
    corrected = make_analysis(context)
    provider = SequencedProvider(
        [
            generation(invalid, duration_ms=11, attempt_count=2),
            generation(corrected, duration_ms=19, attempt_count=3),
        ]
    )

    result = await RepositoryAnalysisService(provider).analyze(context, (context,))

    assert result.value == corrected
    assert result.metadata == GenerationMetadata(duration_ms=30, attempt_count=5)
    correction_prompt = provider.calls[1].user_prompt
    assert "UNKNOWN_TECHNOLOGY" in correction_prompt
    assert sensitive_previous_content not in correction_prompt
    assert "Analysis item uses a technology outside the repository context." not in (
        correction_prompt
    )


@pytest.mark.asyncio
async def test_correction_prompt_deduplicates_violation_codes_in_first_seen_order() -> None:
    context = make_context()
    invalid_observation = GroundedAnalysisItem(
        item_type=AnalysisItemType.OBSERVATION,
        content="입력에 없는 기술을 언급합니다.",
        confidence=EvidenceConfidence.HIGH,
        evidence_refs=(context.evidence[0].evidence_id,),
        criterion_keys=("TECH_STACK_EVIDENCE",),
        technology_names=("MongoDB",),
    )
    invalid = make_analysis(
        context,
        technology_names=("Redis",),
        observations=(invalid_observation,),
    )
    provider = SequencedProvider([generation(invalid), generation(make_analysis(context))])

    await RepositoryAnalysisService(provider).analyze(context, (context,))

    task_prompt = provider.calls[1].user_prompt
    assert task_prompt.count("- UNKNOWN_TECHNOLOGY") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("second_failure", ["reference", "content"])
async def test_second_policy_failure_is_returned_without_third_generation(
    second_failure: str,
) -> None:
    context = make_context()
    first = make_analysis(context, evidence_ref="ev_999")
    second = (
        make_analysis(context, evidence_ref="ev_998")
        if second_failure == "reference"
        else make_analysis(context, technology_names=("Redis",))
    )
    provider = SequencedProvider([generation(first), generation(second)])

    with pytest.raises(ReportPolicyError):
        await RepositoryAnalysisService(provider).analyze(context, (context,))

    assert provider.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_error",
    [
        LLMServiceError("service unavailable", retryable=True, attempt_count=2, status_code=503),
        LLMStructuredOutputError("invalid structured output", attempt_count=1),
    ],
)
async def test_provider_errors_are_not_policy_regenerated(
    provider_error: LLMProviderError,
) -> None:
    context = make_context()
    provider = SequencedProvider([provider_error])

    with pytest.raises(type(provider_error)):
        await RepositoryAnalysisService(provider).analyze(context, (context,))

    assert provider.call_count == 1


@pytest.mark.asyncio
async def test_criteria_error_is_propagated_before_provider_call() -> None:
    context = make_context()
    provider = SequencedProvider([generation(make_analysis(context))])
    service = RepositoryAnalysisService(provider, criteria_loader=FailingCriteriaLoader())

    with pytest.raises(CriteriaValidationError):
        await service.analyze(context, (context,))

    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_rejects_loaded_criteria_depth_mismatch_before_provider_call() -> None:
    context = make_context(AnalysisDepth.P0)
    provider = SequencedProvider([generation(make_analysis(context))])
    service = RepositoryAnalysisService(provider, criteria_loader=MismatchedCriteriaLoader())

    with pytest.raises(RepositoryAnalysisError, match="criteria depth"):
        await service.analyze(context, (context,))

    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_prompt_error_is_propagated_before_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_context()
    provider = SequencedProvider([generation(make_analysis(context))])

    def fail_prompt(*_args: object, **_kwargs: object) -> str:
        raise PromptContextError("safe prompt error")

    monkeypatch.setattr(
        "app.services.repository_service.build_repository_prompt",
        fail_prompt,
    )

    with pytest.raises(PromptContextError, match="safe prompt error"):
        await RepositoryAnalysisService(provider).analyze(context, (context,))

    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_service_input_error_does_not_expose_untrusted_repository_content() -> None:
    sensitive_evidence = "repository secret evidence"
    sensitive_claim = "private user claim"
    context = make_context(
        evidence_summary=sensitive_evidence,
        claim_statement=sensitive_claim,
    )
    provider = SequencedProvider([generation(make_analysis(context))])

    with pytest.raises(RepositoryAnalysisError) as exc_info:
        await RepositoryAnalysisService(provider).analyze(context, ())

    assert sensitive_evidence not in str(exc_info.value)
    assert sensitive_claim not in str(exc_info.value)
