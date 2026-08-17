from dataclasses import dataclass
from enum import StrEnum


class PolicyViolationCode(StrEnum):
    UNKNOWN_EVIDENCE_REF = "UNKNOWN_EVIDENCE_REF"
    UNKNOWN_CLAIM_REF = "UNKNOWN_CLAIM_REF"
    CROSS_REPOSITORY_REF = "CROSS_REPOSITORY_REF"
    UNKNOWN_TECHNOLOGY = "UNKNOWN_TECHNOLOGY"
    UNKNOWN_FILE_PATH = "UNKNOWN_FILE_PATH"
    P0_SCOPE_VIOLATION = "P0_SCOPE_VIOLATION"
    USER_ABILITY_ASSERTION = "USER_ABILITY_ASSERTION"
    CONTRIBUTION_ASSERTION = "CONTRIBUTION_ASSERTION"
    NOT_OBSERVED_MISUSE = "NOT_OBSERVED_MISUSE"
    USER_CLAIM_AS_FACT = "USER_CLAIM_AS_FACT"
    MISSING_DERIVED_EVIDENCE = "MISSING_DERIVED_EVIDENCE"


@dataclass(frozen=True, slots=True)
class PolicyViolation:
    code: PolicyViolationCode
    message: str
    field_path: str | None = None

    def __post_init__(self) -> None:
        message = self.message.strip()
        if not message:
            raise ValueError("Policy violation message must not be blank")
        object.__setattr__(self, "message", message)

        if self.field_path is None:
            return

        field_path = self.field_path.strip()
        if not field_path:
            raise ValueError("Policy violation field_path must not be blank")
        object.__setattr__(self, "field_path", field_path)


__all__ = ["PolicyViolation", "PolicyViolationCode"]
