from enum import StrEnum
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.domain import AnalysisDepth, InternalEvidenceType

NonEmptyString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
CriteriaKey = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[A-Z][A-Z0-9_]*$"),
]


class CriteriaTargetJob(StrEnum):
    """Target jobs supported by the independent criteria layer."""

    BACKEND = "BACKEND"


class CriteriaGuardrailCode(StrEnum):
    """Machine-readable inference boundaries required by criteria layers."""

    USER_ABILITY_ASSERTION = "USER_ABILITY_ASSERTION"
    CONTRIBUTION_ASSERTION = "CONTRIBUTION_ASSERTION"
    CAREER_LEVEL_ASSERTION = "CAREER_LEVEL_ASSERTION"
    EMPLOYMENT_PROBABILITY_ASSERTION = "EMPLOYMENT_PROBABILITY_ASSERTION"
    NOT_OBSERVED_AS_ABSENCE = "NOT_OBSERVED_AS_ABSENCE"
    ACTIVITY_VOLUME_AS_SKILL = "ACTIVITY_VOLUME_AS_SKILL"
    ACTIVITY_VOLUME_AS_CONTRIBUTION = "ACTIVITY_VOLUME_AS_CONTRIBUTION"
    ACTIVITY_ABSENCE_AS_NON_CONTRIBUTION = "ACTIVITY_ABSENCE_AS_NON_CONTRIBUTION"
    CODE_QUALITY_WITHOUT_P2 = "CODE_QUALITY_WITHOUT_P2"
    USER_CLAIM_AS_FACT = "USER_CLAIM_AS_FACT"
    REPOSITORY_WIDE_GENERALIZATION = "REPOSITORY_WIDE_GENERALIZATION"
    CODE_EXECUTION = "CODE_EXECUTION"


BACKEND_CRITERIA_KEYS_BY_DEPTH: Final[dict[AnalysisDepth, frozenset[str]]] = {
    AnalysisDepth.P0: frozenset(
        {
            "README_READINESS",
            "TECH_STACK_EVIDENCE",
            "TEST_PRESENCE",
            "DOCKER_CONFIGURATION",
            "GITHUB_ACTIONS_CONFIGURATION",
        }
    ),
    AnalysisDepth.P1: frozenset(
        {
            "ACTIVITY_SCOPE",
            "CLAIM_ACTIVITY_LINK",
            "CHANGE_AREA_OBSERVATION",
        }
    ),
    AnalysisDepth.P2: frozenset(
        {
            "SNIPPET_SCOPE",
            "INPUT_VALIDATION_OBSERVATION",
            "ERROR_HANDLING_OBSERVATION",
            "RESPONSIBILITY_OBSERVATION",
            "TEST_CASE_OBSERVATION",
        }
    ),
}

BACKEND_GUARDRAILS_BY_DEPTH: Final[dict[AnalysisDepth, frozenset[CriteriaGuardrailCode]]] = {
    AnalysisDepth.P0: frozenset(
        {
            CriteriaGuardrailCode.USER_ABILITY_ASSERTION,
            CriteriaGuardrailCode.CONTRIBUTION_ASSERTION,
            CriteriaGuardrailCode.CAREER_LEVEL_ASSERTION,
            CriteriaGuardrailCode.EMPLOYMENT_PROBABILITY_ASSERTION,
            CriteriaGuardrailCode.NOT_OBSERVED_AS_ABSENCE,
            CriteriaGuardrailCode.CODE_QUALITY_WITHOUT_P2,
        }
    ),
    AnalysisDepth.P1: frozenset(
        {
            CriteriaGuardrailCode.ACTIVITY_VOLUME_AS_SKILL,
            CriteriaGuardrailCode.ACTIVITY_VOLUME_AS_CONTRIBUTION,
            CriteriaGuardrailCode.ACTIVITY_ABSENCE_AS_NON_CONTRIBUTION,
            CriteriaGuardrailCode.CODE_QUALITY_WITHOUT_P2,
            CriteriaGuardrailCode.USER_CLAIM_AS_FACT,
        }
    ),
    AnalysisDepth.P2: frozenset(
        {
            CriteriaGuardrailCode.REPOSITORY_WIDE_GENERALIZATION,
            CriteriaGuardrailCode.USER_ABILITY_ASSERTION,
            CriteriaGuardrailCode.CONTRIBUTION_ASSERTION,
            CriteriaGuardrailCode.CAREER_LEVEL_ASSERTION,
            CriteriaGuardrailCode.CODE_EXECUTION,
        }
    ),
}

