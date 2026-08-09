from typing import Annotated, Literal

from pydantic import Field

from app.schemas.common import (
    ApiModel,
    Confidence,
    EvidenceType,
    NonEmptyString,
    ProjectType,
)

type Percentage = Annotated[float, Field(ge=0, le=100)]
type Score = Annotated[int, Field(ge=0, le=100)]
type NonNegativeInteger = Annotated[int, Field(ge=0)]
type PositiveInteger = Annotated[int, Field(gt=0)]


class LanguageShare(ApiModel):
    name: NonEmptyString
    percentage: Percentage


class GitHubEvidenceReference(ApiModel):
    type: Literal[EvidenceType.GITHUB]
    path: NonEmptyString
    description: NonEmptyString


class TechStackEvidence(ApiModel):
    name: NonEmptyString
    confidence: Confidence
    evidence: Annotated[list[GitHubEvidenceReference], Field(min_length=1)]


class ReadmeEvidence(ApiModel):
    exists: bool
    has_introduction: bool
    has_features: bool
    has_run_guide: bool
    has_environment_variables: bool
    has_tech_stack: bool
    has_api_examples: bool
    has_testing_guide: bool
    has_deployment_guide: bool
    has_troubleshooting: bool


class TestingEvidence(ApiModel):
    exists: bool
    file_count: NonNegativeInteger


class DockerEvidence(ApiModel):
    dockerfile: bool
    compose: bool


class CiEvidence(ApiModel):
    github_actions: bool
    runs_build: bool
    runs_tests: bool


class ActivityEvidence(ApiModel):
    recent_commit_count: NonNegativeInteger
    user_commit_count: NonNegativeInteger
    user_pull_request_count: NonNegativeInteger
    activity_area_candidates: list[NonEmptyString]


class GitHubEvidence(ApiModel):
    languages: list[LanguageShare]
    tech_stacks: list[TechStackEvidence]
    readme: ReadmeEvidence
    testing: TestingEvidence
    docker: DockerEvidence
    ci: CiEvidence
    activity: ActivityEvidence


class BackendMetrics(ApiModel):
    portfolio_readiness_score: Score
    readme_readiness_score: Score
    evidence_clarity_score: Score


class UserProvidedRole(ApiModel):
    project_type: ProjectType
    role: NonEmptyString
    implemented_features: list[NonEmptyString]
    related_files: list[NonEmptyString]
    related_pull_requests: list[NonEmptyString]
    related_commits: list[NonEmptyString]


class RepositoryInput(ApiModel):
    repository_id: PositiveInteger
    name: NonEmptyString
    full_name: NonEmptyString
    description: NonEmptyString | None
    github_evidence: GitHubEvidence
    backend_metrics: BackendMetrics
    user_provided_role: UserProvidedRole | None = None
