from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.domain.enums import (
    AnalysisDepth,
    AnalysisItemType,
    EvidenceConfidence,
    InternalEvidenceType,
    InternalGenerationStage,
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
    technology_names: tuple[NonEmptyString, ...] = ()

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
    """Validated repository data awaiting canonical P0 normalization."""

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


class InternalPortfolioInput(InternalDomainModel):
    """One to five repository inputs sharing analysis-wide identifier scopes."""

    repositories: tuple[InternalRepositoryInput, ...] = Field(
        min_length=1,
        max_length=5,
    )

    @model_validator(mode="after")
    def validate_analysis_wide_identifiers(self) -> Self:
        repository_ids = [repository.repository_id for repository in self.repositories]
        if len(repository_ids) != len(set(repository_ids)):
            raise ValueError("duplicate repository ID")

        repository_names = [repository.repository_full_name for repository in self.repositories]
        if len(repository_names) != len(set(repository_names)):
            raise ValueError("duplicate repository full name")

        evidence_ids = [
            evidence.evidence_id
            for repository in self.repositories
            for evidence in repository.evidence
        ]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("duplicate evidence ID across repositories")

        claim_ids = [
            claim.claim_id for repository in self.repositories for claim in repository.user_claims
        ]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("duplicate claim ID across repositories")

        return self


class NormalizedRepositoryContext(InternalDomainModel):
    """Canonical repository context consumed by prompt and analysis services."""

    repository_id: PositiveRepositoryId
    repository_full_name: NonEmptyString
    description: NonEmptyString | None = None
    analysis_depth: AnalysisDepth
    evidence: tuple[InternalEvidence, ...] = Field(min_length=1)
    user_claims: tuple[InternalUserClaim, ...] = ()
    technology_names: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def validate_normalized_members(self) -> Self:
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence IDs must be unique within a normalized context")

        claim_ids = [item.claim_id for item in self.user_claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim IDs must be unique within a normalized context")

        if any(item.repository_full_name != self.repository_full_name for item in self.evidence):
            raise ValueError("evidence must belong to the normalized repository")
        if any(item.repository_full_name != self.repository_full_name for item in self.user_claims):
            raise ValueError("user claims must belong to the normalized repository")

        if len(self.technology_names) != len(set(self.technology_names)):
            raise ValueError("normalized technology names must be unique")
        if any(
            len(item.technology_names) != len(set(item.technology_names)) for item in self.evidence
        ):
            raise ValueError("evidence technology names must be normalized and unique")

        evidence_technologies = {
            technology for item in self.evidence for technology in item.technology_names
        }
        if set(self.technology_names) != evidence_technologies:
            raise ValueError(
                "context technology names must match the normalized evidence technologies"
            )

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


class InterviewQuestionBatch(InternalDomainModel):
    """Structured-output wrapper for questions about exactly one repository."""

    questions: tuple[InterviewQuestion, ...] = Field(
        min_length=1,
        max_length=10,
    )

    @model_validator(mode="after")
    def validate_question_scope(self) -> Self:
        repository_names = {question.repository_full_name for question in self.questions}
        if len(repository_names) != 1:
            raise ValueError("interview question batch must reference one repository")

        question_texts = [question.question.casefold() for question in self.questions]
        if len(question_texts) != len(set(question_texts)):
            raise ValueError("interview questions must be unique")

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


class InternalGenerationRecord(InternalDomainModel):
    """Provider-neutral execution metadata for one internal generation stage."""

    stage: InternalGenerationStage
    repository_full_name: NonEmptyString | None = None
    duration_ms: int = Field(ge=0)
    attempt_count: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_repository_scope(self) -> Self:
        repository_scoped_stages = {
            InternalGenerationStage.REPOSITORY,
            InternalGenerationStage.INTERVIEW,
        }
        if self.stage in repository_scoped_stages and self.repository_full_name is None:
            raise ValueError(f"{self.stage} generation requires a repository full name")
        if (
            self.stage is InternalGenerationStage.PORTFOLIO
            and self.repository_full_name is not None
        ):
            raise ValueError("PORTFOLIO generation must not reference a repository")
        return self


class InternalPortfolioReport(InternalDomainModel):
    """Complete internal P0 result and provider-neutral generation records."""

    analysis: PortfolioAnalysis
    generation_records: tuple[InternalGenerationRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_generation_records(self) -> Self:
        analyzed_repositories = {
            repository.repository_full_name for repository in self.analysis.repository_analyses
        }

        portfolio_records = [
            record
            for record in self.generation_records
            if record.stage is InternalGenerationStage.PORTFOLIO
        ]
        if len(portfolio_records) != 1:
            raise ValueError("internal report requires exactly one PORTFOLIO generation record")

        repository_record_names = [
            record.repository_full_name
            for record in self.generation_records
            if record.stage is InternalGenerationStage.REPOSITORY
        ]
        if len(repository_record_names) != len(set(repository_record_names)):
            raise ValueError("duplicate REPOSITORY generation record")
        if set(repository_record_names) != analyzed_repositories:
            raise ValueError("REPOSITORY generation records must match all analyzed repositories")

        interview_record_names = [
            record.repository_full_name
            for record in self.generation_records
            if record.stage is InternalGenerationStage.INTERVIEW
        ]
        if len(interview_record_names) != len(set(interview_record_names)):
            raise ValueError("duplicate INTERVIEW generation record")

        interview_question_repositories = {
            question.repository_full_name for question in self.analysis.interview_questions
        }
        if set(interview_record_names) != interview_question_repositories:
            raise ValueError(
                "INTERVIEW generation records must match repositories with interview questions"
            )

        return self
