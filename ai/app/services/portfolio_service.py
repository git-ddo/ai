from collections.abc import Sequence

from app.core.exceptions import PortfolioSynthesisError, ReportPolicyError
from app.criteria import CriteriaLoader, CriteriaSet
from app.domain import (
    AnalysisDepth,
    NormalizedRepositoryContext,
    PortfolioSynthesis,
    RepositoryAnalysis,
)
from app.llm import GenerationMetadata, LLMProvider, StructuredGeneration
from app.prompts import (
    build_portfolio_correction_prompt,
    build_portfolio_prompt,
    build_system_prompt,
)
from app.validators import PortfolioPolicyValidator

_DEPTH_RANK = {
    AnalysisDepth.P0: 0,
    AnalysisDepth.P1: 1,
    AnalysisDepth.P2: 2,
}


class PortfolioSynthesisService:
    """Generate and policy-check one portfolio synthesis without provider coupling."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        criteria_loader: CriteriaLoader | None = None,
        policy_validator: PortfolioPolicyValidator | None = None,
    ) -> None:
        self._llm_provider = llm_provider
        self._criteria_loader = criteria_loader or CriteriaLoader()
        self._policy_validator = policy_validator or PortfolioPolicyValidator()

    async def synthesize(
        self,
        contexts: Sequence[NormalizedRepositoryContext],
        repository_analyses: Sequence[RepositoryAnalysis],
    ) -> StructuredGeneration[PortfolioSynthesis]:
        context_items = tuple(contexts)
        analysis_items = tuple(repository_analyses)
        self._validate_service_input(context_items, analysis_items)

        maximum_depth = max(
            (context.analysis_depth for context in context_items),
            key=_DEPTH_RANK.__getitem__,
        )
        criteria = self._criteria_loader.load("BACKEND", maximum_depth.value)
        if criteria.analysis_depth is not maximum_depth:
            raise PortfolioSynthesisError(
                "Loaded criteria depth does not match the portfolio maximum depth."
            )

        system_prompt = build_system_prompt()
        initial_prompt = build_portfolio_prompt(
            context_items,
            analysis_items,
            criteria,
        )
        initial_generation = await self._llm_provider.generate_structured(
            system_prompt=system_prompt,
            user_prompt=initial_prompt,
            response_model=PortfolioSynthesis,
        )

        try:
            self._validate_generation(
                initial_generation.value,
                context_items,
                criteria,
            )
        except ReportPolicyError as policy_error:
            correction_prompt = build_portfolio_correction_prompt(
                context_items,
                analysis_items,
                criteria,
                tuple(violation.code for violation in policy_error.violations),
            )
            corrected_generation = await self._llm_provider.generate_structured(
                system_prompt=system_prompt,
                user_prompt=correction_prompt,
                response_model=PortfolioSynthesis,
            )
            self._validate_generation(
                corrected_generation.value,
                context_items,
                criteria,
            )
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
        synthesis: PortfolioSynthesis,
        contexts: tuple[NormalizedRepositoryContext, ...],
        criteria: CriteriaSet,
    ) -> None:
        self._policy_validator.validate_references(synthesis, contexts)
        self._policy_validator.validate_content(synthesis, contexts, criteria)

    @staticmethod
    def _validate_service_input(
        contexts: tuple[NormalizedRepositoryContext, ...],
        repository_analyses: tuple[RepositoryAnalysis, ...],
    ) -> None:
        if not 1 <= len(contexts) <= 5:
            raise PortfolioSynthesisError(
                "Portfolio synthesis requires one to five repository contexts."
            )
        if not 1 <= len(repository_analyses) <= 5:
            raise PortfolioSynthesisError(
                "Portfolio synthesis requires one to five repository analyses."
            )

        context_names = [item.repository_full_name for item in contexts]
        analysis_names = [item.repository_full_name for item in repository_analyses]
        if len(context_names) != len(set(context_names)):
            raise PortfolioSynthesisError(
                "Portfolio synthesis contexts contain a duplicate repository."
            )
        if len(analysis_names) != len(set(analysis_names)):
            raise PortfolioSynthesisError(
                "Portfolio synthesis analyses contain a duplicate repository."
            )
        if set(context_names) != set(analysis_names):
            raise PortfolioSynthesisError(
                "Portfolio contexts and analyses must reference the same repositories."
            )


def _combine_metadata(
    first: GenerationMetadata,
    second: GenerationMetadata,
) -> GenerationMetadata:
    return GenerationMetadata(
        duration_ms=first.duration_ms + second.duration_ms,
        attempt_count=first.attempt_count + second.attempt_count,
    )


__all__ = ["PortfolioSynthesisService"]
