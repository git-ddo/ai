import pytest
from pydantic import ValidationError

from app.schemas.common import (
    AnalysisPurpose,
    ApiModel,
    Confidence,
    EvidenceType,
    Priority,
    ProjectType,
    TargetJob,
)


class ExampleApiModel(ApiModel):
    analysis_id: int
    target_job: TargetJob


def test_enum_values_match_api_contract() -> None:
    assert [item.value for item in TargetJob] == [
        "BACKEND",
        "FRONTEND",
        "AI",
        "CLOUD_INFRA",
    ]
    assert [item.value for item in AnalysisPurpose] == [
        "GITHUB_DIAGNOSIS",
        "PORTFOLIO_ORGANIZATION",
        "JOB_PREPARATION",
        "INTERVIEW_PREPARATION",
    ]
    assert [item.value for item in ProjectType] == ["PERSONAL", "TEAM"]
    assert [item.value for item in EvidenceType] == [
        "GITHUB",
        "USER_PROVIDED",
        "BACKEND_DERIVED",
        "AI_RECOMMENDATION",
    ]
    assert [item.value for item in Confidence] == ["HIGH", "MEDIUM", "LOW"]
    assert [item.value for item in Priority] == ["HIGH", "MEDIUM", "LOW"]


def test_api_model_accepts_and_serializes_camel_case_fields() -> None:
    model = ExampleApiModel.model_validate(
        {
            "analysisId": 123,
            "targetJob": "BACKEND",
        }
    )

    assert model.analysis_id == 123
    assert model.target_job is TargetJob.BACKEND
    assert model.model_dump(mode="json", by_alias=True) == {
        "analysisId": 123,
        "targetJob": "BACKEND",
    }
    assert "analysisId" in ExampleApiModel.model_json_schema()["properties"]


def test_api_model_accepts_python_field_names() -> None:
    model = ExampleApiModel(analysis_id=123, target_job=TargetJob.AI)

    assert model.analysis_id == 123
    assert model.target_job is TargetJob.AI


def test_api_model_rejects_unknown_enum_values() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ExampleApiModel.model_validate(
            {
                "analysisId": 123,
                "targetJob": "DATA",
            }
        )

    assert exc_info.value.errors()[0]["type"] == "enum"


def test_api_model_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ExampleApiModel.model_validate(
            {
                "analysisId": 123,
                "targetJob": "BACKEND",
                "unexpectedField": "value",
            }
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"
