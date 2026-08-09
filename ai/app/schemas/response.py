from typing import Annotated, Literal

from pydantic import Field

from app.schemas.common import (
    ApiModel,
    Confidence,
    EvidenceType,
    NonEmptyString,
    Priority,
    TargetJob,
)

type NonEmptyStringList = Annotated[list[NonEmptyString], Field(min_length=1)]


class EvidenceBasedFinding(ApiModel):
    content: NonEmptyString
    evidence_type: EvidenceType
    evidence: NonEmptyStringList
    confidence: Confidence


class OverallDiagnosis(ApiModel):
    summary: NonEmptyString
    strengths: list[EvidenceBasedFinding]
    improvements: list[EvidenceBasedFinding]


class RepresentativeProject(ApiModel):
    repository_name: NonEmptyString
    reason: NonEmptyString
    evidence_type: EvidenceType
    evidence: NonEmptyStringList


class RepositoryReport(ApiModel):
    repository_name: NonEmptyString
    summary: NonEmptyString
    strengths: list[EvidenceBasedFinding]
    improvements: list[EvidenceBasedFinding]
    interview_points: list[EvidenceBasedFinding]


class JobAppeal(ApiModel):
    target_job: TargetJob
    visible_experiences: list[NonEmptyString]
    experiences_to_highlight: list[NonEmptyString]
    experiences_to_improve: list[NonEmptyString]


class RoadmapItem(ApiModel):
    priority: Priority
    title: NonEmptyString
    reason: NonEmptyString
    actions: NonEmptyStringList
    expected_effect: NonEmptyString


class InterviewQuestion(ApiModel):
    repository_name: NonEmptyString
    question: NonEmptyString
    intent: NonEmptyString
    answer_guide: NonEmptyStringList
    follow_up_questions: list[NonEmptyString]
    evidence_type: EvidenceType
    evidence: NonEmptyStringList


class PortfolioStatements(ApiModel):
    resume: NonEmptyString
    portfolio: NonEmptyString
    interview: NonEmptyString


class PortfolioReportResponse(ApiModel):
    schema_version: Literal["1.0"]
    analysis_id: Annotated[int, Field(gt=0)]
    overall_diagnosis: OverallDiagnosis
    representative_projects: Annotated[
        list[RepresentativeProject], Field(min_length=1, max_length=5)
    ]
    repository_reports: Annotated[list[RepositoryReport], Field(min_length=1, max_length=5)]
    job_appeal: JobAppeal
    roadmap: Annotated[list[RoadmapItem], Field(min_length=1)]
    interview_questions: Annotated[list[InterviewQuestion], Field(min_length=1)]
    portfolio_statements: PortfolioStatements
    limitations: NonEmptyStringList
