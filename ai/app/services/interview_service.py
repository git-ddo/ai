from collections.abc import Sequence

from app.core.exceptions import InterviewQuestionGenerationError, ReportPolicyError
from app.criteria import CriteriaLoader, CriteriaSet
from app.domain import (
    InterviewQuestionBatch,
    NormalizedRepositoryContext,
    RepositoryAnalysis,
)
from app.llm import GenerationMetadata, LLMProvider, StructuredGeneration
from app.prompts import (
    build_interview_correction_prompt,
    build_interview_prompt,
    build_system_prompt,
)
from app.validators import InterviewQuestionPolicyValidator


class InterviewQuestionService:
    """Generate and policy-check one repository's interview question batch."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        criteria_loader: CriteriaLoader | None = None,
        policy_validator: InterviewQuestionPolicyValidator | None = None,
    ) -> None:
        self._llm_provider = llm_provider
        self._criteria_loader = criteria_loader or CriteriaLoader()
        self._policy_validator = policy_validator or InterviewQuestionPolicyValidator()

    async def generate(
        self,
        context: NormalizedRepositoryContext,
        repository_analysis: RepositoryAnalysis,
        portfolio_contexts: Sequence[NormalizedRepositoryContext],
        *,
        question_count: int = 5,
    ) -> StructuredGeneration[InterviewQuestionBatch]:
        contexts = tuple(portfolio_contexts)
        self._validate_service_input(
            context,
            repository_analysis,
            contexts,
            question_count,
        )

        criteria = self._criteria_loader.load("BACKEND", context.analysis_depth.value)
        if criteria.analysis_depth is not context.analysis_depth:
            raise InterviewQuestionGenerationError(
                "Loaded criteria depth does not match the repository context."
            )

        system_prompt = build_system_prompt()
        initial_prompt = build_interview_prompt(
            context,
            repository_analysis,
            criteria,
            question_count=question_count,
        )
        initial_generation = await self._llm_provider.generate_structured(
            system_prompt=system_prompt,
            user_prompt=initial_prompt,
            response_model=InterviewQuestionBatch,
        )

        try:
            self._validate_generation(initial_generation.value, context, contexts, criteria)
        except ReportPolicyError as policy_error:
            correction_prompt = build_interview_correction_prompt(
                context,
                repository_analysis,
                criteria,
                tuple(violation.code for violation in policy_error.violations),
                question_count=question_count,
            )
            corrected_generation = await self._llm_provider.generate_structured(
                system_prompt=system_prompt,
                user_prompt=correction_prompt,
                response_model=InterviewQuestionBatch,
            )
            self._validate_generation(corrected_generation.value, context, contexts, criteria)
            return StructuredGeneration(
                value=corrected_generation.value,
                metadata=_combine_metadata(
                    initial_generation.metadata,
                    corrected_generation.metadata,
                ),
            )

        return initial_generation

    def _validate_generation(
        self,
        batch: InterviewQuestionBatch,
        context: NormalizedRepositoryContext,
        portfolio_contexts: tuple[NormalizedRepositoryContext, ...],
        criteria: CriteriaSet,
    ) -> None:
        self._policy_validator.validate_references(
            batch,
            context,
            portfolio_contexts,
        )
        self._policy_validator.validate_content(batch, context, criteria)

    @staticmethod
    def _validate_service_input(
        context: NormalizedRepositoryContext,
        repository_analysis: RepositoryAnalysis,
        portfolio_contexts: tuple[NormalizedRepositoryContext, ...],
        question_count: int,
    ) -> None:
        if not 1 <= len(portfolio_contexts) <= 5:
            raise InterviewQuestionGenerationError(
                "Interview generation requires one to five portfolio contexts."
            )

        repository_names = [item.repository_full_name for item in portfolio_contexts]
        if len(repository_names) != len(set(repository_names)):
            raise InterviewQuestionGenerationError(
                "Interview generation contexts contain a duplicate repository."
            )

        matching_contexts = [item for item in portfolio_contexts if item == context]
        if len(matching_contexts) != 1:
            raise InterviewQuestionGenerationError(
                "The target repository context is not present exactly once."
            )

        if repository_analysis.repository_full_name != context.repository_full_name:
            raise InterviewQuestionGenerationError(
                "Repository analysis does not match the interview repository context."
            )

        if (
            isinstance(question_count, bool)
            or not isinstance(question_count, int)
            or not 1 <= question_count <= 10
        ):
            raise InterviewQuestionGenerationError(
                "Interview question count must be between one and ten."
            )


def _combine_metadata(
    first: GenerationMetadata,
    second: GenerationMetadata,
) -> GenerationMetadata:
    return GenerationMetadata(
        duration_ms=first.duration_ms + second.duration_ms,
        attempt_count=first.attempt_count + second.attempt_count,
    )


__all__ = ["InterviewQuestionService"]
