from pathlib import PurePosixPath

from pydantic import ValidationError

from app.core.exceptions import (
    RequestMappingError,
    UnsupportedAnalysisCombinationError,
)
from app.domain import (
    AnalysisDepth as InternalAnalysisDepth,
)
from app.domain import (
    EvidenceValueType as InternalEvidenceValueType,
)
from app.domain import (
    InternalEvidence,
    InternalEvidenceType,
    InternalPortfolioInput,
    InternalRepositoryInput,
    InternalUserClaim,
)
from app.domain import (
    SnapshotHashAlgorithm as InternalSnapshotHashAlgorithm,
)
from app.schemas.common import (
    AnalysisDepth as WireAnalysisDepth,
)
from app.schemas.common import (
    RequestAnalysisPurpose,
    RequestEvidenceType,
    TargetCareerLevel,
    TargetJob,
)
from app.schemas.repository import Evidence, RepositoryInput, UserClaim
from app.schemas.request import PortfolioReportRequest

_DEPTH_PREFIXES: dict[WireAnalysisDepth, tuple[WireAnalysisDepth, ...]] = {
    WireAnalysisDepth.P0: (WireAnalysisDepth.P0,),
    WireAnalysisDepth.P1: (WireAnalysisDepth.P0, WireAnalysisDepth.P1),
    WireAnalysisDepth.P2: (
        WireAnalysisDepth.P0,
        WireAnalysisDepth.P1,
        WireAnalysisDepth.P2,
    ),
}
_DEPTH_RANK = {
    WireAnalysisDepth.P0: 0,
    WireAnalysisDepth.P1: 1,
    WireAnalysisDepth.P2: 2,
}
_P1_FILE_LIST_FACT_KEYS = frozenset({"CHANGED_FILES", "PULL_REQUEST"})
_P1_FILE_LIST_MARKER = "files:"


