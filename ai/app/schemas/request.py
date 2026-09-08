from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import (
    AnalysisDepth,
    ApiModel,
    RequestAnalysisPurpose,
    TargetCareerLevel,
    TargetJob,
)
from app.schemas.repository import RepositoryInput


class PortfolioReportRequest(ApiModel):
    """Backend analysis request v1.0 wire contract."""

    schema_version: Literal["1.0"]
    analysis_id: UUID
    target_job: TargetJob
    target_career_level: TargetCareerLevel
    analysis_purpose: RequestAnalysisPurpose
    requested_analysis_depth: AnalysisDepth
    extractor_version: str
    repositories: Annotated[list[RepositoryInput], Field(min_length=1, max_length=5)]
