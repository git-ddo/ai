from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints
from pydantic.alias_generators import to_camel

type NonEmptyString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


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


class RequestAnalysisPurpose(StrEnum):
    """Analysis purposes accepted by the Backend request v1.0 contract."""

    PORTFOLIO_ANALYSIS = "PORTFOLIO_ANALYSIS"


class TargetCareerLevel(StrEnum):
    ENTRY = "ENTRY"
    JUNIOR = "JUNIOR"
    MID = "MID"
    SENIOR = "SENIOR"


class AnalysisDepth(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class SnapshotHashAlgorithm(StrEnum):
    SHA1 = "SHA1"
    SHA256 = "SHA256"


class RequestEvidenceType(StrEnum):
    """Evidence types accepted by the Backend request v1.0 contract."""

    GITHUB_STATIC = "GITHUB_STATIC"
    GITHUB_ACTIVITY = "GITHUB_ACTIVITY"
    CODE_EVIDENCE = "CODE_EVIDENCE"
    BACKEND_DERIVED = "BACKEND_DERIVED"


class EvidenceValueType(StrEnum):
    STRING = "STRING"
    BOOLEAN = "BOOLEAN"
    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"
    STRING_LIST = "STRING_LIST"


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
