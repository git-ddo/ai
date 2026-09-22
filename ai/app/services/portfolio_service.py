from collections.abc import Sequence

from app.core.exceptions import PortfolioSynthesisError, ReportPolicyError
from app.criteria import CriteriaLoader, CriteriaSet
from app.domain import (
    AnalysisDepth,
    NormalizedRepositoryContext,
    PortfolioSynthesis,
    PortfolioSynthesisDraft,
    RepositoryAnalysis,
)
from app.llm import GenerationMetadata, LLMProvider, StructuredGeneration
from app.prompts import (
    build_portfolio_correction_prompt,
    build_portfolio_prompt,
    build_system_prompt,
)
from app.services.criterion_assignment_service import CriterionAssignmentService
from app.services.criterion_context_service import CriterionContextService
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
        criterion_context_service: CriterionContextService | None = None,
        criterion_assignment_service: CriterionAssignmentService | None = None,
    ) -> None:
        self._llm_provider = llm_provider
        self._criteria_loader = criteria_loader or CriteriaLoader()
        self._policy_validator = policy_validator or PortfolioPolicyValidator()
        self._criterion_context_service = criterion_context_service or CriterionContextService()
        self._criterion_assignment_service = (
            criterion_assignment_service or CriterionAssignmentService()
        )

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
        criterion_contexts = self._criterion_context_service.build(context_items, criteria)

        system_prompt = build_system_prompt()
        initial_prompt = build_portfolio_prompt(
            context_items,
            analysis_items,
            criteria,
            criterion_contexts=criterion_contexts,
        )
        initial_generation = await self._llm_provider.generate_structured(
            system_prompt=system_prompt,
            user_prompt=initial_prompt,
            response_model=PortfolioSynthesisDraft,
        )

        try:
            synthesis = self._criterion_assignment_service.assign_portfolio(
                initial_generation.value,
                criterion_contexts,
            )
            self._validate_generation(
                synthesis,
                context_items,
                criteria,
            )
        except ReportPolicyError as policy_error:
            correction_prompt = build_portfolio_correction_prompt(
                context_items,
                analysis_items,
                criteria,
                tuple(violation.code for violation in policy_error.violations),
                criterion_contexts=criterion_contexts,
            )
            corrected_generation = await self._llm_provider.generate_structured(
                system_prompt=system_prompt,
                user_prompt=correction_prompt,
                response_model=PortfolioSynthesisDraft,
            )
            corrected_synthesis = self._criterion_assignment_service.assign_portfolio(
                corrected_generation.value,
                criterion_contexts,
            )
            self._validate_generation(
                corrected_synthesis,
                context_items,
                criteria,
            )
            return StructuredGeneration(
                value=corrected_synthesis,
                metadata=_combine_metadata(
                    initial_generation.metadata,
                    corrected_generation.metadata,
                ),
            )

        return StructuredGeneration(value=synthesis, metadata=initial_generation.metadata)

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
