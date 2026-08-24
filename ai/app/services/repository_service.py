from collections.abc import Sequence

from app.core.exceptions import ReportPolicyError, RepositoryAnalysisError
from app.criteria import CriteriaLoader, CriteriaSet
from app.domain import NormalizedRepositoryContext, RepositoryAnalysis
from app.llm import GenerationMetadata, LLMProvider, StructuredGeneration
from app.prompts import (
    build_repository_correction_prompt,
    build_repository_prompt,
    build_system_prompt,
)
from app.validators import RepositoryPolicyValidator


class RepositoryAnalysisService:
    """Generate and policy-check one repository analysis without provider coupling."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        criteria_loader: CriteriaLoader | None = None,
        policy_validator: RepositoryPolicyValidator | None = None,
    ) -> None:
        self._llm_provider = llm_provider
        self._criteria_loader = criteria_loader or CriteriaLoader()
        self._policy_validator = policy_validator or RepositoryPolicyValidator()

    async def analyze(
        self,
        context: NormalizedRepositoryContext,
        portfolio_contexts: Sequence[NormalizedRepositoryContext],
    ) -> StructuredGeneration[RepositoryAnalysis]:
        contexts = tuple(portfolio_contexts)
        self._validate_service_input(context, contexts)

        criteria = self._criteria_loader.load("BACKEND", context.analysis_depth.value)
        if criteria.analysis_depth is not context.analysis_depth:
            raise RepositoryAnalysisError(
                "Loaded criteria depth does not match the repository context."
            )

        system_prompt = build_system_prompt()
        initial_prompt = build_repository_prompt(context, criteria)
        initial_generation = await self._llm_provider.generate_structured(
            system_prompt=system_prompt,
            user_prompt=initial_prompt,
            response_model=RepositoryAnalysis,
        )

        try:
            self._validate_generation(initial_generation.value, context, contexts, criteria)
        except ReportPolicyError as policy_error:
            correction_prompt = build_repository_correction_prompt(
                context,
                criteria,
                tuple(violation.code for violation in policy_error.violations),
            )
            corrected_generation = await self._llm_provider.generate_structured(
                system_prompt=system_prompt,
                user_prompt=correction_prompt,
                response_model=RepositoryAnalysis,
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
        analysis: RepositoryAnalysis,
        context: NormalizedRepositoryContext,
        portfolio_contexts: tuple[NormalizedRepositoryContext, ...],
        criteria: CriteriaSet,
    ) -> None:
        self._policy_validator.validate_references(
            analysis,
            context,
            portfolio_contexts,
        )
        self._policy_validator.validate_content(analysis, context, criteria)

    @staticmethod
    def _validate_service_input(
        context: NormalizedRepositoryContext,
        portfolio_contexts: tuple[NormalizedRepositoryContext, ...],
    ) -> None:
        if not 1 <= len(portfolio_contexts) <= 5:
            raise RepositoryAnalysisError(
                "Repository analysis requires one to five portfolio contexts."
            )

        repository_names = [item.repository_full_name for item in portfolio_contexts]
        if len(repository_names) != len(set(repository_names)):
            raise RepositoryAnalysisError("Portfolio contexts contain a duplicate repository.")

        matching_contexts = [item for item in portfolio_contexts if item == context]
        if len(matching_contexts) != 1:
            raise RepositoryAnalysisError(
                "The target repository context is not present exactly once."
            )


def _combine_metadata(
    first: GenerationMetadata,
    second: GenerationMetadata,
) -> GenerationMetadata:
    return GenerationMetadata(
        duration_ms=first.duration_ms + second.duration_ms,
        attempt_count=first.attempt_count + second.attempt_count,
    )


__all__ = ["RepositoryAnalysisService"]
