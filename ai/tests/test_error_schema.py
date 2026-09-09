import json
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.schemas.common import AnalysisErrorCode
from app.schemas.error import AnalysisErrorResponse

BACKEND_CONTRACT_COMMIT = "9d9fc7caf36150bc090c7a5b9bad62ce33743fc3"
FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "contracts"
    / "backend_contract"
    / "analysis-error.example.json"
)


def load_example() -> dict[str, Any]:
    with FIXTURE_PATH.open(encoding="utf-8") as fixture_file:
        raw_data: object = json.load(fixture_file)

    if not isinstance(raw_data, dict):
        raise TypeError("Error fixture must contain a JSON object")
    return cast(dict[str, Any], raw_data)


@pytest.fixture
def valid_error_data() -> dict[str, Any]:
    return load_example()


def test_backend_example_parses_and_round_trips() -> None:
    raw_data = load_example()

    response = AnalysisErrorResponse.model_validate(raw_data)

    assert response.analysis_id == UUID("11111111-1111-4111-8111-111111111111")
    assert response.code is AnalysisErrorCode.LLM_TIMEOUT
    assert response.model_dump(mode="json", by_alias=True) == raw_data
    assert "schemaVersion" in response.model_dump(mode="json", by_alias=True)


def test_python_field_names_are_accepted(valid_error_data: dict[str, Any]) -> None:
    response = AnalysisErrorResponse.model_validate(valid_error_data)

    reparsed = AnalysisErrorResponse.model_validate(response.model_dump())

    assert reparsed == response


@pytest.mark.parametrize("schema_version", ["1.1", "2.0", 1.0])
def test_schema_version_only_accepts_1_0(
    valid_error_data: dict[str, Any], schema_version: object
) -> None:
    valid_error_data["schemaVersion"] = schema_version

    with pytest.raises(ValidationError):
        AnalysisErrorResponse.model_validate(valid_error_data)


@pytest.mark.parametrize(
    "required_field",
    ["schemaVersion", "analysisId", "code", "message", "retryable", "details"],
)
def test_missing_required_top_level_fields_are_rejected(
    valid_error_data: dict[str, Any], required_field: str
) -> None:
    valid_error_data.pop(required_field)

    with pytest.raises(ValidationError) as exc_info:
        AnalysisErrorResponse.model_validate(valid_error_data)

    assert exc_info.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize("extra_field", ["httpStatus", "timestamp", "traceId", "unknown"])
def test_unknown_top_level_fields_are_rejected(
    valid_error_data: dict[str, Any], extra_field: str
) -> None:
    valid_error_data[extra_field] = "unexpected"

    with pytest.raises(ValidationError) as exc_info:
        AnalysisErrorResponse.model_validate(valid_error_data)

    assert any(error["type"] == "extra_forbidden" for error in exc_info.value.errors())


def test_analysis_id_allows_null(valid_error_data: dict[str, Any]) -> None:
    valid_error_data["analysisId"] = None

    response = AnalysisErrorResponse.model_validate(valid_error_data)

    assert response.analysis_id is None


def test_analysis_id_rejects_invalid_uuid(valid_error_data: dict[str, Any]) -> None:
    valid_error_data["analysisId"] = "not-a-uuid"

    with pytest.raises(ValidationError):
        AnalysisErrorResponse.model_validate(valid_error_data)


def test_analysis_id_does_not_require_uuid_v4(valid_error_data: dict[str, Any]) -> None:
    uuid_v1 = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
    valid_error_data["analysisId"] = uuid_v1

    response = AnalysisErrorResponse.model_validate(valid_error_data)

    assert response.analysis_id == UUID(uuid_v1)
    assert response.analysis_id.version == 1


@pytest.mark.parametrize("code", list(AnalysisErrorCode))
def test_all_contract_error_codes_are_allowed(
    valid_error_data: dict[str, Any], code: AnalysisErrorCode
) -> None:
    valid_error_data["code"] = code.value

    response = AnalysisErrorResponse.model_validate(valid_error_data)

    assert response.code is code


