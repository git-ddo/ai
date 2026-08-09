from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """Base model for versioned JSON contracts shared with the backend."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class TargetJob(StrEnum):
    BACKEND = "BACKEND"
    FRONTEND = "FRONTEND"
    AI = "AI"
    CLOUD_INFRA = "CLOUD_INFRA"


class AnalysisPurpose(StrEnum):
    GITHUB_DIAGNOSIS = "GITHUB_DIAGNOSIS"
    PORTFOLIO_ORGANIZATION = "PORTFOLIO_ORGANIZATION"
    JOB_PREPARATION = "JOB_PREPARATION"
    INTERVIEW_PREPARATION = "INTERVIEW_PREPARATION"


class ProjectType(StrEnum):
    PERSONAL = "PERSONAL"
    TEAM = "TEAM"


class EvidenceType(StrEnum):
    GITHUB = "GITHUB"
    USER_PROVIDED = "USER_PROVIDED"
    BACKEND_DERIVED = "BACKEND_DERIVED"
    AI_RECOMMENDATION = "AI_RECOMMENDATION"


class Confidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Priority(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
