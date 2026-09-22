from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.criteria import CriteriaSet, Criterion
from app.domain import (
    AnalysisDepth,
    CodeObservationType,
    InternalEvidence,
    NormalizedRepositoryContext,
)


@dataclass(frozen=True, slots=True)
class CriterionEvidenceContext:
    """One service-owned Criterion scope exposed to an LLM generation stage."""

    context_id: str
    criterion_key: str
    analysis_depth: AnalysisDepth
    title: str
    description: str
    eligible_evidence_refs: tuple[str, ...]
    eligible_claim_refs: tuple[str, ...]


_FACT_KEY_CANDIDATES: dict[str, frozenset[str]] = {
    "README": frozenset({"README_READINESS"}),
    "README_SECTIONS_OBSERVED": frozenset({"README_READINESS"}),
    "BUILD_MANIFEST": frozenset({"TECH_STACK_EVIDENCE"}),
    "TECHNOLOGY_DEPENDENCY": frozenset({"TECH_STACK_EVIDENCE"}),
    "LANGUAGE_BREAKDOWN": frozenset({"TECH_STACK_EVIDENCE"}),
    "TECHNOLOGY_DETECTED": frozenset({"TECH_STACK_EVIDENCE"}),
    "TEST_FILES_OBSERVED": frozenset({"TEST_PRESENCE"}),
    "CONTAINER_CONFIGURATION": frozenset({"DOCKER_CONFIGURATION"}),
    "DOCKER_COMPOSE_OBSERVED": frozenset({"DOCKER_CONFIGURATION"}),
    "CI_CONFIGURATION": frozenset({"GITHUB_ACTIONS_CONFIGURATION"}),
    "GITHUB_ACTIONS_NOT_OBSERVED": frozenset({"GITHUB_ACTIONS_CONFIGURATION"}),
    "GITHUB_ACTIONS_WORKFLOW_OBSERVED": frozenset({"GITHUB_ACTIONS_CONFIGURATION"}),
    "PROJECT_STRUCTURE": frozenset({"TEST_PRESENCE", "GITHUB_ACTIONS_CONFIGURATION"}),
    "COMMIT_SUMMARY": frozenset({"ACTIVITY_SCOPE"}),
    "ACTIVITY_SUMMARY": frozenset({"ACTIVITY_SCOPE"}),
    "COMMIT_ACTIVITY_OBSERVED": frozenset({"ACTIVITY_SCOPE"}),
    "CHANGED_FILES": frozenset({"CHANGE_AREA_OBSERVATION"}),
}

_CODE_OBSERVATION_CRITERION: dict[CodeObservationType, str] = {
    CodeObservationType.SNIPPET_SCOPE: "SNIPPET_SCOPE",
    CodeObservationType.INPUT_VALIDATION: "INPUT_VALIDATION_OBSERVATION",
    CodeObservationType.ERROR_HANDLING: "ERROR_HANDLING_OBSERVATION",
    CodeObservationType.RESPONSIBILITY: "RESPONSIBILITY_OBSERVATION",
    CodeObservationType.TEST_CASE: "TEST_CASE_OBSERVATION",
}


class CriterionContextError(ValueError):
    """Raised when deterministic Criterion Context construction is invalid."""


class CriterionContextService:
    """Build Criterion-scoped Evidence contexts without delegating key selection to an LLM."""

    def build(
        self,
        repositories: Sequence[NormalizedRepositoryContext],
        criteria: CriteriaSet,
    ) -> tuple[CriterionEvidenceContext, ...]:
        contexts = tuple(repositories)
        self._validate_input(contexts, criteria)

        evidence = tuple(item for context in contexts for item in context.evidence)
        claims = tuple(item for context in contexts for item in context.user_claims)
        result: list[CriterionEvidenceContext] = []
        for index, criterion in enumerate(criteria.criteria, start=1):
            evidence_refs = tuple(
                item.evidence_id for item in evidence if self._supports(item, criterion, criteria)
            )
            claim_refs = (
                tuple(item.claim_id for item in claims) if criterion.allow_user_claims else ()
            )
            if not evidence_refs and not claim_refs:
                continue
            result.append(
                CriterionEvidenceContext(
                    context_id=f"ctx_{index:03d}",
                    criterion_key=criterion.key,
                    analysis_depth=criterion.analysis_depth,
                    title=criterion.title,
                    description=criterion.description,
                    eligible_evidence_refs=evidence_refs,
                    eligible_claim_refs=claim_refs,
                )
            )
        if not result:
            raise CriterionContextError(
                "No Criterion Context can be built from the supplied evidence."
            )
        return tuple(result)

    @staticmethod
    def _validate_input(
        repositories: tuple[NormalizedRepositoryContext, ...],
        criteria: CriteriaSet,
    ) -> None:
        if not 1 <= len(repositories) <= 5:
            raise CriterionContextError("Criterion Context requires one to five repositories.")
        maximum_depth = max(
            (context.analysis_depth for context in repositories),
            key=lambda item: list(AnalysisDepth).index(item),
        )
        if criteria.analysis_depth is not maximum_depth:
            raise CriterionContextError(
                "Criterion Context criteria must match the deepest repository."
            )

    @classmethod
    def _supports(
        cls,
        evidence: InternalEvidence,
        criterion: Criterion,
        criteria: CriteriaSet,
    ) -> bool:
        if evidence.analysis_depth is not criterion.analysis_depth:
            return False
        if evidence.evidence_type not in criterion.allowed_evidence_types:
            return False

        compatible_keys = {
            item.key
            for item in criteria.criteria
            if item.analysis_depth is evidence.analysis_depth
            and evidence.evidence_type in item.allowed_evidence_types
        }
        narrowed = cls._narrowed_candidates(evidence) & compatible_keys
        candidates = narrowed or compatible_keys
        return criterion.key in candidates

    @staticmethod
    def _narrowed_candidates(evidence: InternalEvidence) -> set[str]:
        candidates = set(_FACT_KEY_CANDIDATES.get(evidence.key.upper(), ()))
        candidates.update(
            _CODE_OBSERVATION_CRITERION[item] for item in evidence.code_observation_types
        )
        return candidates


__all__ = [
    "CriterionContextError",
    "CriterionContextService",
    "CriterionEvidenceContext",
]