@pytest.mark.parametrize(
    "invalid_code",
    ["UNKNOWN_ERROR", "DUPLICATE_REPOSITORY_ID", "UNKNOWN_EVIDENCE_REF"],
)
def test_unknown_and_internal_error_codes_are_rejected(
    valid_error_data: dict[str, Any], invalid_code: str
) -> None:
    valid_error_data["code"] = invalid_code

    with pytest.raises(ValidationError):
        AnalysisErrorResponse.model_validate(valid_error_data)


@pytest.mark.parametrize("message", ["정상 오류 메시지", " "])
def test_message_accepts_non_empty_strings(valid_error_data: dict[str, Any], message: str) -> None:
    valid_error_data["message"] = message

    response = AnalysisErrorResponse.model_validate(valid_error_data)

    assert response.message == message


@pytest.mark.parametrize("message", ["", 123, True])
def test_message_rejects_empty_or_non_string_values(
    valid_error_data: dict[str, Any], message: object
) -> None:
    valid_error_data["message"] = message

    with pytest.raises(ValidationError):
        AnalysisErrorResponse.model_validate(valid_error_data)


@pytest.mark.parametrize("retryable", [True, False])
def test_retryable_accepts_only_json_booleans(
    valid_error_data: dict[str, Any], retryable: bool
) -> None:
    valid_error_data["retryable"] = retryable

    response = AnalysisErrorResponse.model_validate(valid_error_data)

    assert response.retryable is retryable


@pytest.mark.parametrize("retryable", [1, 0, "true", "false", "yes", "no"])
def test_retryable_rejects_coercible_values(
    valid_error_data: dict[str, Any], retryable: object
) -> None:
    valid_error_data["retryable"] = retryable

    with pytest.raises(ValidationError):
        AnalysisErrorResponse.model_validate(valid_error_data)


@pytest.mark.parametrize(
    "details",
    [
        {},
        {"message": "detail"},
        {"integer": 1, "decimal": 1.5},
        {"boolean": True, "nothing": None},
        {"items": ["value", 1, False, None]},
        {"nested": {"key": {"deeper": "value"}}},
        {"timeoutMs": 30000},
    ],
)
def test_details_accepts_json_objects(
    valid_error_data: dict[str, Any], details: dict[str, object]
) -> None:
    valid_error_data["details"] = details

    response = AnalysisErrorResponse.model_validate(valid_error_data)

    assert response.details == details


@pytest.mark.parametrize("details", [[], "detail", None])
def test_details_rejects_non_object_top_level_values(
    valid_error_data: dict[str, Any], details: object
) -> None:
    valid_error_data["details"] = details

    with pytest.raises(ValidationError):
        AnalysisErrorResponse.model_validate(valid_error_data)


def test_details_rejects_non_json_values(valid_error_data: dict[str, Any]) -> None:
    valid_error_data["details"] = {"value": object()}

    with pytest.raises(ValidationError):
        AnalysisErrorResponse.model_validate(valid_error_data)


def test_details_keys_are_not_top_level_extra_fields(valid_error_data: dict[str, Any]) -> None:
    details = {
        "customKey": "allowed",
        "violations": [{"code": "UNKNOWN_EVIDENCE_REF", "fieldPath": "findings[0]"}],
    }
    valid_error_data["details"] = details

    response = AnalysisErrorResponse.model_validate(valid_error_data)

    assert response.details == details


@pytest.mark.parametrize(
    ("code", "retryable"),
    [
        ("INVALID_REQUEST", True),
        ("LLM_TIMEOUT", False),
    ],
)
def test_dto_does_not_enforce_code_retryable_policy(
    valid_error_data: dict[str, Any], code: str, retryable: bool
) -> None:
    valid_error_data["code"] = code
    valid_error_data["retryable"] = retryable

    response = AnalysisErrorResponse.model_validate(valid_error_data)

    assert response.code.value == code
    assert response.retryable is retryable


def test_wire_error_does_not_convert_internal_exceptions(
    valid_error_data: dict[str, Any],
) -> None:
    response = AnalysisErrorResponse.model_validate(valid_error_data)

    assert not hasattr(response, "from_exception")
    assert not hasattr(response, "to_exception")
