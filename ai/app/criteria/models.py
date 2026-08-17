from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonEmptyString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
CriteriaKey = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[A-Z][A-Z0-9_]*$"),
]

BACKEND_P0_CRITERIA_KEYS: Final[frozenset[str]] = frozenset(
    {
        "README_READINESS",
        "TECH_STACK_EVIDENCE",
        "TEST_PRESENCE",
        "DOCKER_CONFIGURATION",
        "GITHUB_ACTIONS_CONFIGURATION",
    }
)


class CriteriaTargetJob(StrEnum):
    """Target jobs supported by the independent criteria layer."""

    BACKEND = "BACKEND"


class CriteriaAnalysisDepth(StrEnum):
    """Analysis depths supported by the independent criteria layer."""

    P0 = "P0"


class P0EvidenceType(StrEnum):
    """Evidence types that P0 criteria may interpret."""

    GITHUB_STATIC = "GITHUB_STATIC"
    BACKEND_DERIVED = "BACKEND_DERIVED"


class CriteriaModel(BaseModel):
    """Strict base model for internal criteria configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Criterion(CriteriaModel):
    """One allowed P0 interpretation boundary."""

    key: CriteriaKey
    title: NonEmptyString
    description: NonEmptyString
    allowed_evidence_types: tuple[P0EvidenceType, ...] = Field(min_length=1)
    allowed_judgments: tuple[NonEmptyString, ...] = Field(min_length=1)
    forbidden_judgments: tuple[NonEmptyString, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_duplicate_values(self) -> "Criterion":
        fields = {
            "allowed_evidence_types": self.allowed_evidence_types,
            "allowed_judgments": self.allowed_judgments,
            "forbidden_judgments": self.forbidden_judgments,
        }
        for field_name, values in fields.items():
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must not contain duplicate values")
        return self


class CriteriaSet(CriteriaModel):
    """Validated BACKEND P0 criteria loaded from YAML."""

    version: Literal["1.0"]
    target_job: Literal[CriteriaTargetJob.BACKEND]
    analysis_depth: Literal[CriteriaAnalysisDepth.P0]
    criteria: tuple[Criterion, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_criteria_keys(self) -> "CriteriaSet":
        keys = [criterion.key for criterion in self.criteria]
        if len(keys) != len(set(keys)):
            raise ValueError("criteria keys must be unique")

        actual_keys = set(keys)
        missing_keys = sorted(BACKEND_P0_CRITERIA_KEYS - actual_keys)
        unexpected_keys = sorted(actual_keys - BACKEND_P0_CRITERIA_KEYS)
        if missing_keys or unexpected_keys:
            problems: list[str] = []
            if missing_keys:
                problems.append(f"missing criteria keys: {', '.join(missing_keys)}")
            if unexpected_keys:
                problems.append(f"unexpected criteria keys: {', '.join(unexpected_keys)}")
            raise ValueError("; ".join(problems))
        return self
