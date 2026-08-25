import re
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.domain.enums import (
    AnalysisDepth,
    AnalysisItemType,
    EvidenceConfidence,
    EvidenceValueType,
    InternalEvidenceType,
    InternalGenerationStage,
    PortfolioStatementType,
    RecommendationPriority,
    SnapshotHashAlgorithm,
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
RepositoryId = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, pattern=r"^[1-9][0-9]*$"),
]
PositiveLineNumber = Annotated[int, Field(strict=True, gt=0)]
PositivePullRequestNumber = Annotated[int, Field(strict=True, gt=0)]

_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")

_COMPLETED_DEPTH_PREFIXES: dict[AnalysisDepth, tuple[AnalysisDepth, ...]] = {
    AnalysisDepth.P0: (AnalysisDepth.P0,),
    AnalysisDepth.P1: (AnalysisDepth.P0, AnalysisDepth.P1),
    AnalysisDepth.P2: (AnalysisDepth.P0, AnalysisDepth.P1, AnalysisDepth.P2),
}


class InternalDomainModel(BaseModel):
    """Strict immutable base for models used only inside the AI pipeline."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class InternalEvidence(InternalDomainModel):
    """One backend-observed or derived fact available to the AI pipeline.

    Backend ``factKey`` maps to ``key``, ``value`` maps to ``summary``, and
    ``sourceEvidenceRefs`` maps to ``source_evidence_refs`` at the future wire boundary.
    """

    evidence_id: EvidenceId
    repository_full_name: NonEmptyString
    evidence_type: InternalEvidenceType
    analysis_depth: AnalysisDepth = AnalysisDepth.P0
    key: NonEmptyString
    summary: NonEmptyString
    value_type: EvidenceValueType = EvidenceValueType.STRING
    source_paths: tuple[NonEmptyString, ...] = ()
    technology_names: tuple[NonEmptyString, ...] = ()
    path: NonEmptyString | None = None
    start_line: PositiveLineNumber | None = None
    end_line: PositiveLineNumber | None = None
    commit_sha: NonEmptyString | None = None
    pull_request_number: PositivePullRequestNumber | None = None
    source_evidence_refs: tuple[EvidenceId, ...] = ()
    derived_from_level: AnalysisDepth | None = None

    @model_validator(mode="after")
    def validate_evidence_semantics(self) -> Self:
        if len(self.source_paths) != len(set(self.source_paths)):
            raise ValueError("source_paths must not contain duplicates")

        if len(self.source_evidence_refs) != len(set(self.source_evidence_refs)):
            raise ValueError("source_evidence_refs must not contain duplicates")
        if self.evidence_id in self.source_evidence_refs:
            raise ValueError("evidence must not reference itself as a source")

        required_depth = {
            InternalEvidenceType.GITHUB_STATIC: AnalysisDepth.P0,
            InternalEvidenceType.GITHUB_ACTIVITY: AnalysisDepth.P1,
            InternalEvidenceType.CODE_EVIDENCE: AnalysisDepth.P2,
        }.get(self.evidence_type)
        if required_depth is not None and self.analysis_depth is not required_depth:
            raise ValueError(
                f"{self.evidence_type} evidence requires analysis depth {required_depth}"
            )

        if (self.start_line is None) is not (self.end_line is None):
            raise ValueError("start_line and end_line must be provided together")
        if (
            self.start_line is not None
            and self.end_line is not None
            and self.start_line > self.end_line
        ):
            raise ValueError("start_line must not be greater than end_line")

        if self.evidence_type is InternalEvidenceType.CODE_EVIDENCE:
            missing_fields: list[str] = []
            if self.path is None:
                missing_fields.append("path")
            if self.start_line is None:
                missing_fields.append("start_line")
            if self.end_line is None:
                missing_fields.append("end_line")
            if self.commit_sha is None:
                missing_fields.append("commit_sha")
            if not self.source_evidence_refs:
                missing_fields.append("source_evidence_refs")
            if missing_fields:
                raise ValueError("CODE_EVIDENCE requires " + ", ".join(missing_fields))
            if self.value_type is not EvidenceValueType.STRING:
                raise ValueError("CODE_EVIDENCE requires STRING value_type")

        if self.evidence_type is InternalEvidenceType.BACKEND_DERIVED:
            if self.derived_from_level is None:
                raise ValueError("BACKEND_DERIVED evidence requires derived_from_level")
            if self.derived_from_level is not self.analysis_depth:
                raise ValueError("BACKEND_DERIVED derived_from_level must match analysis_depth")
        elif self.derived_from_level is not None:
            raise ValueError("derived_from_level is only allowed for BACKEND_DERIVED evidence")

        return self


class InternalUserClaim(InternalDomainModel):
    """One untrusted statement supplied by the user about their role or work."""

    claim_id: ClaimId
    repository_full_name: NonEmptyString
    statement: NonEmptyString
    related_evidence_refs: tuple[EvidenceId, ...] = ()

    @model_validator(mode="after")
    def reject_duplicate_evidence_refs(self) -> Self:
        if len(self.related_evidence_refs) != len(set(self.related_evidence_refs)):
            raise ValueError("related_evidence_refs must not contain duplicates")
        return self


class InternalRepositoryInput(InternalDomainModel):
    """Validated repository evidence awaiting depth-specific normalization."""

    repository_id: RepositoryId
    repository_full_name: NonEmptyString
    description: NonEmptyString | None = None
    analysis_depth: AnalysisDepth
    completed_evidence_levels: tuple[AnalysisDepth, ...] = (AnalysisDepth.P0,)
    snapshot_hash_algorithm: SnapshotHashAlgorithm | None = None
    snapshot_sha: NonEmptyString | None = None
    evidence: tuple[InternalEvidence, ...] = Field(min_length=1)
    user_claims: tuple[InternalUserClaim, ...] = ()

    @model_validator(mode="after")
    def validate_repository_members(self) -> Self:
        expected_levels = _COMPLETED_DEPTH_PREFIXES[self.analysis_depth]
        if self.completed_evidence_levels != expected_levels:
            raise ValueError(
                "completed_evidence_levels must be the ordered P0-to-analysis_depth prefix"
            )

        has_snapshot_algorithm = self.snapshot_hash_algorithm is not None
        has_snapshot_sha = self.snapshot_sha is not None
        if has_snapshot_algorithm != has_snapshot_sha:
            raise ValueError("snapshot_hash_algorithm and snapshot_sha must be provided together")
        if self.analysis_depth is not AnalysisDepth.P0 and not has_snapshot_sha:
            raise ValueError("P1/P2 repository input requires snapshot metadata")

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

        completed_levels = set(self.completed_evidence_levels)
        if any(item.analysis_depth not in completed_levels for item in self.evidence):
            raise ValueError("evidence depth must be included in completed_evidence_levels")

        return self


class InternalPortfolioInput(InternalDomainModel):
    """One to five repository inputs sharing analysis-wide identifier scopes."""

    requested_analysis_depth: AnalysisDepth
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

    repository_id: RepositoryId
    repository_full_name: NonEmptyString
    description: NonEmptyString | None = None
    analysis_depth: AnalysisDepth
    completed_evidence_levels: tuple[AnalysisDepth, ...] = (AnalysisDepth.P0,)
    snapshot_hash_algorithm: SnapshotHashAlgorithm | None = None
    snapshot_sha: NonEmptyString | None = None
    evidence: tuple[InternalEvidence, ...] = Field(min_length=1)
    user_claims: tuple[InternalUserClaim, ...] = ()
    technology_names: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def validate_normalized_members(self) -> Self:
        expected_levels = _COMPLETED_DEPTH_PREFIXES[self.analysis_depth]
        if self.completed_evidence_levels != expected_levels:
            raise ValueError(
                "completed_evidence_levels must be the ordered P0-to-analysis_depth prefix"
            )

        has_snapshot_algorithm = self.snapshot_hash_algorithm is not None
        has_snapshot_sha = self.snapshot_sha is not None
        if has_snapshot_algorithm != has_snapshot_sha:
            raise ValueError("snapshot_hash_algorithm and snapshot_sha must be provided together")
        if self.analysis_depth is not AnalysisDepth.P0 and not has_snapshot_sha:
            raise ValueError("P1/P2 normalized context requires snapshot metadata")

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

        completed_levels = set(self.completed_evidence_levels)
        if any(item.analysis_depth not in completed_levels for item in self.evidence):
            raise ValueError("evidence depth must be included in completed_evidence_levels")

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
    criterion_keys: tuple[NonEmptyString, ...] = Field(min_length=1)
    technology_names: tuple[NonEmptyString, ...] = ()
    file_paths: tuple[NonEmptyString, ...] = ()
    priority: RecommendationPriority | None = None

    @model_validator(mode="after")
    def validate_grounding_policy(self) -> Self:
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("evidence_refs must not contain duplicates")
        if len(self.claim_refs) != len(set(self.claim_refs)):
            raise ValueError("claim_refs must not contain duplicates")
        if len(self.criterion_keys) != len(set(self.criterion_keys)):
            raise ValueError("criterion_keys must not contain duplicates")
        if len({name.casefold() for name in self.technology_names}) != len(self.technology_names):
            raise ValueError("technology_names must not contain duplicates")
        if len(self.file_paths) != len(set(self.file_paths)):
            raise ValueError("file_paths must not contain duplicates")
        if any(not _is_repository_relative_path(path) for path in self.file_paths):
            raise ValueError("file_paths must contain only safe repository-relative paths")

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


def _is_repository_relative_path(path: str) -> bool:
    if "\x00" in path or path.startswith(("/", "\\")) or _WINDOWS_ABSOLUTE_PATH.match(path):
        return False
    return all(part != ".." for part in re.split(r"[\\/]", path))


def _validate_grounding_metadata(
    *,
    evidence_refs: tuple[str, ...],
    claim_refs: tuple[str, ...],
    criterion_keys: tuple[str, ...],
    technology_names: tuple[str, ...],
    file_paths: tuple[str, ...],
) -> None:
    if len(evidence_refs) != len(set(evidence_refs)):
        raise ValueError("evidence_refs must not contain duplicates")
    if len(claim_refs) != len(set(claim_refs)):
        raise ValueError("claim_refs must not contain duplicates")
    if len(criterion_keys) != len(set(criterion_keys)):
        raise ValueError("criterion_keys must not contain duplicates")
    if len({name.casefold() for name in technology_names}) != len(technology_names):
        raise ValueError("technology_names must not contain duplicates")
    if len(file_paths) != len(set(file_paths)):
        raise ValueError("file_paths must not contain duplicates")
    if any(not _is_repository_relative_path(path) for path in file_paths):
        raise ValueError("file_paths must contain only safe repository-relative paths")


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
    criterion_keys: tuple[NonEmptyString, ...] = Field(min_length=1)
    technology_names: tuple[NonEmptyString, ...] = ()
    file_paths: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def validate_question_grounding(self) -> Self:
        if not self.evidence_refs and not self.claim_refs:
            raise ValueError("interview question requires an evidence or claim ref")

        _validate_grounding_metadata(
            evidence_refs=self.evidence_refs,
            claim_refs=self.claim_refs,
            criterion_keys=self.criterion_keys,
            technology_names=self.technology_names,
            file_paths=self.file_paths,
        )

        normalized_follow_ups = [question.casefold() for question in self.follow_up_questions]
        if len(normalized_follow_ups) != len(set(normalized_follow_ups)):
            raise ValueError("follow_up_questions must not contain duplicates")
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
    criterion_keys: tuple[NonEmptyString, ...] = Field(min_length=1)
    technology_names: tuple[NonEmptyString, ...] = ()
    file_paths: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def validate_statement_grounding(self) -> Self:
        if not self.evidence_refs and not self.claim_refs:
            raise ValueError("portfolio statement requires an evidence or claim ref")

        _validate_grounding_metadata(
            evidence_refs=self.evidence_refs,
            claim_refs=self.claim_refs,
            criterion_keys=self.criterion_keys,
            technology_names=self.technology_names,
            file_paths=self.file_paths,
        )
        return self


class PortfolioStatementBatch(InternalDomainModel):
    """Structured-output wrapper for reusable portfolio statements."""

    statements: tuple[PortfolioStatement, ...] = Field(
        min_length=1,
        max_length=15,
    )

    @model_validator(mode="after")
    def validate_statement_uniqueness(self) -> Self:
        identities = [
            (statement.statement_type, statement.content.casefold())
            for statement in self.statements
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("portfolio statements must be unique within each statement type")
        return self


class PortfolioSynthesis(InternalDomainModel):
    """Structured output generated by synthesizing repository analyses."""

    overall_summary: GroundedAnalysisItem
    representative_projects: tuple[RepresentativeProject, ...] = Field(
        min_length=1,
        max_length=5,
    )
    strengths: tuple[GroundedAnalysisItem, ...] = ()
    gaps: tuple[GroundedAnalysisItem, ...] = ()
    next_actions: tuple[GroundedAnalysisItem, ...] = ()
    job_appeal: GroundedAnalysisItem
    limitations: tuple[NonEmptyString, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_synthesis_members(self) -> Self:
        if self.overall_summary.item_type is not AnalysisItemType.INTERPRETATION:
            raise ValueError("overall_summary must be an INTERPRETATION")

        representative_names = [
            project.repository_full_name for project in self.representative_projects
        ]
        if len(representative_names) != len(set(representative_names)):
            raise ValueError("representative project names must be unique")

        if any(item.item_type is not AnalysisItemType.INTERPRETATION for item in self.strengths):
            raise ValueError("strengths must contain only INTERPRETATION items")
        if any(not item.evidence_refs for item in self.strengths):
            raise ValueError("strengths require at least one evidence ref")

        if any(item.item_type is not AnalysisItemType.INTERPRETATION for item in self.gaps):
            raise ValueError("gaps must contain only INTERPRETATION items")
        if any(not item.evidence_refs for item in self.gaps):
            raise ValueError("gaps require at least one evidence ref")

        if any(item.item_type is not AnalysisItemType.RECOMMENDATION for item in self.next_actions):
            raise ValueError("next_actions must contain only RECOMMENDATION items")

        if self.job_appeal.item_type is not AnalysisItemType.JOB_APPEAL:
            raise ValueError("job_appeal must be a JOB_APPEAL item")

        if len(self.limitations) != len(set(self.limitations)):
            raise ValueError("limitations must not contain duplicates")

        return self


class PortfolioAnalysis(InternalDomainModel):
    """Complete internal result assembled from analyses and generated coaching."""

    repository_analyses: tuple[RepositoryAnalysis, ...] = Field(
        min_length=1,
        max_length=5,
    )
    synthesis: PortfolioSynthesis
    interview_questions: tuple[InterviewQuestion, ...] = ()
    portfolio_statements: tuple[PortfolioStatement, ...] = ()

    @model_validator(mode="after")
    def validate_portfolio_members(self) -> Self:
        repository_names = [analysis.repository_full_name for analysis in self.repository_analyses]
        if len(repository_names) != len(set(repository_names)):
            raise ValueError("repository analysis names must be unique")
        known_repositories = set(repository_names)

        representative_names = [
            project.repository_full_name for project in self.synthesis.representative_projects
        ]
        if not set(representative_names).issubset(known_repositories):
            raise ValueError("representative projects must reference analyzed repositories")

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
        portfolio_scoped_stages = {
            InternalGenerationStage.PORTFOLIO,
            InternalGenerationStage.STATEMENT,
        }
        if self.stage in portfolio_scoped_stages and self.repository_full_name is not None:
            raise ValueError(f"{self.stage} generation must not reference a repository")
        return self


class InternalPortfolioReport(InternalDomainModel):
    """Complete internal P0/P1/P2 result and provider-neutral generation records."""

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

        statement_records = [
            record
            for record in self.generation_records
            if record.stage is InternalGenerationStage.STATEMENT
        ]
        if len(statement_records) != 1:
            raise ValueError("internal report requires exactly one STATEMENT generation record")

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
