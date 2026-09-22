from __future__ import annotations

import json
from collections.abc import Mapping

from pydantic import BaseModel

from app.domain import (
    EvidenceGroundedAnalysisDraft,
    GroundedAnalysisDraft,
    GroundedAnalysisItem,
    PortfolioSynthesis,
    PortfolioSynthesisDraft,
    RecommendationAnalysisDraft,
    RepositoryAnalysis,
    RepositoryAnalysisDraft,
)
from app.prompts.context import REPOSITORY_DATA_SECTION


def project_provider_result(
    value: BaseModel,
    response_model: type[BaseModel],
    user_prompt: str,
) -> BaseModel:
    """Project final test fixtures into the provider-owned schema requested by a service."""

    context_ids = _criterion_context_ids(user_prompt)
    if response_model is RepositoryAnalysisDraft and isinstance(value, RepositoryAnalysis):
        return _repository_draft(value, context_ids)
    if response_model is PortfolioSynthesisDraft and isinstance(value, PortfolioSynthesis):
        return _portfolio_draft(value, context_ids)
    return value


def _repository_draft(
    analysis: RepositoryAnalysis,
    context_ids: Mapping[str, str],
) -> RepositoryAnalysisDraft:
    return RepositoryAnalysisDraft(
        repository_full_name=analysis.repository_full_name,
        summary=_common_draft(analysis.summary, context_ids),
        observations=tuple(_evidence_draft(item, context_ids) for item in analysis.observations),
        strengths=tuple(_common_draft(item, context_ids) for item in analysis.strengths),
        recommendations=tuple(
            _recommendation_draft(item, context_ids) for item in analysis.recommendations
        ),
        limitations=analysis.limitations,
    )


def _portfolio_draft(
    synthesis: PortfolioSynthesis,
    context_ids: Mapping[str, str],
) -> PortfolioSynthesisDraft:
    return PortfolioSynthesisDraft(
        overall_summary=_evidence_draft(synthesis.overall_summary, context_ids),
        representative_projects=synthesis.representative_projects,
        strengths=tuple(_evidence_draft(item, context_ids) for item in synthesis.strengths),
        gaps=tuple(_evidence_draft(item, context_ids) for item in synthesis.gaps),
        next_actions=tuple(
            _recommendation_draft(item, context_ids) for item in synthesis.next_actions
        ),
        job_appeal=_evidence_draft(synthesis.job_appeal, context_ids),
        limitations=synthesis.limitations,
    )


def _common_draft(
    item: GroundedAnalysisItem,
    context_ids: Mapping[str, str],
) -> GroundedAnalysisDraft:
    return GroundedAnalysisDraft(**_provider_item_data(item, context_ids))


def _evidence_draft(
    item: GroundedAnalysisItem,
    context_ids: Mapping[str, str],
) -> EvidenceGroundedAnalysisDraft:
    return EvidenceGroundedAnalysisDraft(**_provider_item_data(item, context_ids))


def _recommendation_draft(
    item: GroundedAnalysisItem,
    context_ids: Mapping[str, str],
) -> RecommendationAnalysisDraft:
    return RecommendationAnalysisDraft(
        **_provider_item_data(item, context_ids),
        priority=item.priority,
    )


def _provider_item_data(
    item: GroundedAnalysisItem,
    context_ids: Mapping[str, str],
) -> dict[str, object]:
    return {
        "content": item.content,
        "confidence": item.confidence,
        "evidence_refs": item.evidence_refs,
        "claim_refs": item.claim_refs,
        "criterion_context_refs": tuple(
            context_ids.get(key, f"ctx_{900000 + index}")
            for index, key in enumerate(item.criterion_keys, start=1)
        ),
        "technology_names": item.technology_names,
        "file_paths": item.file_paths,
    }


def _criterion_context_ids(user_prompt: str) -> dict[str, str]:
    start_marker = f"[{REPOSITORY_DATA_SECTION}_BEGIN]\n"
    end_marker = f"\n[{REPOSITORY_DATA_SECTION}_END]"
    payload = user_prompt.split(start_marker, maxsplit=1)[1].split(end_marker, maxsplit=1)[0]
    repository_data = json.loads(payload)
    return {
        item["criterion_key"]: item["context_id"] for item in repository_data["criterionContexts"]
    }