ALLOWED_EVIDENCE_TYPES_BY_DEPTH: Final[dict[AnalysisDepth, frozenset[InternalEvidenceType]]] = {
    AnalysisDepth.P0: frozenset(
        {
            InternalEvidenceType.GITHUB_STATIC,
            InternalEvidenceType.BACKEND_DERIVED,
        }
    ),
    AnalysisDepth.P1: frozenset(
        {
            InternalEvidenceType.GITHUB_ACTIVITY,
            InternalEvidenceType.BACKEND_DERIVED,
        }
    ),
    AnalysisDepth.P2: frozenset(
        {
            InternalEvidenceType.CODE_EVIDENCE,
            InternalEvidenceType.BACKEND_DERIVED,
        }
    ),
}

_DEPTH_PREFIXES: Final[dict[AnalysisDepth, tuple[AnalysisDepth, ...]]] = {
    AnalysisDepth.P0: (AnalysisDepth.P0,),
    AnalysisDepth.P1: (AnalysisDepth.P0, AnalysisDepth.P1),
    AnalysisDepth.P2: (AnalysisDepth.P0, AnalysisDepth.P1, AnalysisDepth.P2),
}
_KEY_DEPTH: Final[dict[str, AnalysisDepth]] = {
    key: depth for depth, keys in BACKEND_CRITERIA_KEYS_BY_DEPTH.items() for key in keys
}


