from fastapi import APIRouter, Request, status

from app.core.runtime import ReportRuntime
from app.schemas.request import PortfolioReportRequest
from app.schemas.response import PortfolioReportResponse

router = APIRouter(prefix="/internal/v1", tags=["reports"])


def get_report_runtime(request: Request) -> ReportRuntime:
    """Return the lifespan-managed runtime without trusting request input."""

    runtime = getattr(request.app.state, "report_runtime", None)
    if not isinstance(runtime, ReportRuntime):
        raise RuntimeError("Portfolio report runtime is unavailable.")
    return runtime


@router.post(
    "/portfolio-reports",
    response_model=PortfolioReportResponse,
    status_code=status.HTTP_200_OK,
)
async def create_portfolio_report(
    payload: PortfolioReportRequest,
    request: Request,
) -> PortfolioReportResponse:
    """Generate one Backend v1.1 report from a validated v1.0 request."""

    request.state.analysis_id = payload.analysis_id
    runtime = get_report_runtime(request)
    internal_input = runtime.request_mapper.to_internal(payload)
    internal_report = await runtime.report_service.generate(internal_input)
    return runtime.response_mapper.to_wire(
        payload,
        internal_report,
        evaluator_version=runtime.evaluator_version,
    )


__all__ = ["create_portfolio_report", "get_report_runtime", "router"]
