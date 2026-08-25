from collections.abc import Sequence

import pytest

from app.core.exceptions import (
    InterviewQuestionGenerationError,
    LLMProviderError,
    LLMServiceError,
    ReportPolicyError,
)
from app.criteria import CriteriaLoader, CriteriaSet
from app.domain import (
    AnalysisDepth,
    AnalysisItemType,
    EvidenceConfidence,
    EvidenceValueType,
    GroundedAnalysisItem,
    InternalEvidence,
    InternalEvidenceType,
    InterviewQuestion,
    InterviewQuestionBatch,
    NormalizedRepositoryContext,
    RepositoryAnalysis,
    SnapshotHashAlgorithm,
)
from app.llm import FakeLLMProvider, GenerationMetadata, StructuredGeneration
from app.llm.provider import GenerationCall
from app.services import InterviewQuestionService
from app.validators import InterviewQuestionPolicyValidator


class SequencedProvider:
    def __init__(
        self,
        results: Sequence[StructuredGeneration[InterviewQuestionBatch] | LLMProviderError],
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
        response_model: type[InterviewQuestionBatch],
    ) -> StructuredGeneration[InterviewQuestionBatch]:
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
        return super().load(target_job, AnalysisDepth.P1.value)


class TrackingInterviewValidator(InterviewQuestionPolicyValidator):
    def __init__(self) -> None:
        self.reference_calls = 0
        self.content_calls = 0
        self.events: list[str] = []

    def validate_references(
        self,
        batch: InterviewQuestionBatch,
        expected_context: NormalizedRepositoryContext,
        portfolio_contexts: Sequence[NormalizedRepositoryContext],
    ) -> None:
        self.reference_calls += 1
        self.events.append("references")
        super().validate_references(batch, expected_context, portfolio_contexts)

    def validate_content(
        self,
        batch: InterviewQuestionBatch,
        context: NormalizedRepositoryContext,
        criteria: CriteriaSet,
    ) -> None:
        self.content_calls += 1
        self.events.append("content")
        super().validate_content(batch, context, criteria)


def make_context(
    depth: AnalysisDepth = AnalysisDepth.P0,
    *,
    index: int = 1,
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
        technology_names=("Spring Boot",),
    )


def make_analysis(
    context: NormalizedRepositoryContext,
    *,
    repository_full_name: str | None = None,
) -> RepositoryAnalysis:
    evidence_by_depth = {item.analysis_depth: item for item in context.evidence}
    evidence = evidence_by_depth[context.analysis_depth]
    criterion_by_depth = {
        AnalysisDepth.P0: "TECH_STACK_EVIDENCE",
        AnalysisDepth.P1: "ACTIVITY_SCOPE",
        AnalysisDepth.P2: "INPUT_VALIDATION_OBSERVATION",
    }
    return RepositoryAnalysis(
        repository_full_name=repository_full_name or context.repository_full_name,
        summary=GroundedAnalysisItem(
            item_type=AnalysisItemType.INTERPRETATION,
            content="공개 근거에서 프로젝트를 설명할 수 있습니다.",
            confidence=EvidenceConfidence.HIGH,
            evidence_refs=(evidence.evidence_id,),
            criterion_keys=(criterion_by_depth[context.analysis_depth],),
        ),
    )