class CriteriaModel(BaseModel):
    """Strict base model for internal criteria configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Criterion(CriteriaModel):
    """One depth-scoped interpretation boundary."""

    key: CriteriaKey
    analysis_depth: AnalysisDepth
    title: NonEmptyString
    description: NonEmptyString
    allowed_evidence_types: tuple[InternalEvidenceType, ...] = Field(min_length=1)
    allow_user_claims: bool = False
    allowed_judgments: tuple[NonEmptyString, ...] = Field(min_length=1)
    forbidden_judgments: tuple[NonEmptyString, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_criterion_policy(self) -> Self:
        fields = {
            "allowed_evidence_types": self.allowed_evidence_types,
            "allowed_judgments": self.allowed_judgments,
            "forbidden_judgments": self.forbidden_judgments,
        }
        for field_name, values in fields.items():
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must not contain duplicate values")

        allowed_types = ALLOWED_EVIDENCE_TYPES_BY_DEPTH[self.analysis_depth]
        unexpected_types = set(self.allowed_evidence_types) - allowed_types
        if unexpected_types:
            names = ", ".join(sorted(item.value for item in unexpected_types))
            raise ValueError(
                f"{self.analysis_depth} criterion contains disallowed evidence types: {names}"
            )

        expects_user_claims = self.key == "CLAIM_ACTIVITY_LINK"
        if self.allow_user_claims != expects_user_claims:
            raise ValueError("only CLAIM_ACTIVITY_LINK must allow user claims")
        return self


class CriteriaLayer(CriteriaModel):
    """One independently validated P0, P1, or P2 YAML layer."""

    version: Literal["1.0"]
    target_job: Literal[CriteriaTargetJob.BACKEND]
    analysis_depth: AnalysisDepth
    guardrail_codes: tuple[CriteriaGuardrailCode, ...] = Field(min_length=1)
    criteria: tuple[Criterion, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_layer_contract(self) -> Self:
        _validate_unique_criteria_keys(self.criteria)
        _validate_exact_criteria_keys(
            self.criteria,
            BACKEND_CRITERIA_KEYS_BY_DEPTH[self.analysis_depth],
        )
        if any(item.analysis_depth is not self.analysis_depth for item in self.criteria):
            raise ValueError("criterion analysis_depth must match its criteria layer")
        _validate_exact_guardrails(
            self.guardrail_codes,
            BACKEND_GUARDRAILS_BY_DEPTH[self.analysis_depth],
        )
        return self


class CriteriaSet(CriteriaModel):
    """Cumulative BACKEND criteria from P0 through the requested depth."""

    version: Literal["1.0"]
    target_job: Literal[CriteriaTargetJob.BACKEND]
    analysis_depth: AnalysisDepth
    guardrail_codes: tuple[CriteriaGuardrailCode, ...] = Field(min_length=1)
    criteria: tuple[Criterion, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cumulative_contract(self) -> Self:
        expected_depths = _DEPTH_PREFIXES[self.analysis_depth]
        expected_keys = frozenset(
            key for depth in expected_depths for key in BACKEND_CRITERIA_KEYS_BY_DEPTH[depth]
        )
        expected_guardrails = frozenset(
            guardrail
            for depth in expected_depths
            for guardrail in BACKEND_GUARDRAILS_BY_DEPTH[depth]
        )

        _validate_unique_criteria_keys(self.criteria)
        _validate_exact_criteria_keys(self.criteria, expected_keys)
        _validate_exact_guardrails(self.guardrail_codes, expected_guardrails)

        if any(_KEY_DEPTH[item.key] is not item.analysis_depth for item in self.criteria):
            raise ValueError("criterion key does not match its defined analysis depth")

        depth_ranks = {depth: index for index, depth in enumerate(AnalysisDepth)}
        actual_ranks = [depth_ranks[item.analysis_depth] for item in self.criteria]
        if actual_ranks != sorted(actual_ranks):
            raise ValueError("cumulative criteria must be ordered from P0 through requested depth")
        return self


def _validate_unique_criteria_keys(criteria: tuple[Criterion, ...]) -> None:
    keys = [item.key for item in criteria]
    if len(keys) != len(set(keys)):
        raise ValueError("criteria keys must be unique")


def _validate_exact_criteria_keys(
    criteria: tuple[Criterion, ...],
    expected_keys: frozenset[str],
) -> None:
    actual_keys = {item.key for item in criteria}
    missing_keys = sorted(expected_keys - actual_keys)
    unexpected_keys = sorted(actual_keys - expected_keys)
    if missing_keys or unexpected_keys:
        problems: list[str] = []
        if missing_keys:
            problems.append(f"missing criteria keys: {', '.join(missing_keys)}")
        if unexpected_keys:
            problems.append(f"unexpected criteria keys: {', '.join(unexpected_keys)}")
        raise ValueError("; ".join(problems))


def _validate_exact_guardrails(
    guardrails: tuple[CriteriaGuardrailCode, ...],
    expected_guardrails: frozenset[CriteriaGuardrailCode],
) -> None:
    if len(guardrails) != len(set(guardrails)):
        raise ValueError("guardrail_codes must not contain duplicates")

    actual_guardrails = set(guardrails)
    missing_guardrails = sorted(item.value for item in expected_guardrails - actual_guardrails)
    unexpected_guardrails = sorted(item.value for item in actual_guardrails - expected_guardrails)
    if missing_guardrails or unexpected_guardrails:
        problems: list[str] = []
        if missing_guardrails:
            problems.append(f"missing guardrail codes: {', '.join(missing_guardrails)}")
        if unexpected_guardrails:
            problems.append(f"unexpected guardrail codes: {', '.join(unexpected_guardrails)}")
        raise ValueError("; ".join(problems))
