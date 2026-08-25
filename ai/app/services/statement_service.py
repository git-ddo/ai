from collections.abc import Sequence

from app.core.exceptions import PortfolioStatementGenerationError, ReportPolicyError
from app.criteria import CriteriaLoader, CriteriaSet
from app.domain import (
    AnalysisDepth,
    NormalizedRepositoryContext,
    PortfolioStatementBatch,
    PortfolioSynthesis,
    RepositoryAnalysis,
)
from app.llm import GenerationMetadata, LLMProvider, StructuredGeneration
from app.prompts import (
    build_statement_correction_prompt,
    build_statement_prompt,
    build_system_prompt,
)
from app.validators import PortfolioStatementPolicyValidator

_DEPTH_RANK = {
    AnalysisDepth.P0: 0,
    AnalysisDepth.P1: 1,
    AnalysisDepth.P2: 2,
}


class PortfolioStatementService:
    """Generate and policy-check reusable portfolio statements."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        criteria_loader: CriteriaLoader | None = None,
        policy_validator: PortfolioStatementPolicyValidator | None = None,
    ) -> None:
        self._llm_provider = llm_provider
        self._criteria_loader = criteria_loader or CriteriaLoader()
        self._policy_validator = policy_validator or PortfolioStatementPolicyValidator()

    async def generate(
        self,
        contexts: Sequence[NormalizedRepositoryContext],
        repository_analyses: Sequence[RepositoryAnalysis],
        synthesis: PortfolioSynthesis,
        *,
        statement_count: int = 6,
    ) -> StructuredGeneration[PortfolioStatementBatch]:
        context_items = tuple(contexts)
        analysis_items = tuple(repository_analyses)
        maximum_depth = self._validate_service_input(
            context_items,
            analysis_items,
            synthesis,
            statement_count,
        )

        criteria = self._criteria_loader.load("BACKEND", maximum_depth.value)
        if criteria.analysis_depth is not maximum_depth:
            raise PortfolioStatementGenerationError(
                "Loaded criteria depth does not match the portfolio maximum depth."
            )

        system_prompt = build_system_prompt()
        initial_prompt = build_statement_prompt(
            context_items,
            analysis_items,
            synthesis,
            criteria,
            statement_count=statement_count,
        )
        initial_generation = await self._llm_provider.generate_structured(
            system_prompt=system_prompt,
            user_prompt=initial_prompt,
            response_model=PortfolioStatementBatch,
        )

        try:
            self._validate_generation(initial_generation.value, context_items, criteria)
        except ReportPolicyError as policy_error:
            correction_prompt = build_statement_correction_prompt(
                context_items,
                analysis_items,
                synthesis,
                criteria,
                tuple(violation.code for violation in policy_error.violations),
                statement_count=statement_count,
            )
            corrected_generation = await self._llm_provider.generate_structured(
                system_prompt=system_prompt,
                user_prompt=correction_prompt,
                response_model=PortfolioStatementBatch,
            )
            self._validate_generation(corrected_generation.value, context_items, criteria)
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
        batch: PortfolioStatementBatch,
        contexts: tuple[NormalizedRepositoryContext, ...],
        criteria: CriteriaSet,
    ) -> None:
        self._policy_validator.validate_references(batch, contexts)
        self._policy_validator.validate_content(batch, contexts, criteria)

    @staticmethod
    def _validate_service_input(
        contexts: tuple[NormalizedRepositoryContext, ...],
        repository_analyses: tuple[RepositoryAnalysis, ...],
        synthesis: PortfolioSynthesis,
        statement_count: int,
    ) -> AnalysisDepth:
        if not 1 <= len(contexts) <= 5:
            raise PortfolioStatementGenerationError(
                "Statement generation requires one to five repository contexts."
            )
        if not 1 <= len(repository_analyses) <= 5:
            raise PortfolioStatementGenerationError(
                "Statement generation requires one to five repository analyses."
            )

        context_names = [item.repository_full_name for item in contexts]
        analysis_names = [item.repository_full_name for item in repository_analyses]
        if len(context_names) != len(set(context_names)):
            raise PortfolioStatementGenerationError(
                "Statement generation contexts contain a duplicate repository."
            )
        if len(analysis_names) != len(set(analysis_names)):
            raise PortfolioStatementGenerationError(
                "Statement generation analyses contain a duplicate repository."
            )
        if set(context_names) != set(analysis_names):
            raise PortfolioStatementGenerationError(
                "Statement contexts and analyses must reference the same repositories."
            )

        representative_names = {
            project.repository_full_name for project in synthesis.representative_projects
        }
        if not representative_names.issubset(set(context_names)):
            raise PortfolioStatementGenerationError(
                "Statement synthesis contains an unknown representative repository."
            )

        if (
            isinstance(statement_count, bool)
            or not isinstance(statement_count, int)
            or not 1 <= statement_count <= 15
        ):
            raise PortfolioStatementGenerationError(
                "Statement count must be an integer between one and fifteen."
            )

        return max(
            (context.analysis_depth for context in contexts),
            key=_DEPTH_RANK.__getitem__,
        )


def _combine_metadata(
    first: GenerationMetadata,
    second: GenerationMetadata,
) -> GenerationMetadata:
    return GenerationMetadata(
        duration_ms=first.duration_ms + second.duration_ms,
        attempt_count=first.attempt_count + second.attempt_count,
    )


__all__ = ["PortfolioStatementService"]
