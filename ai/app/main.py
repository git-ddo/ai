from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.error_handlers import register_exception_handlers
from app.api.health import router as health_router
from app.api.reports import router as reports_router
from app.core.config import Settings, get_settings
from app.core.runtime import (
    ProviderFactory,
    ReportRuntime,
    build_report_runtime,
)
from app.llm import GeminiProvider

APP_VERSION = "0.1.0"


def create_app(
    *,
    runtime: ReportRuntime | None = None,
    settings: Settings | None = None,
    provider_factory: ProviderFactory = GeminiProvider,
) -> FastAPI:
    application_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        provider = None
        try:
            active_runtime = runtime
            if active_runtime is None:
                provider = provider_factory(application_settings)
                active_runtime = build_report_runtime(application_settings, provider)
            application.state.report_runtime = active_runtime
            yield
        finally:
            if hasattr(application.state, "report_runtime"):
                del application.state.report_runtime
            if provider is not None:
                await provider.aclose()

    application = FastAPI(
        title=application_settings.app_name,
        version=APP_VERSION,
        lifespan=lifespan,
    )
    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(reports_router)
    return application


app = create_app()
