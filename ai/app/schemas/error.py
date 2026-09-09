from typing import Annotated, Literal
from uuid import UUID

from pydantic import JsonValue, StrictBool, StringConstraints

from app.schemas.common import AnalysisErrorCode, ApiModel

type WireNonEmptyString = Annotated[str, StringConstraints(min_length=1)]


class AnalysisErrorResponse(ApiModel):
    """Backend analysis error-envelope v1.0 wire contract."""

    schema_version: Literal["1.0"]
    analysis_id: UUID | None
    code: AnalysisErrorCode
    message: WireNonEmptyString
    retryable: StrictBool
    details: dict[str, JsonValue]
