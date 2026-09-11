from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings
from app.core.exceptions import LLMConfigurationError
from app.domain import InternalPortfolioInput, InternalPortfolioReport
from app.llm import LLMProvider
from app.mappers import RequestWireMapper, ResponseWireMapper
from app.prompts import SYSTEM_PROMPT_VERSION
from app.services.report_service import PortfolioReportService


class PortfolioReportGenerator(Protocol):
    """Service contract consumed by the HTTP route."""

    async def generate(
        self,
        portfolio: InternalPortfolioInput,
        *,
        question_count: int = 5,
        statement_count: int = 6,
    ) -> InternalPortfolioReport: ...


type ProviderFactory = Callable[[Settings], LLMProvider]


@dataclass(frozen=True, slots=True)
class ReportRuntime:
    """Long-lived dependencies required by the portfolio report route."""

    report_service: PortfolioReportGenerator
    request_mapper: RequestWireMapper
    response_mapper: ResponseWireMapper
    evaluator_version: str

    def __post_init__(self) -> None:
        normalized_version = self.evaluator_version.strip()
        if not normalized_version:
            raise LLMConfigurationError("Evaluator version is not configured.")
        object.__setattr__(self, "evaluator_version", normalized_version)


def build_report_runtime(settings: Settings, provider: LLMProvider) -> ReportRuntime:
    """Build the production report dependency graph around one provider."""

    model = settings.gemini_model.strip() if settings.gemini_model is not None else ""
    if not model:
        raise LLMConfigurationError("Gemini model is not configured.")

    return ReportRuntime(
        report_service=PortfolioReportService(
            provider,
            deadline_seconds=settings.ai_analysis_deadline_seconds,
        ),
        request_mapper=RequestWireMapper(),
        response_mapper=ResponseWireMapper(),
        evaluator_version=f"{model}:{SYSTEM_PROMPT_VERSION}",
    )


__all__ = [
    "PortfolioReportGenerator",
    "ProviderFactory",
    "ReportRuntime",
    "build_report_runtime",
]
