from datetime import date
from typing import Annotated

from pydantic import StrictInt, StringConstraints

from app.schemas.common import (
    AnalysisDepth,
    ApiModel,
    EvidenceValueType,
    RequestEvidenceType,
    SnapshotHashAlgorithm,
)

type ClaimId = Annotated[str, StringConstraints(pattern=r"^claim_[0-9]{3,}$")]
type EvidenceId = Annotated[str, StringConstraints(pattern=r"^ev_[0-9]{3,}$")]


class CollectionWarning(ApiModel):
    code: str
    path: str | None
    message: str


class UserClaim(ApiModel):
    claim_id: ClaimId
    statement: str
    participation_level: str | None
    participation_started_on: date | None
    participation_ended_on: date | None
    related_evidence_refs: list[EvidenceId]


class Evidence(ApiModel):
    evidence_id: EvidenceId
    evidence_type: RequestEvidenceType
    analysis_depth: AnalysisDepth
    repository_id: str
    repository_full_name: str
    snapshot_hash_algorithm: SnapshotHashAlgorithm
    snapshot_sha: str
    fact_key: str
    value_type: EvidenceValueType
    value: str
    path: str | None
    start_line: StrictInt | None
    end_line: StrictInt | None
    commit_sha: str | None
    pull_request_number: StrictInt | None
    source_evidence_refs: list[EvidenceId]
    derived_from_level: AnalysisDepth | None


class RepositoryInput(ApiModel):
    repository_id: str
    repository_full_name: str
    default_branch: str | None
    snapshot_hash_algorithm: SnapshotHashAlgorithm
    snapshot_sha: str
    completed_evidence_levels: list[AnalysisDepth]
    collection_warnings: list[CollectionWarning]
    user_claims: list[UserClaim]
    evidence: list[Evidence]
