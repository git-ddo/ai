import re
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AfterValidator, Field, StringConstraints, model_validator

from app.schemas.common import (
    AnalysisDepth,
    ApiModel,
    Confidence,
    FindingCategory,
    FindingSeverity,
    LimitationCode,
    SnapshotHashAlgorithm,
)

type WireNonEmptyString = Annotated[str, StringConstraints(min_length=1)]
type FindingId = Annotated[str, StringConstraints(pattern=r"^find_[0-9]{3,}$")]
type EvidenceRef = Annotated[str, StringConstraints(pattern=r"^ev_[0-9]{3,}$")]
type ClaimRef = Annotated[str, StringConstraints(pattern=r"^claim_[0-9]{3,}$")]

_REPOSITORY_PATH_PATTERN = re.compile(r"^(?!/)(?!.*\.\.).+$")


def _validate_repository_path(value: str) -> str:
    if _REPOSITORY_PATH_PATTERN.fullmatch(value) is None:
        raise ValueError("file path must be a non-empty repository-relative path without '..'")
    return value


type RepositoryPath = Annotated[
    str,
    StringConstraints(min_length=1),
    AfterValidator(_validate_repository_path),
]


class Finding(ApiModel):
    finding_id: FindingId
    category: FindingCategory
    severity: FindingSeverity
    confidence: Confidence
    title: WireNonEmptyString
    detail: WireNonEmptyString
    evidence_refs: list[EvidenceRef]
    claim_refs: list[ClaimRef]
    file_paths: list[RepositoryPath]


class RepositoryReport(ApiModel):
    repository_id: str
    repository_full_name: str
    snapshot_hash_algorithm: SnapshotHashAlgorithm
    snapshot_sha: str
    findings: list[Finding]


class CoachingItem(ApiModel):
    text: WireNonEmptyString
    confidence: Confidence
    evidence_refs: Annotated[list[EvidenceRef], Field(min_length=1)]


class JobAppeal(ApiModel):
    text: WireNonEmptyString
    confidence: Confidence
    evidence_refs: Annotated[list[EvidenceRef], Field(min_length=1)]


class PortfolioStatement(ApiModel):
    text: WireNonEmptyString
    confidence: Confidence
    evidence_refs: list[EvidenceRef]
    claim_refs: list[ClaimRef]

    @model_validator(mode="after")
    def validate_reference_presence(self) -> Self:
        if not self.evidence_refs and not self.claim_refs:
            raise ValueError("portfolio statement requires an evidence or claim reference")
        return self


class InterviewQuestion(ApiModel):
    question: WireNonEmptyString
    intent: WireNonEmptyString
    answer_guide: Annotated[list[WireNonEmptyString], Field(min_length=1)]
    follow_up_questions: list[WireNonEmptyString]
    confidence: Confidence
    evidence_refs: list[EvidenceRef]
    claim_refs: list[ClaimRef]

    @model_validator(mode="after")
    def validate_reference_presence(self) -> Self:
        if not self.evidence_refs and not self.claim_refs:
            raise ValueError("interview question requires an evidence or claim reference")
        return self


class Coaching(ApiModel):
    strengths: list[CoachingItem]
    gaps: list[CoachingItem]
    next_actions: list[CoachingItem]
    job_appeal: JobAppeal
    portfolio_statements: list[PortfolioStatement]
    interview_questions: list[InterviewQuestion]


class Limitation(ApiModel):
    code: LimitationCode
    message: WireNonEmptyString


class PortfolioReportResponse(ApiModel):
    """Backend analysis response v1.1 wire contract."""

    schema_version: Literal["1.1"]
    analysis_id: UUID
    evaluator_version: WireNonEmptyString
    requested_analysis_depth: AnalysisDepth
    used_evidence_levels: Annotated[list[AnalysisDepth], Field(min_length=1)]
    summary: WireNonEmptyString
    repositories: Annotated[list[RepositoryReport], Field(min_length=1, max_length=5)]
    coaching: Coaching
    limitations: list[Limitation]
