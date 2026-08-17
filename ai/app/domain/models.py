from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.domain.enums import (
    AnalysisDepth,
    AnalysisItemType,
    EvidenceConfidence,
    InternalEvidenceType,
    PortfolioStatementType,
    RecommendationPriority,
)

NonEmptyString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
EvidenceId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^ev_[0-9]{3,}$"),
]
ClaimId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^claim_[0-9]{3,}$"),
]
PositiveRepositoryId = Annotated[int, Field(gt=0)]


class InternalDomainModel(BaseModel):
    """Strict immutable base for models used only inside the AI pipeline."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class InternalEvidence(InternalDomainModel):
    """One P0 fact observed or deterministically derived by the backend."""

    evidence_id: EvidenceId
    repository_full_name: NonEmptyString
    evidence_type: InternalEvidenceType
    key: NonEmptyString
    summary: NonEmptyString
    source_paths: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def reject_duplicate_source_paths(self) -> Self:
        if len(self.source_paths) != len(set(self.source_paths)):
            raise ValueError("source_paths must not contain duplicates")
        return self


class InternalUserClaim(InternalDomainModel):
    """One untrusted statement supplied by the user about their role or work."""

    claim_id: ClaimId
    repository_full_name: NonEmptyString
    statement: NonEmptyString


class InternalRepositoryInput(InternalDomainModel):
    """Normalized repository data required by independent P0 analysis."""

    repository_id: PositiveRepositoryId
    repository_full_name: NonEmptyString
    description: NonEmptyString | None = None
    analysis_depth: AnalysisDepth
    evidence: tuple[InternalEvidence, ...] = Field(min_length=1)
    user_claims: tuple[InternalUserClaim, ...] = ()

    @model_validator(mode="after")
    def validate_repository_members(self) -> Self:
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence IDs must be unique within a repository input")

        claim_ids = [item.claim_id for item in self.user_claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim IDs must be unique within a repository input")

        mismatched_evidence = any(
            item.repository_full_name != self.repository_full_name for item in self.evidence
        )
        if mismatched_evidence:
            raise ValueError("evidence must belong to the parent repository")

        mismatched_claims = any(
            item.repository_full_name != self.repository_full_name for item in self.user_claims
        )
        if mismatched_claims:
            raise ValueError("user claims must belong to the parent repository")

        return self


class GroundedAnalysisItem(InternalDomainModel):
    """One generated analysis item whose grounding policy is type dependent."""

    item_type: AnalysisItemType
    content: NonEmptyString
    confidence: EvidenceConfidence
    evidence_refs: tuple[EvidenceId, ...] = ()
    claim_refs: tuple[ClaimId, ...] = ()
    priority: RecommendationPriority | None = None

    @model_validator(mode="after")
    def validate_grounding_policy(self) -> Self:
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("evidence_refs must not contain duplicates")
        if len(self.claim_refs) != len(set(self.claim_refs)):
            raise ValueError("claim_refs must not contain duplicates")

        requires_evidence = self.item_type in {
            AnalysisItemType.OBSERVATION,
            AnalysisItemType.RECOMMENDATION,
            AnalysisItemType.JOB_APPEAL,
        }
        if requires_evidence and not self.evidence_refs:
            raise ValueError(f"{self.item_type} requires at least one evidence ref")

        if (
            self.item_type is AnalysisItemType.INTERPRETATION
            and not self.evidence_refs
            and not self.claim_refs
        ):
            raise ValueError("INTERPRETATION requires an evidence or claim ref")

        if self.item_type is AnalysisItemType.RECOMMENDATION:
            if self.priority is None:
                raise ValueError("RECOMMENDATION requires a priority")
        elif self.priority is not None:
            raise ValueError("priority is only allowed for RECOMMENDATION items")

        return self


class RepositoryAnalysis(InternalDomainModel):
    """P0 coaching result generated for one repository."""

    repository_full_name: NonEmptyString
    summary: GroundedAnalysisItem
    observations: tuple[GroundedAnalysisItem, ...] = ()
    strengths: tuple[GroundedAnalysisItem, ...] = ()
    recommendations: tuple[GroundedAnalysisItem, ...] = ()
    limitations: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def validate_item_roles(self) -> Self:
        if self.summary.item_type is not AnalysisItemType.INTERPRETATION:
            raise ValueError("repository summary must be an INTERPRETATION")
        if any(item.item_type is not AnalysisItemType.OBSERVATION for item in self.observations):
            raise ValueError("observations must contain only OBSERVATION items")
        if any(item.item_type is not AnalysisItemType.INTERPRETATION for item in self.strengths):
            raise ValueError("strengths must contain only INTERPRETATION items")
        if any(
            item.item_type is not AnalysisItemType.RECOMMENDATION for item in self.recommendations
        ):
            raise ValueError("recommendations must contain only RECOMMENDATION items")
        return self


class RepresentativeProject(InternalDomainModel):
    """One evidence- or claim-grounded representative repository selection."""

    repository_full_name: NonEmptyString
    reason: NonEmptyString
    confidence: EvidenceConfidence
    evidence_refs: tuple[EvidenceId, ...] = ()
    claim_refs: tuple[ClaimId, ...] = ()

    @model_validator(mode="after")
    def require_grounding(self) -> Self:
        if not self.evidence_refs and not self.claim_refs:
            raise ValueError("representative project requires an evidence or claim ref")
        return self


class InterviewQuestion(InternalDomainModel):
    """One project-grounded interview question and answer direction."""

    repository_full_name: NonEmptyString
    question: NonEmptyString
    intent: NonEmptyString
    answer_guide: tuple[NonEmptyString, ...] = Field(min_length=1)
    follow_up_questions: tuple[NonEmptyString, ...] = ()
    evidence_refs: tuple[EvidenceId, ...] = ()
    claim_refs: tuple[ClaimId, ...] = ()

    @model_validator(mode="after")
    def require_grounding(self) -> Self:
        if not self.evidence_refs and not self.claim_refs:
            raise ValueError("interview question requires an evidence or claim ref")
        return self


class PortfolioStatement(InternalDomainModel):
    """One reusable statement grounded by evidence or an explicit user claim."""

    statement_type: PortfolioStatementType
    content: NonEmptyString
    evidence_refs: tuple[EvidenceId, ...] = ()
    claim_refs: tuple[ClaimId, ...] = ()

    @model_validator(mode="after")
    def require_grounding(self) -> Self:
        if not self.evidence_refs and not self.claim_refs:
            raise ValueError("portfolio statement requires an evidence or claim ref")
        return self


class PortfolioAnalysis(InternalDomainModel):
    """P0 portfolio result aggregated from one to five repository analyses."""

    overall_summary: GroundedAnalysisItem
    repository_analyses: tuple[RepositoryAnalysis, ...] = Field(
        min_length=1,
        max_length=5,
    )
    representative_projects: tuple[RepresentativeProject, ...] = Field(
        min_length=1,
        max_length=5,
    )
    job_appeal: tuple[GroundedAnalysisItem, ...] = ()
    recommendations: tuple[GroundedAnalysisItem, ...] = ()
    interview_questions: tuple[InterviewQuestion, ...] = ()
    portfolio_statements: tuple[PortfolioStatement, ...] = ()
    limitations: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def validate_portfolio_members(self) -> Self:
        if self.overall_summary.item_type is not AnalysisItemType.INTERPRETATION:
            raise ValueError("overall_summary must be an INTERPRETATION")

        repository_names = [analysis.repository_full_name for analysis in self.repository_analyses]
        if len(repository_names) != len(set(repository_names)):
            raise ValueError("repository analysis names must be unique")
        known_repositories = set(repository_names)

        representative_names = [
            project.repository_full_name for project in self.representative_projects
        ]
        if len(representative_names) != len(set(representative_names)):
            raise ValueError("representative project names must be unique")
        if not set(representative_names).issubset(known_repositories):
            raise ValueError("representative projects must reference analyzed repositories")

        if any(item.item_type is not AnalysisItemType.JOB_APPEAL for item in self.job_appeal):
            raise ValueError("job_appeal must contain only JOB_APPEAL items")
        if any(
            item.item_type is not AnalysisItemType.RECOMMENDATION for item in self.recommendations
        ):
            raise ValueError("recommendations must contain only RECOMMENDATION items")
        if any(
            question.repository_full_name not in known_repositories
            for question in self.interview_questions
        ):
            raise ValueError("interview questions must reference analyzed repositories")

        return self
