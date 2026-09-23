from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from app.domain import (
    EvidenceConfidence,
    PortfolioSynthesis,
    RecommendationPriority,
    RepositoryAnalysis,
)


class _PriorAnalysisDTO(BaseModel):
    """Prompt-only projection of validated analysis data."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class PriorGroundedAnalysisDTO(_PriorAnalysisDTO):
    content: str
    confidence: EvidenceConfidence
    evidence_refs: tuple[str, ...]
    claim_refs: tuple[str, ...]
    technology_names: tuple[str, ...]
    file_paths: tuple[str, ...]
    priority: RecommendationPriority | None


class PriorRepositoryAnalysisDTO(_PriorAnalysisDTO):
    repository_full_name: str
    summary: PriorGroundedAnalysisDTO
    observations: tuple[PriorGroundedAnalysisDTO, ...]
    strengths: tuple[PriorGroundedAnalysisDTO, ...]
    recommendations: tuple[PriorGroundedAnalysisDTO, ...]
    limitations: tuple[str, ...]


class PriorRepresentativeProjectDTO(_PriorAnalysisDTO):
    repository_full_name: str
    reason: str
    confidence: EvidenceConfidence
    evidence_refs: tuple[str, ...]
    claim_refs: tuple[str, ...]


class PriorPortfolioSynthesisDTO(_PriorAnalysisDTO):
    overall_summary: PriorGroundedAnalysisDTO
    representative_projects: tuple[PriorRepresentativeProjectDTO, ...]
    strengths: tuple[PriorGroundedAnalysisDTO, ...]
    gaps: tuple[PriorGroundedAnalysisDTO, ...]
    next_actions: tuple[PriorGroundedAnalysisDTO, ...]
    job_appeal: PriorGroundedAnalysisDTO
    limitations: tuple[str, ...]


def project_repository_analysis(
    analysis: RepositoryAnalysis,
) -> PriorRepositoryAnalysisDTO:
    return PriorRepositoryAnalysisDTO(
        repository_full_name=analysis.repository_full_name,
        summary=_project_grounded_analysis(analysis.summary),
        observations=tuple(_project_grounded_analysis(item) for item in analysis.observations),
        strengths=tuple(_project_grounded_analysis(item) for item in analysis.strengths),
        recommendations=tuple(
            _project_grounded_analysis(item) for item in analysis.recommendations
        ),
        limitations=analysis.limitations,
    )


def project_repository_analyses(
    analyses: Sequence[RepositoryAnalysis],
) -> tuple[PriorRepositoryAnalysisDTO, ...]:
    return tuple(project_repository_analysis(analysis) for analysis in analyses)


def collect_repository_analysis_evidence_refs(
    analysis: RepositoryAnalysis,
) -> tuple[str, ...]:
    """Collect Evidence IDs used by one validated RepositoryAnalysis in stable order."""

    items = (
        analysis.summary,
        *analysis.observations,
        *analysis.strengths,
        *analysis.recommendations,
    )
    return tuple(
        dict.fromkeys(evidence_ref for item in items for evidence_ref in item.evidence_refs)
    )


def project_portfolio_synthesis(
    synthesis: PortfolioSynthesis,
) -> PriorPortfolioSynthesisDTO:
    return PriorPortfolioSynthesisDTO(
        overall_summary=_project_grounded_analysis(synthesis.overall_summary),
        representative_projects=tuple(
            PriorRepresentativeProjectDTO(
                repository_full_name=project.repository_full_name,
                reason=project.reason,
                confidence=project.confidence,
                evidence_refs=project.evidence_refs,
                claim_refs=project.claim_refs,
            )
            for project in synthesis.representative_projects
        ),
        strengths=tuple(_project_grounded_analysis(item) for item in synthesis.strengths),
        gaps=tuple(_project_grounded_analysis(item) for item in synthesis.gaps),
        next_actions=tuple(_project_grounded_analysis(item) for item in synthesis.next_actions),
        job_appeal=_project_grounded_analysis(synthesis.job_appeal),
        limitations=synthesis.limitations,
    )


def _project_grounded_analysis(item: object) -> PriorGroundedAnalysisDTO:
    return PriorGroundedAnalysisDTO.model_validate(
        item,
        from_attributes=True,
    )


__all__ = [
    "PriorPortfolioSynthesisDTO",
    "PriorRepositoryAnalysisDTO",
    "collect_repository_analysis_evidence_refs",
    "project_portfolio_synthesis",
    "project_repository_analyses",
    "project_repository_analysis",
]