class RequestWireMapper:
    """Convert the Backend request wire contract into internal analysis input."""

    def to_internal(self, request: PortfolioReportRequest) -> InternalPortfolioInput:
        self._validate_supported_combination(request)
        requested_depth = self._map_depth(request.requested_analysis_depth)

        repositories = tuple(
            self._map_repository(repository, request.requested_analysis_depth, repository_index)
            for repository_index, repository in enumerate(request.repositories)
        )
        try:
            return InternalPortfolioInput(
                requested_analysis_depth=requested_depth,
                repositories=repositories,
            )
        except ValidationError as exc:
            raise RequestMappingError(
                "Wire request could not form a valid internal portfolio input."
            ) from exc

    @staticmethod
    def _validate_supported_combination(request: PortfolioReportRequest) -> None:
        if (
            request.target_job is not TargetJob.BACKEND
            or request.target_career_level is not TargetCareerLevel.ENTRY
            or request.analysis_purpose is not RequestAnalysisPurpose.PORTFOLIO_ANALYSIS
        ):
            raise UnsupportedAnalysisCombinationError(
                "The requested analysis combination is not supported."
            )

    def _map_repository(
        self,
        repository: RepositoryInput,
        requested_depth: WireAnalysisDepth,
        repository_index: int,
    ) -> InternalRepositoryInput:
        actual_wire_depth = self._validate_completed_levels(
            repository.completed_evidence_levels,
            requested_depth,
            repository_index,
        )
        evidence = tuple(
            self._map_evidence(repository, item, repository_index, evidence_index)
            for evidence_index, item in enumerate(repository.evidence)
        )
        claims = tuple(
            self._map_claim(repository, item, repository_index, claim_index)
            for claim_index, item in enumerate(repository.user_claims)
        )

        try:
            return InternalRepositoryInput(
                repository_id=repository.repository_id,
                repository_full_name=repository.repository_full_name,
                description=None,
                analysis_depth=self._map_depth(actual_wire_depth),
                completed_evidence_levels=tuple(
                    self._map_depth(level) for level in repository.completed_evidence_levels
                ),
                snapshot_hash_algorithm=InternalSnapshotHashAlgorithm(
                    repository.snapshot_hash_algorithm.value
                ),
                snapshot_sha=repository.snapshot_sha,
                evidence=evidence,
                user_claims=claims,
            )
        except ValidationError as exc:
            raise RequestMappingError(
                f"Repository mapping failed at repositories[{repository_index}]."
            ) from exc

    @staticmethod
    def _validate_completed_levels(
        completed_levels: list[WireAnalysisDepth],
        requested_depth: WireAnalysisDepth,
        repository_index: int,
    ) -> WireAnalysisDepth:
        if not completed_levels:
            raise RequestMappingError(
                f"Completed evidence levels are empty at repositories[{repository_index}]."
            )

        actual_depth = completed_levels[-1]
        if tuple(completed_levels) != _DEPTH_PREFIXES[actual_depth]:
            raise RequestMappingError(
                f"Completed evidence levels are invalid at repositories[{repository_index}]."
            )
        if _DEPTH_RANK[actual_depth] > _DEPTH_RANK[requested_depth]:
            raise RequestMappingError(
                f"Repository depth exceeds the request at repositories[{repository_index}]."
            )
        return actual_depth

    def _map_evidence(
        self,
        repository: RepositoryInput,
        evidence: Evidence,
        repository_index: int,
        evidence_index: int,
    ) -> InternalEvidence:
        evidence_path = f"repositories[{repository_index}].evidence[{evidence_index}]"
        self._validate_evidence_ownership(repository, evidence, evidence_path)
        source_paths = self._map_source_paths(evidence)

        try:
            return InternalEvidence(
                evidence_id=evidence.evidence_id,
                repository_full_name=evidence.repository_full_name,
                evidence_type=InternalEvidenceType(evidence.evidence_type.value),
                analysis_depth=self._map_depth(evidence.analysis_depth),
                key=evidence.fact_key,
                summary=evidence.value,
                value_type=InternalEvidenceValueType(evidence.value_type.value),
                source_paths=source_paths,
                technology_names=(),
                path=evidence.path,
                start_line=evidence.start_line,
                end_line=evidence.end_line,
                commit_sha=evidence.commit_sha,
                pull_request_number=evidence.pull_request_number,
                source_evidence_refs=tuple(evidence.source_evidence_refs),
                derived_from_level=(
                    self._map_depth(evidence.derived_from_level)
                    if evidence.derived_from_level is not None
                    else None
                ),
            )
        except ValidationError as exc:
            raise RequestMappingError(f"Evidence mapping failed at {evidence_path}.") from exc

    @staticmethod
    def _map_source_paths(evidence: Evidence) -> tuple[str, ...]:
        paths: list[str] = []
        if evidence.path is not None:
            paths.append(evidence.path)

        if (
            evidence.evidence_type is RequestEvidenceType.GITHUB_ACTIVITY
            and evidence.fact_key in _P1_FILE_LIST_FACT_KEYS
        ):
            paths.extend(_extract_p1_file_list_paths(evidence.value))

        return tuple(dict.fromkeys(paths))

    @staticmethod
    def _validate_evidence_ownership(
        repository: RepositoryInput,
        evidence: Evidence,
        evidence_path: str,
    ) -> None:
        checks = (
            (evidence.repository_id == repository.repository_id, "repository_id"),
            (
                evidence.repository_full_name == repository.repository_full_name,
                "repository_full_name",
            ),
            (
                evidence.snapshot_hash_algorithm == repository.snapshot_hash_algorithm,
                "snapshot_hash_algorithm",
            ),
            (evidence.snapshot_sha == repository.snapshot_sha, "snapshot_sha"),
        )
        for matches, field_name in checks:
            if not matches:
                raise RequestMappingError(
                    f"Evidence ownership mismatch at {evidence_path}.{field_name}."
                )

    @staticmethod
    def _map_claim(
        repository: RepositoryInput,
        claim: UserClaim,
        repository_index: int,
        claim_index: int,
    ) -> InternalUserClaim:
        claim_path = f"repositories[{repository_index}].user_claims[{claim_index}]"
        try:
            return InternalUserClaim(
                claim_id=claim.claim_id,
                repository_full_name=repository.repository_full_name,
                statement=claim.statement,
                related_evidence_refs=tuple(claim.related_evidence_refs),
            )
        except ValidationError as exc:
            raise RequestMappingError(f"UserClaim mapping failed at {claim_path}.") from exc

    @staticmethod
    def _map_depth(depth: WireAnalysisDepth) -> InternalAnalysisDepth:
        return InternalAnalysisDepth(depth.value)


def _extract_p1_file_list_paths(value: str) -> tuple[str, ...]:
    lines = value.splitlines()
    try:
        marker_index = lines.index(_P1_FILE_LIST_MARKER)
    except ValueError:
        return ()

    paths: list[str] = []
    for line in lines[marker_index + 1 :]:
        if not line:
            continue
        fields = line.split("\t")
        if len(fields) != 3:
            continue
        _status, path, _change_count = fields
        if _is_safe_repository_path(path):
            paths.append(path)
    return tuple(dict.fromkeys(paths))


def _is_safe_repository_path(path: str) -> bool:
    if not path or path != path.strip() or "\\" in path or "\x00" in path:
        return False
    candidate = PurePosixPath(path)
    return not candidate.is_absolute() and all(
        part not in {"", ".", ".."} for part in candidate.parts
    )


__all__ = ["RequestWireMapper"]
