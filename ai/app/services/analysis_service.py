from collections.abc import Sequence

from app.core.exceptions import PortfolioAnalysisAssemblyError
from app.criteria import CriteriaLoader, CriteriaSet
from app.domain import (
    AnalysisDepth,
    InterviewQuestion,
    InterviewQuestionBatch,
    NormalizedRepositoryContext,
    PortfolioAnalysis,
    PortfolioStatementBatch,
    PortfolioSynthesis,
    RepositoryAnalysis,
)
from app.validators import (
    InterviewQuestionPolicyValidator,
    PortfolioPolicyValidator,
    PortfolioStatementPolicyValidator,
    RepositoryPolicyValidator,
)

_DEPTH_RANK = {
    AnalysisDepth.P0: 0,
    AnalysisDepth.P1: 1,
    AnalysisDepth.P2: 2,
}


class PortfolioAnalysisAssembler:
    """Revalidate and deterministically assemble completed analysis components."""

    def __init__(
        self,
        criteria_loader: CriteriaLoader | None = None,
        repository_validator: RepositoryPolicyValidator | None = None,
        portfolio_validator: PortfolioPolicyValidator | None = None,
        interview_validator: InterviewQuestionPolicyValidator | None = None,
        statement_validator: PortfolioStatementPolicyValidator | None = None,
    ) -> None:
        self._criteria_loader = criteria_loader or CriteriaLoader()
        self._repository_validator = repository_validator or RepositoryPolicyValidator()
        self._portfolio_validator = portfolio_validator or PortfolioPolicyValidator()
        self._interview_validator = interview_validator or InterviewQuestionPolicyValidator()
        self._statement_validator = statement_validator or PortfolioStatementPolicyValidator()

    def assemble(
        self,
        contexts: Sequence[NormalizedRepositoryContext],
        repository_analyses: Sequence[RepositoryAnalysis],
        synthesis: PortfolioSynthesis,
        interview_batches: Sequence[InterviewQuestionBatch],
        statement_batch: PortfolioStatementBatch,
    ) -> PortfolioAnalysis:
        context_items = tuple(contexts)
        analysis_items = tuple(repository_analyses)
        interview_items = tuple(interview_batches)
        (
            analysis_by_repository,
            interview_by_repository,
            maximum_depth,
        ) = self._validate_input_relationships(
            context_items,
            analysis_items,
            synthesis,
            interview_items,
            statement_batch,
        )

        criteria_by_repository: dict[str, CriteriaSet] = {}
        ordered_analyses: list[RepositoryAnalysis] = []
        for context in context_items:
            criteria = self._load_matching_criteria(context.analysis_depth)
            criteria_by_repository[context.repository_full_name] = criteria
            analysis = analysis_by_repository[context.repository_full_name]
            self._repository_validator.validate_references(
                analysis,
                context,
                context_items,
            )
            self._repository_validator.validate_content(analysis, context, criteria)
            ordered_analyses.append(analysis)

        portfolio_criteria = self._load_matching_criteria(maximum_depth)
        self._portfolio_validator.validate_references(synthesis, context_items)
        self._portfolio_validator.validate_content(
            synthesis,
            context_items,
            portfolio_criteria,
        )

        flattened_questions: list[InterviewQuestion] = []
        for context in context_items:
            batch = interview_by_repository.get(context.repository_full_name)
            if batch is None:
                continue
            criteria = criteria_by_repository[context.repository_full_name]
            self._interview_validator.validate_references(batch, context, context_items)
            self._interview_validator.validate_content(batch, context, criteria)
            flattened_questions.extend(batch.questions)

        self._statement_validator.validate_references(statement_batch, context_items)
        self._statement_validator.validate_content(
            statement_batch,
            context_items,
            portfolio_criteria,
        )

        return PortfolioAnalysis(
            repository_analyses=tuple(ordered_analyses),
            synthesis=synthesis,
            interview_questions=tuple(flattened_questions),
            portfolio_statements=statement_batch.statements,
        )

    def _load_matching_criteria(self, depth: AnalysisDepth) -> CriteriaSet:
        criteria = self._criteria_loader.load("BACKEND", depth.value)
        if criteria.analysis_depth is not depth:
            raise PortfolioAnalysisAssemblyError(
                "Loaded criteria depth does not match the requested analysis depth."
            )
        return criteria

    @staticmethod
    def _validate_input_relationships(
        contexts: tuple[NormalizedRepositoryContext, ...],
        repository_analyses: tuple[RepositoryAnalysis, ...],
        synthesis: PortfolioSynthesis,
        interview_batches: tuple[InterviewQuestionBatch, ...],
        statement_batch: PortfolioStatementBatch,
    ) -> tuple[
        dict[str, RepositoryAnalysis],
        dict[str, InterviewQuestionBatch],
        AnalysisDepth,
    ]:
        if not 1 <= len(contexts) <= 5:
            raise PortfolioAnalysisAssemblyError(
                "Portfolio assembly requires one to five repository contexts."
            )
        if not 1 <= len(repository_analyses) <= 5:
            raise PortfolioAnalysisAssemblyError(
                "Portfolio assembly requires one to five repository analyses."
            )
        if not 0 <= len(interview_batches) <= 5:
            raise PortfolioAnalysisAssemblyError(
                "Portfolio assembly accepts zero to five interview batches."
            )
        if not isinstance(statement_batch, PortfolioStatementBatch):
            raise PortfolioAnalysisAssemblyError(
                "Portfolio assembly requires a portfolio statement batch."
            )

        context_names = [item.repository_full_name for item in contexts]
        analysis_names = [item.repository_full_name for item in repository_analyses]
        if len(context_names) != len(set(context_names)):
            raise PortfolioAnalysisAssemblyError(
                "Portfolio assembly contexts contain a duplicate repository."
            )
        if len(analysis_names) != len(set(analysis_names)):
            raise PortfolioAnalysisAssemblyError(
                "Portfolio assembly analyses contain a duplicate repository."
            )
        if set(context_names) != set(analysis_names):
            raise PortfolioAnalysisAssemblyError(
                "Portfolio contexts and analyses must reference the same repositories."
            )

        known_repositories = set(context_names)
        representative_names = {
            project.repository_full_name for project in synthesis.representative_projects
        }
        if not representative_names.issubset(known_repositories):
            raise PortfolioAnalysisAssemblyError(
                "Portfolio synthesis contains an unknown representative repository."
            )

        interview_by_repository: dict[str, InterviewQuestionBatch] = {}
        for batch in interview_batches:
            repository_name = batch.questions[0].repository_full_name
            if repository_name not in known_repositories:
                raise PortfolioAnalysisAssemblyError(
                    "Interview batch references an unknown repository."
                )
            if repository_name in interview_by_repository:
                raise PortfolioAnalysisAssemblyError(
                    "Portfolio assembly contains a duplicate interview repository."
                )
            interview_by_repository[repository_name] = batch

        maximum_depth = max(
            (context.analysis_depth for context in contexts),
            key=_DEPTH_RANK.__getitem__,
        )
        return (
            {analysis.repository_full_name: analysis for analysis in repository_analyses},
            interview_by_repository,
            maximum_depth,
        )


__all__ = ["PortfolioAnalysisAssembler"]
