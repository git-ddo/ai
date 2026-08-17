from dataclasses import FrozenInstanceError

import pytest

from app.core.exceptions import LLMProviderError, ReportPolicyError
from app.validators.report_validator import PolicyViolation, PolicyViolationCode

EXPECTED_POLICY_VIOLATION_CODES = {
    "UNKNOWN_EVIDENCE_REF",
    "UNKNOWN_CLAIM_REF",
    "CROSS_REPOSITORY_REF",
    "UNKNOWN_TECHNOLOGY",
    "UNKNOWN_FILE_PATH",
    "P0_SCOPE_VIOLATION",
    "USER_ABILITY_ASSERTION",
    "CONTRIBUTION_ASSERTION",
    "NOT_OBSERVED_MISUSE",
    "USER_CLAIM_AS_FACT",
    "MISSING_DERIVED_EVIDENCE",
}


def make_violation(
    code: PolicyViolationCode = PolicyViolationCode.UNKNOWN_TECHNOLOGY,
    *,
    message: str = "Technology is not present in the input evidence",
    field_path: str | None = None,
) -> PolicyViolation:
    return PolicyViolation(code=code, message=message, field_path=field_path)


def test_policy_violation_code_has_exact_expected_values() -> None:
    assert {code.value for code in PolicyViolationCode} == (EXPECTED_POLICY_VIOLATION_CODES)


def test_policy_violation_stores_normalized_values() -> None:
    violation = make_violation(
        message="  Unknown technology  ",
        field_path="  repository_analysis.strengths[0]  ",
    )

    assert violation.code is PolicyViolationCode.UNKNOWN_TECHNOLOGY
    assert violation.message == "Unknown technology"
    assert violation.field_path == "repository_analysis.strengths[0]"


@pytest.mark.parametrize("message", ["", "   "])
def test_policy_violation_rejects_blank_message(message: str) -> None:
    with pytest.raises(ValueError, match="message must not be blank"):
        make_violation(message=message)


def test_policy_violation_allows_absent_field_path() -> None:
    assert make_violation().field_path is None


@pytest.mark.parametrize("field_path", ["", "   "])
def test_policy_violation_rejects_blank_field_path(field_path: str) -> None:
    with pytest.raises(ValueError, match="field_path must not be blank"):
        make_violation(field_path=field_path)


def test_policy_violation_is_frozen() -> None:
    violation = make_violation()

    with pytest.raises(FrozenInstanceError):
        violation.message = "changed"


def test_report_policy_error_stores_single_violation_as_tuple() -> None:
    violation = make_violation()
    error = ReportPolicyError([violation])

    assert error.violations == (violation,)
    assert isinstance(error.violations, tuple)


def test_report_policy_error_preserves_violation_order() -> None:
    first = make_violation(PolicyViolationCode.UNKNOWN_FILE_PATH)
    second = make_violation(PolicyViolationCode.P0_SCOPE_VIOLATION)

    assert ReportPolicyError([first, second]).violations == (first, second)


def test_report_policy_error_preserves_duplicate_violations() -> None:
    violation = make_violation()

    assert ReportPolicyError([violation, violation]).violations == (
        violation,
        violation,
    )


def test_report_policy_error_rejects_empty_violations() -> None:
    with pytest.raises(ValueError, match="at least one violation"):
        ReportPolicyError([])


def test_report_policy_error_defensively_copies_input_sequence() -> None:
    first = make_violation(PolicyViolationCode.UNKNOWN_EVIDENCE_REF)
    mutable_violations = [first]
    error = ReportPolicyError(mutable_violations)

    mutable_violations.append(make_violation(PolicyViolationCode.UNKNOWN_CLAIM_REF))

    assert error.violations == (first,)


def test_report_policy_error_string_contains_codes_in_order() -> None:
    error = ReportPolicyError(
        [
            make_violation(PolicyViolationCode.UNKNOWN_EVIDENCE_REF),
            make_violation(PolicyViolationCode.UNKNOWN_CLAIM_REF),
        ]
    )

    assert str(error) == (
        "Report policy validation failed: UNKNOWN_EVIDENCE_REF, UNKNOWN_CLAIM_REF"
    )


def test_report_policy_error_string_excludes_violation_messages() -> None:
    sensitive_message = "untrusted repository content must remain private"
    error = ReportPolicyError([make_violation(message=sensitive_message)])

    assert sensitive_message not in str(error)


def test_report_policy_error_is_not_an_llm_provider_error() -> None:
    error = ReportPolicyError([make_violation()])

    assert not isinstance(error, LLMProviderError)


def test_report_policy_error_does_not_auto_expose_sensitive_content() -> None:
    prompt = "system prompt raw text"
    response = "raw model response"
    secret = "api-secret-value"
    error = ReportPolicyError([make_violation(message=f"{prompt} {response} {secret}")])

    rendered_error = str(error)
    assert prompt not in rendered_error
    assert response not in rendered_error
    assert secret not in rendered_error