def make_batch(
    context: NormalizedRepositoryContext,
    *,
    question: str = "프로젝트에서 관찰된 기술 선택 배경을 설명해 주세요.",
    evidence_ref: str | None = None,
    technology_names: tuple[str, ...] | None = None,
) -> InterviewQuestionBatch:
    evidence_by_depth = {item.analysis_depth: item for item in context.evidence}
    evidence = evidence_by_depth[context.analysis_depth]
    criterion_by_depth = {
        AnalysisDepth.P0: "TECH_STACK_EVIDENCE",
        AnalysisDepth.P1: "ACTIVITY_SCOPE",
        AnalysisDepth.P2: "INPUT_VALIDATION_OBSERVATION",
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
    return InterviewQuestionBatch(
        questions=(
            InterviewQuestion(
                repository_full_name=context.repository_full_name,
                question=question,
                intent="프로젝트 근거에 대한 설명을 확인합니다.",
                answer_guide=("관찰된 범위 안에서 선택 배경을 설명합니다.",),
                evidence_refs=(evidence_ref or evidence.evidence_id,),
                criterion_keys=(criterion_by_depth[context.analysis_depth],),
                technology_names=(
                    technologies_by_depth[context.analysis_depth]
                    if technology_names is None
                    else technology_names
                ),
                file_paths=paths_by_depth[context.analysis_depth],
            ),
        )
    )


def generation(
    value: InterviewQuestionBatch,
    *,
    duration_ms: int = 10,
    attempt_count: int = 1,
) -> StructuredGeneration[InterviewQuestionBatch]:
    return StructuredGeneration(
        value=value,
        metadata=GenerationMetadata(
            duration_ms=duration_ms,
            attempt_count=attempt_count,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("depth", list(AnalysisDepth))
async def test_generates_interview_questions_at_each_supported_depth(
    depth: AnalysisDepth,
) -> None:
    context = make_context(depth)
    expected = make_batch(context)
    provider = FakeLLMProvider(expected)
    loader = TrackingCriteriaLoader()
    validator = TrackingInterviewValidator()

    result = await InterviewQuestionService(
        provider,
        criteria_loader=loader,
        policy_validator=validator,
    ).generate(context, make_analysis(context), (context,), question_count=7)

    assert result.value == expected
    assert result.metadata == GenerationMetadata(duration_ms=0, attempt_count=1)
    assert provider.call_count == 1
    assert loader.calls == [("BACKEND", depth.value)]
    assert validator.reference_calls == 1
    assert validator.content_calls == 1
    assert validator.events == ["references", "content"]
    call = provider.calls[0]
    assert call.response_model is InterviewQuestionBatch
    assert "공개 GitHub" in call.system_prompt
    assert "최대 7개" in call.user_prompt
    assert f"BACKEND × ENTRY × {depth.value}" in call.user_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("repository_count", [1, 5])
async def test_accepts_one_to_five_portfolio_contexts(repository_count: int) -> None:
    contexts = tuple(make_context(index=index) for index in range(1, repository_count + 1))
    target = contexts[0]
    provider = FakeLLMProvider(make_batch(target))

    result = await InterviewQuestionService(provider).generate(
        target,
        make_analysis(target),
        contexts,
    )

    assert result.value == make_batch(target)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "portfolio_contexts",
    [(), tuple(make_context(index=index) for index in range(1, 7))],
)
async def test_rejects_portfolio_context_count_outside_one_to_five(
    portfolio_contexts: tuple[NormalizedRepositoryContext, ...],
) -> None:
    context = make_context()
    provider = FakeLLMProvider(make_batch(context))

    with pytest.raises(InterviewQuestionGenerationError, match="one to five"):
        await InterviewQuestionService(provider).generate(
            context,
            make_analysis(context),
            portfolio_contexts,
        )

    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_rejects_duplicate_repository_context_before_provider_call() -> None:
    context = make_context()
    provider = FakeLLMProvider(make_batch(context))

    with pytest.raises(InterviewQuestionGenerationError, match="duplicate repository"):
        await InterviewQuestionService(provider).generate(
            context,
            make_analysis(context),
            (context, context),
        )

    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_rejects_missing_or_nonidentical_target_context_before_provider_call() -> None:
    context = make_context()
    same_name_different_context = context.model_copy(update={"description": "different"})
    provider = FakeLLMProvider(make_batch(context))

    with pytest.raises(InterviewQuestionGenerationError, match="not present exactly once"):
        await InterviewQuestionService(provider).generate(
            context,
            make_analysis(context),
            (same_name_different_context,),
        )

    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_rejects_repository_analysis_mismatch_before_provider_call() -> None:
    context = make_context()
    provider = FakeLLMProvider(make_batch(context))

    with pytest.raises(InterviewQuestionGenerationError, match="does not match"):
        await InterviewQuestionService(provider).generate(
            context,
            make_analysis(context, repository_full_name="git-ddo/other"),
            (context,),
        )

    assert provider.call_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("question_count", [0, 11, True, 1.0, "5"])
async def test_rejects_invalid_question_count_before_provider_call(
    question_count: object,
) -> None:
    context = make_context()
    provider = FakeLLMProvider(make_batch(context))

    with pytest.raises(InterviewQuestionGenerationError, match="between one and ten"):
        await InterviewQuestionService(provider).generate(
            context,
            make_analysis(context),
            (context,),
            question_count=question_count,  # type: ignore[arg-type]
        )

    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_rejects_loaded_criteria_depth_mismatch_before_provider_call() -> None:
    context = make_context(AnalysisDepth.P0)
    provider = FakeLLMProvider(make_batch(context))
    service = InterviewQuestionService(
        provider,
        criteria_loader=MismatchedCriteriaLoader(),
    )

    with pytest.raises(InterviewQuestionGenerationError, match="criteria depth"):
        await service.generate(context, make_analysis(context), (context,))

    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_regenerates_once_after_policy_failure_and_combines_metadata() -> None:
    context = make_context()
    sensitive_previous_content = "이전 질문의 민감한 원문"
    invalid = make_batch(
        context,
        question=sensitive_previous_content,
        technology_names=("Redis",),
    )
    corrected = make_batch(context)
    provider = SequencedProvider(
        [
            generation(invalid, duration_ms=11, attempt_count=2),
            generation(corrected, duration_ms=19, attempt_count=3),
        ]
    )

    result = await InterviewQuestionService(provider).generate(
        context,
        make_analysis(context),
        (context,),
    )

    assert result.value == corrected
    assert result.metadata == GenerationMetadata(duration_ms=30, attempt_count=5)
    assert provider.call_count == 2
    correction_prompt = provider.calls[1].user_prompt
    assert "UNKNOWN_TECHNOLOGY" in correction_prompt
    assert sensitive_previous_content not in correction_prompt
    assert "Generated text" not in correction_prompt
    assert "field_path" not in correction_prompt


@pytest.mark.asyncio
async def test_correction_prompt_deduplicates_policy_codes_in_first_seen_order() -> None:
    context = make_context()
    invalid = InterviewQuestionBatch(
        questions=(
            make_batch(context, question="첫 번째 질문", technology_names=("Redis",)).questions[0],
            make_batch(context, question="두 번째 질문", technology_names=("MongoDB",)).questions[
                0
            ],
        )
    )
    provider = SequencedProvider([generation(invalid), generation(make_batch(context))])

    await InterviewQuestionService(provider).generate(
        context,
        make_analysis(context),
        (context,),
    )

    correction_prompt = provider.calls[1].user_prompt
    assert correction_prompt.count("- UNKNOWN_TECHNOLOGY") == 1


@pytest.mark.asyncio
async def test_correction_prompt_preserves_first_seen_policy_code_order() -> None:
    context = make_context()
    question = make_batch(context, technology_names=("Redis",)).questions[0]
    invalid = InterviewQuestionBatch(
        questions=(question.model_copy(update={"file_paths": ("unknown/path.py",)}),)
    )
    provider = SequencedProvider([generation(invalid), generation(make_batch(context))])

    await InterviewQuestionService(provider).generate(
        context,
        make_analysis(context),
        (context,),
    )

    correction_prompt = provider.calls[1].user_prompt
    assert correction_prompt.index("- UNKNOWN_TECHNOLOGY") < correction_prompt.index(
        "- UNKNOWN_FILE_PATH"
    )


@pytest.mark.asyncio
async def test_second_policy_failure_is_returned_without_third_generation() -> None:
    context = make_context()
    first = make_batch(context, evidence_ref="ev_999")
    second = make_batch(context, evidence_ref="ev_998")
    provider = SequencedProvider([generation(first), generation(second)])

    with pytest.raises(ReportPolicyError) as exc_info:
        await InterviewQuestionService(provider).generate(
            context,
            make_analysis(context),
            (context,),
        )

    assert provider.call_count == 2
    assert exc_info.value.violations[0].code.value == "UNKNOWN_EVIDENCE_REF"


@pytest.mark.asyncio
async def test_first_provider_error_is_not_policy_regenerated() -> None:
    context = make_context()
    provider_error = LLMServiceError(
        "service unavailable",
        retryable=True,
        attempt_count=2,
        status_code=503,
    )
    provider = SequencedProvider([provider_error])

    with pytest.raises(LLMServiceError):
        await InterviewQuestionService(provider).generate(
            context,
            make_analysis(context),
            (context,),
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
        await InterviewQuestionService(provider).generate(
            context,
            make_analysis(context),
            (context,),
        )

    assert provider.call_count == 2


@pytest.mark.asyncio
async def test_generation_does_not_mutate_or_reorder_inputs_or_batch() -> None:
    contexts = (make_context(index=2), make_context(index=1))
    target = contexts[1]
    analysis = make_analysis(target)
    batch = make_batch(target)
    provider = FakeLLMProvider(batch)
    contexts_before = tuple(item.model_dump(mode="python") for item in contexts)
    analysis_before = analysis.model_dump(mode="python")

    result = await InterviewQuestionService(provider).generate(
        target,
        analysis,
        contexts,
    )

    assert tuple(item.model_dump(mode="python") for item in contexts) == contexts_before
    assert analysis.model_dump(mode="python") == analysis_before
    assert result.value is batch
