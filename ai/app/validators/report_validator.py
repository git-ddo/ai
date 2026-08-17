from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.core.exceptions import ReportPolicyError
from app.domain import (
    GroundedAnalysisItem,
    NormalizedRepositoryContext,
    RepositoryAnalysis,
)


class PolicyViolationCode(StrEnum):
    UNKNOWN_EVIDENCE_REF = "UNKNOWN_EVIDENCE_REF"
    UNKNOWN_CLAIM_REF = "UNKNOWN_CLAIM_REF"
    CROSS_REPOSITORY_REF = "CROSS_REPOSITORY_REF"
    UNKNOWN_TECHNOLOGY = "UNKNOWN_TECHNOLOGY"
    UNKNOWN_FILE_PATH = "UNKNOWN_FILE_PATH"
    P0_SCOPE_VIOLATION = "P0_SCOPE_VIOLATION"
    USER_ABILITY_ASSERTION = "USER_ABILITY_ASSERTION"
    CONTRIBUTION_ASSERTION = "CONTRIBUTION_ASSERTION"
    NOT_OBSERVED_MISUSE = "NOT_OBSERVED_MISUSE"
    USER_CLAIM_AS_FACT = "USER_CLAIM_AS_FACT"
    MISSING_DERIVED_EVIDENCE = "MISSING_DERIVED_EVIDENCE"


@dataclass(frozen=True, slots=True)
class PolicyViolation:
    code: PolicyViolationCode
    message: str
    field_path: str | None = None

    def __post_init__(self) -> None:
        message = self.message.strip()
        if not message:
            raise ValueError("Policy violation message must not be blank")
        object.__setattr__(self, "message", message)

        if self.field_path is None:
            return

        field_path = self.field_path.strip()
        if not field_path:
            raise ValueError("Policy violation field_path must not be blank")
        object.__setattr__(self, "field_path", field_path)


class RepositoryPolicyValidator:
    """Validate repository-scoped Evidence and UserClaim references."""

    def validate_references(
        self,
        analysis: RepositoryAnalysis,
        expected_context: NormalizedRepositoryContext,
        portfolio_contexts: Sequence[NormalizedRepositoryContext],
    ) -> None:
        expected_repository = expected_context.repository_full_name
        evidence_owners = {
            evidence.evidence_id: context.repository_full_name
            for context in portfolio_contexts
            for evidence in context.evidence
        }
        claim_owners = {
            claim.claim_id: context.repository_full_name
            for context in portfolio_contexts
            for claim in context.user_claims
        }

        violations: list[PolicyViolation] = []
        if analysis.repository_full_name != expected_repository:
            violations.append(
                PolicyViolation(
                    code=PolicyViolationCode.CROSS_REPOSITORY_REF,
                    message="Repository analysis does not match the expected repository.",
                    field_path="repository_full_name",
                )
            )

        for field_path, item in self._iter_analysis_items(analysis):
            violations.extend(
                self._find_item_reference_violations(
                    item=item,
                    field_path=field_path,
                    expected_repository=expected_repository,
                    evidence_owners=evidence_owners,
                    claim_owners=claim_owners,
                )
            )

        if violations:
            raise ReportPolicyError(violations)

    @staticmethod
    def _iter_analysis_items(
        analysis: RepositoryAnalysis,
    ) -> tuple[tuple[str, GroundedAnalysisItem], ...]:
        indexed_items: list[tuple[str, GroundedAnalysisItem]] = [("summary", analysis.summary)]
        collections = (
            ("observations", analysis.observations),
            ("strengths", analysis.strengths),
            ("recommendations", analysis.recommendations),
        )
        for collection_name, items in collections:
            indexed_items.extend(
                (f"{collection_name}[{index}]", item) for index, item in enumerate(items)
            )
        return tuple(indexed_items)

    @staticmethod
    def _find_item_reference_violations(
        *,
        item: GroundedAnalysisItem,
        field_path: str,
        expected_repository: str,
        evidence_owners: dict[str, str],
        claim_owners: dict[str, str],
    ) -> tuple[PolicyViolation, ...]:
        violations: list[PolicyViolation] = []

        for index, evidence_ref in enumerate(item.evidence_refs):
            owner = evidence_owners.get(evidence_ref)
            reference_path = f"{field_path}.evidence_refs[{index}]"
            if owner is None:
                violations.append(
                    PolicyViolation(
                        code=PolicyViolationCode.UNKNOWN_EVIDENCE_REF,
                        message="Analysis item references unknown evidence.",
                        field_path=reference_path,
                    )
                )
            elif owner != expected_repository:
                violations.append(
                    PolicyViolation(
                        code=PolicyViolationCode.CROSS_REPOSITORY_REF,
                        message="Analysis item references evidence from another repository.",
                        field_path=reference_path,
                    )
                )

        for index, claim_ref in enumerate(item.claim_refs):
            owner = claim_owners.get(claim_ref)
            reference_path = f"{field_path}.claim_refs[{index}]"
            if owner is None:
                violations.append(
                    PolicyViolation(
                        code=PolicyViolationCode.UNKNOWN_CLAIM_REF,
                        message="Analysis item references an unknown user claim.",
                        field_path=reference_path,
                    )
                )
            elif owner != expected_repository:
                violations.append(
                    PolicyViolation(
                        code=PolicyViolationCode.CROSS_REPOSITORY_REF,
                        message="Analysis item references a user claim from another repository.",
                        field_path=reference_path,
                    )
                )

        return tuple(violations)


__all__ = ["PolicyViolation", "PolicyViolationCode", "RepositoryPolicyValidator"]
