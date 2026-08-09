from typing import Annotated, Literal

from pydantic import Field

from app.schemas.common import AnalysisPurpose, ApiModel, TargetJob
from app.schemas.repository import RepositoryInput


class PortfolioReportRequest(ApiModel):
    schema_version: Literal["1.0"]
    analysis_id: Annotated[int, Field(gt=0)]
    target_job: TargetJob
    analysis_purpose: AnalysisPurpose
    repositories: Annotated[list[RepositoryInput], Field(min_length=1, max_length=5)]
