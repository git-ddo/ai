from collections.abc import Sequence

from app.core.exceptions import (
    InputValidationError,
    InputViolation,
    InputViolationCode,
)
from app.domain import (
    AnalysisDepth,
    InternalEvidence,
    InternalEvidenceType,
    InternalPortfolioInput,
    InternalRepositoryInput,
)


class EvidenceReferenceValidator:
    """Validate analysis-wide Evidence and UserClaim reference relationships."""

    def validate(self, portfolio: InternalPortfolioInput) -> None:
        violations: list[InputViolation] = []
        repositories = portfolio.repositories
        self._validate_global_identifiers(repositories, violations)

        evidence_owners: dict[str, tuple[int, int, str, InternalEvidence]] = {}
        for repository_index, repository in enumerate(repositories):
            for evidence_index, evidence in enumerate(repository.evidence):
                evidence_owners.setdefault(
                    evidence.evidence_id,
                    (
                        repository_index,
                        evidence_index,
                        repository.repository_full_name,
                        evidence,
                    ),
                )

        adjacency: dict[str, list[tuple[str, int]]] = {}
        for repository_index, repository in enumerate(repositories):
            repository_name = repository.repository_full_name
            for evidence_index, evidence in enumerate(repository.evidence):
                evidence_path = f"repositories[{repository_index}].evidence[{evidence_index}]"
                if evidence.repository_full_name != repository_name:
                    violations.append(
                        InputViolation(
                            InputViolationCode.REPOSITORY_OWNERSHIP_MISMATCH,
                            "Evidence does not belong to its parent repository.",
                            f"{evidence_path}.repository_full_name",
                        )
                    )

                valid_local_sources: list[InternalEvidence] = []
                for reference_index, source_ref in enumerate(evidence.source_evidence_refs):
                    reference_path = f"{evidence_path}.source_evidence_refs[{reference_index}]"
                    source = evidence_owners.get(source_ref)
                    if source is None:
                        violations.append(
                            InputViolation(
                                InputViolationCode.UNKNOWN_SOURCE_EVIDENCE_REF,
                                "Evidence references an unknown source Evidence ID.",
                                reference_path,
                            )
                        )
                        continue
                    if source_ref == evidence.evidence_id:
                        violations.append(
                            InputViolation(
                                InputViolationCode.REFERENCE_CYCLE,
                                "Evidence must not reference itself.",
                                reference_path,
                            )
                        )
                        continue

                    source_repository = source[2]
                    if source_repository != repository_name:
                        violations.append(
                            InputViolation(
                                InputViolationCode.CROSS_REPOSITORY_REF,
                                "Evidence source reference crosses a repository boundary.",
                                reference_path,
                            )
                        )
                        continue

                    valid_local_sources.append(source[3])
                    adjacency.setdefault(evidence.evidence_id, []).append(
                        (source_ref, reference_index)
                    )

                if evidence.evidence_type is InternalEvidenceType.CODE_EVIDENCE:
                    has_p1_source = any(
                        source.analysis_depth is AnalysisDepth.P1
                        and source.evidence_type
                        in {
                            InternalEvidenceType.GITHUB_ACTIVITY,
                            InternalEvidenceType.BACKEND_DERIVED,
                        }
                        for source in valid_local_sources
                    )
                    if not has_p1_source:
                        violations.append(
                            InputViolation(
                                InputViolationCode.P2_SOURCE_INVALID,
                                "CODE_EVIDENCE requires a local P1 source Evidence reference.",
                                f"{evidence_path}.source_evidence_refs",
                            )
                        )

            for claim_index, claim in enumerate(repository.user_claims):
                claim_path = f"repositories[{repository_index}].user_claims[{claim_index}]"
                if claim.repository_full_name != repository_name:
                    violations.append(
                        InputViolation(
                            InputViolationCode.REPOSITORY_OWNERSHIP_MISMATCH,
                            "UserClaim does not belong to its parent repository.",
                            f"{claim_path}.repository_full_name",
                        )
                    )

                for reference_index, evidence_ref in enumerate(claim.related_evidence_refs):
                    reference_path = f"{claim_path}.related_evidence_refs[{reference_index}]"
                    source = evidence_owners.get(evidence_ref)
                    if source is None:
                        violations.append(
                            InputViolation(
                                InputViolationCode.UNKNOWN_RELATED_EVIDENCE_REF,
                                "UserClaim references an unknown Evidence ID.",
                                reference_path,
                            )
                        )
                    elif source[2] != repository_name:
                        violations.append(
                            InputViolation(
                                InputViolationCode.CROSS_REPOSITORY_REF,
                                "UserClaim Evidence reference crosses a repository boundary.",
                                reference_path,
                            )
                        )

        violations.extend(self._find_reference_cycles(adjacency, evidence_owners))
        if violations:
            raise InputValidationError(violations)

    @staticmethod
    def _validate_global_identifiers(
        repositories: Sequence[InternalRepositoryInput],
        violations: list[InputViolation],
    ) -> None:
        seen_repository_ids: set[str] = set()
        seen_repository_names: set[str] = set()
        seen_evidence_ids: set[str] = set()
        seen_claim_ids: set[str] = set()

        for repository_index, repository in enumerate(repositories):
            repository_id = repository.repository_id
            repository_name = repository.repository_full_name
            if repository_id in seen_repository_ids:
                violations.append(
                    InputViolation(
                        InputViolationCode.DUPLICATE_REPOSITORY_ID,
                        "Repository ID must be unique across the analysis.",
                        f"repositories[{repository_index}].repository_id",
                    )
                )
            seen_repository_ids.add(repository_id)
            if repository_name in seen_repository_names:
                violations.append(
                    InputViolation(
                        InputViolationCode.DUPLICATE_REPOSITORY_NAME,
                        "Repository full name must be unique across the analysis.",
                        f"repositories[{repository_index}].repository_full_name",
                    )
                )
            seen_repository_names.add(repository_name)

            for evidence_index, evidence in enumerate(repository.evidence):
                if evidence.evidence_id in seen_evidence_ids:
                    violations.append(
                        InputViolation(
                            InputViolationCode.DUPLICATE_EVIDENCE_ID,
                            "Evidence ID must be unique across the analysis.",
                            f"repositories[{repository_index}].evidence[{evidence_index}].evidence_id",
                        )
                    )
                seen_evidence_ids.add(evidence.evidence_id)

            for claim_index, claim in enumerate(repository.user_claims):
                if claim.claim_id in seen_claim_ids:
                    violations.append(
                        InputViolation(
                            InputViolationCode.DUPLICATE_CLAIM_ID,
                            "Claim ID must be unique across the analysis.",
                            f"repositories[{repository_index}].user_claims[{claim_index}].claim_id",
                        )
                    )
                seen_claim_ids.add(claim.claim_id)

    @staticmethod
    def _find_reference_cycles(
        adjacency: dict[str, list[tuple[str, int]]],
        evidence_owners: dict[str, tuple[int, int, str, InternalEvidence]],
    ) -> tuple[InputViolation, ...]:
        states: dict[str, int] = {}
        violations: list[InputViolation] = []

        def visit(evidence_id: str) -> None:
            states[evidence_id] = 1
            for source_ref, reference_index in adjacency.get(evidence_id, ()):
                state = states.get(source_ref, 0)
                if state == 0:
                    visit(source_ref)
                elif state == 1:
                    owner = evidence_owners[evidence_id]
                    violations.append(
                        InputViolation(
                            InputViolationCode.REFERENCE_CYCLE,
                            "Evidence source references must not form a cycle.",
                            (
                                f"repositories[{owner[0]}].evidence[{owner[1]}]"
                                f".source_evidence_refs[{reference_index}]"
                            ),
                        )
                    )
            states[evidence_id] = 2

        for evidence_id in evidence_owners:
            if states.get(evidence_id, 0) == 0:
                visit(evidence_id)
        return tuple(violations)


__all__ = ["EvidenceReferenceValidator"]
