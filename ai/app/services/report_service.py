import asyncio
import math

from app.core.exceptions import PortfolioReportDeadlineError
from app.domain import (
    InternalGenerationRecord,
    InternalGenerationStage,
    InternalPortfolioInput,
    InternalPortfolioReport,
    InterviewQuestionBatch,
    RepositoryAnalysis,
)
from app.llm import GenerationMetadata, LLMProvider
from app.services.analysis_service import PortfolioAnalysisAssembler
from app.services.interview_service import InterviewQuestionService
from app.services.normalization_service import NormalizationService
from app.services.portfolio_service import PortfolioSynthesisService
from app.services.repository_service import RepositoryAnalysisService
from app.services.statement_service import PortfolioStatementService
from app.validators import AnalysisDepthValidator, EvidenceReferenceValidator


class PortfolioReportService:
    """Run the complete internal portfolio pipeline within one deadline."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        *,
        normalization_service: NormalizationService | None = None,
        evidence_validator: EvidenceReferenceValidator | None = None,
        depth_validator: AnalysisDepthValidator | None = None,
        analysis_assembler: PortfolioAnalysisAssembler | None = None,
        repository_service: RepositoryAnalysisService | None = None,
        portfolio_service: PortfolioSynthesisService | None = None,
        interview_service: InterviewQuestionService | None = None,
        statement_service: PortfolioStatementService | None = None,
        deadline_seconds: float = 270.0,
    ) -> None:
        self._deadline_seconds = self._validate_deadline(deadline_seconds)
        self._normalization_service = normalization_service or NormalizationService()
        self._evidence_validator = evidence_validator or EvidenceReferenceValidator()
        self._depth_validator = depth_validator or AnalysisDepthValidator()
        self._analysis_assembler = analysis_assembler or PortfolioAnalysisAssembler()
        self._repository_service = repository_service or RepositoryAnalysisService(llm_provider)
        self._portfolio_service = portfolio_service or PortfolioSynthesisService(llm_provider)
        self._interview_service = interview_service or InterviewQuestionService(llm_provider)
        self._statement_service = statement_service or PortfolioStatementService(llm_provider)

    async def generate(
        self,
        portfolio: InternalPortfolioInput,
        *,
        question_count: int = 5,
        statement_count: int = 6,
    ) -> InternalPortfolioReport:
        try:
            async with asyncio.timeout(self._deadline_seconds):
                return await self._generate(
                    portfolio,
                    question_count=question_count,
                    statement_count=statement_count,
                )
        except TimeoutError as exc:
            raise PortfolioReportDeadlineError(
                "Portfolio report generation exceeded the configured deadline."
            ) from exc

    async def _generate(
        self,
        portfolio: InternalPortfolioInput,
        *,
        question_count: int,
        statement_count: int,
    ) -> InternalPortfolioReport:
        self._evidence_validator.validate(portfolio)
        self._depth_validator.validate(portfolio)
        contexts = tuple(
            self._normalization_service.normalize(repository)
            for repository in portfolio.repositories
        )

        repository_analyses: list[RepositoryAnalysis] = []
        repository_records: list[InternalGenerationRecord] = []
        for context in contexts:
            repository_generation = await self._repository_service.analyze(context, contexts)
            repository_analyses.append(repository_generation.value)
            repository_records.append(
                self._generation_record(
                    InternalGenerationStage.REPOSITORY,
                    repository_generation.metadata,
                    repository_full_name=context.repository_full_name,
                )
            )
        analysis_items = tuple(repository_analyses)

        portfolio_generation = await self._portfolio_service.synthesize(
            contexts,
            analysis_items,
        )
        portfolio_record = self._generation_record(
            InternalGenerationStage.PORTFOLIO,
            portfolio_generation.metadata,
        )

        interview_batches: list[InterviewQuestionBatch] = []
        interview_records: list[InternalGenerationRecord] = []
        for context, repository_analysis in zip(
            contexts,
            analysis_items,
            strict=True,
        ):
            interview_generation = await self._interview_service.generate(
                context,
                repository_analysis,
                contexts,
                question_count=question_count,
            )
            interview_batches.append(interview_generation.value)
            interview_records.append(
                self._generation_record(
                    InternalGenerationStage.INTERVIEW,
                    interview_generation.metadata,
                    repository_full_name=context.repository_full_name,
                )
            )

        statement_generation = await self._statement_service.generate(
            contexts,
            analysis_items,
            portfolio_generation.value,
            statement_count=statement_count,
        )
        statement_record = self._generation_record(
            InternalGenerationStage.STATEMENT,
            statement_generation.metadata,
        )

        analysis = self._analysis_assembler.assemble(
            contexts=contexts,
            repository_analyses=analysis_items,
            synthesis=portfolio_generation.value,
            interview_batches=tuple(interview_batches),
            statement_batch=statement_generation.value,
        )
        return InternalPortfolioReport(
            analysis=analysis,
            generation_records=(
                *repository_records,
                portfolio_record,
                *interview_records,
                statement_record,
            ),
        )

    @staticmethod
    def _validate_deadline(deadline_seconds: float) -> float:
        if (
            isinstance(deadline_seconds, bool)
            or not isinstance(deadline_seconds, (int, float))
            or not math.isfinite(deadline_seconds)
            or not 0 < deadline_seconds <= 300
        ):
            raise ValueError(
                "Analysis deadline must be finite, greater than 0, and at most 300 seconds."
            )
        return float(deadline_seconds)

    @staticmethod
    def _generation_record(
        stage: InternalGenerationStage,
        metadata: GenerationMetadata,
        *,
        repository_full_name: str | None = None,
    ) -> InternalGenerationRecord:
        return InternalGenerationRecord(
            stage=stage,
            repository_full_name=repository_full_name,
            duration_ms=metadata.duration_ms,
            attempt_count=metadata.attempt_count,
        )


__all__ = ["PortfolioReportService"]
