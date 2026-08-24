from app.core.exceptions import InputValidationError, InputViolation, InputViolationCode
from app.domain import (
    AnalysisDepth,
    EvidenceValueType,
    InternalEvidence,
    InternalEvidenceType,
    InternalPortfolioInput,
)

_DEPTH_RANK = {
    AnalysisDepth.P0: 0,
    AnalysisDepth.P1: 1,
    AnalysisDepth.P2: 2,
}
_DEPTH_PREFIX = {
    AnalysisDepth.P0: (AnalysisDepth.P0,),
    AnalysisDepth.P1: (AnalysisDepth.P0, AnalysisDepth.P1),
    AnalysisDepth.P2: (AnalysisDepth.P0, AnalysisDepth.P1, AnalysisDepth.P2),
}
_TYPE_DEPTH = {
    InternalEvidenceType.GITHUB_STATIC: AnalysisDepth.P0,
    InternalEvidenceType.GITHUB_ACTIVITY: AnalysisDepth.P1,
    InternalEvidenceType.CODE_EVIDENCE: AnalysisDepth.P2,
}


class AnalysisDepthValidator:
    """Validate requested, completed, and Evidence-specific analysis depths."""

    def validate(self, portfolio: InternalPortfolioInput) -> None:
        violations: list[InputViolation] = []
        requested_rank = _DEPTH_RANK[portfolio.requested_analysis_depth]

        for repository_index, repository in enumerate(portfolio.repositories):
            repository_path = f"repositories[{repository_index}]"
            if _DEPTH_RANK[repository.analysis_depth] > requested_rank:
                violations.append(
                    InputViolation(
                        InputViolationCode.DEPTH_EXCEEDS_REQUESTED,
                        "Repository analysis depth exceeds the requested maximum depth.",
                        f"{repository_path}.analysis_depth",
                    )
                )

            expected_levels = _DEPTH_PREFIX[repository.analysis_depth]
            if repository.completed_evidence_levels != expected_levels:
                violations.append(
                    InputViolation(
                        InputViolationCode.COMPLETED_LEVELS_INVALID,
                        "Completed Evidence levels must be the ordered depth prefix.",
                        f"{repository_path}.completed_evidence_levels",
                    )
                )

            has_algorithm = repository.snapshot_hash_algorithm is not None
            has_sha = repository.snapshot_sha is not None
            if not has_algorithm or not has_sha:
                violations.append(
                    InputViolation(
                        InputViolationCode.SNAPSHOT_REQUIRED,
                        "Repository snapshot algorithm and SHA are both required.",
                        f"{repository_path}.snapshot_sha",
                    )
                )

            completed_levels = set(repository.completed_evidence_levels)
            actual_levels = {evidence.analysis_depth for evidence in repository.evidence}
            if not completed_levels.issubset(actual_levels):
                violations.append(
                    InputViolation(
                        InputViolationCode.COMPLETED_LEVELS_INVALID,
                        "Every completed Evidence level requires at least one Evidence item.",
                        f"{repository_path}.completed_evidence_levels",
                    )
                )
            for evidence_index, evidence in enumerate(repository.evidence):
                evidence_path = f"{repository_path}.evidence[{evidence_index}]"
                if evidence.analysis_depth not in completed_levels:
                    violations.append(
                        InputViolation(
                            InputViolationCode.EVIDENCE_DEPTH_NOT_COMPLETED,
                            "Evidence depth is not included in the repository completed levels.",
                            f"{evidence_path}.analysis_depth",
                        )
                    )

                expected_depth = _TYPE_DEPTH.get(evidence.evidence_type)
                if expected_depth is not None and evidence.analysis_depth is not expected_depth:
                    violations.append(
                        InputViolation(
                            InputViolationCode.EVIDENCE_TYPE_DEPTH_MISMATCH,
                            "Evidence type does not match its required analysis depth.",
                            f"{evidence_path}.analysis_depth",
                        )
                    )

                if evidence.evidence_type is InternalEvidenceType.BACKEND_DERIVED:
                    derived_level = evidence.derived_from_level
                    if derived_level is None:
                        violations.append(
                            InputViolation(
                                InputViolationCode.EVIDENCE_TYPE_DEPTH_MISMATCH,
                                "BACKEND_DERIVED Evidence requires a derived depth.",
                                f"{evidence_path}.derived_from_level",
                            )
                        )
                    elif _DEPTH_RANK[derived_level] > _DEPTH_RANK[evidence.analysis_depth]:
                        violations.append(
                            InputViolation(
                                InputViolationCode.UPWARD_DEPTH_DERIVATION,
                                "Evidence must not derive from a deeper analysis level.",
                                f"{evidence_path}.derived_from_level",
                            )
                        )
                    elif derived_level is not evidence.analysis_depth:
                        violations.append(
                            InputViolation(
                                InputViolationCode.EVIDENCE_TYPE_DEPTH_MISMATCH,
                                "BACKEND_DERIVED depth must match its derived depth.",
                                f"{evidence_path}.derived_from_level",
                            )
                        )
                elif evidence.derived_from_level is not None:
                    violations.append(
                        InputViolation(
                            InputViolationCode.EVIDENCE_TYPE_DEPTH_MISMATCH,
                            "Only BACKEND_DERIVED Evidence may declare a derived depth.",
                            f"{evidence_path}.derived_from_level",
                        )
                    )

                if evidence.evidence_type is InternalEvidenceType.CODE_EVIDENCE:
                    violations.extend(self._validate_code_evidence(evidence, evidence_path))
                elif evidence.start_line is not None or evidence.end_line is not None:
                    violations.append(
                        InputViolation(
                            InputViolationCode.P2_METADATA_INVALID,
                            "Line range metadata is only allowed for CODE_EVIDENCE.",
                            f"{evidence_path}.start_line",
                        )
                    )

        if violations:
            raise InputValidationError(violations)

    @staticmethod
    def _validate_code_evidence(
        evidence: InternalEvidence,
        evidence_path: str,
    ) -> tuple[InputViolation, ...]:
        violations: list[InputViolation] = []

        def require(condition: bool, field: str, message: str) -> None:
            if not condition:
                violations.append(
                    InputViolation(
                        InputViolationCode.P2_METADATA_INVALID,
                        message,
                        f"{evidence_path}.{field}",
                    )
                )

        require(evidence.key == "CODE_SNIPPET", "key", "CODE_EVIDENCE requires CODE_SNIPPET key.")
        require(
            evidence.value_type is EvidenceValueType.STRING,
            "value_type",
            "CODE_EVIDENCE requires STRING value type.",
        )
        require(evidence.path is not None, "path", "CODE_EVIDENCE requires a repository path.")
        require(
            evidence.start_line is not None and evidence.start_line > 0,
            "start_line",
            "CODE_EVIDENCE requires a positive start line.",
        )
        require(
            evidence.end_line is not None
            and evidence.start_line is not None
            and evidence.end_line >= evidence.start_line,
            "end_line",
            "CODE_EVIDENCE requires a valid end line.",
        )
        require(
            evidence.commit_sha is not None,
            "commit_sha",
            "CODE_EVIDENCE requires a commit SHA.",
        )
        require(
            bool(evidence.source_evidence_refs),
            "source_evidence_refs",
            "CODE_EVIDENCE requires source Evidence references.",
        )
        return tuple(violations)


__all__ = ["AnalysisDepthValidator"]
