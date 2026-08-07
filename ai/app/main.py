from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import get_settings

APP_VERSION = "0.1.0"


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, version=APP_VERSION)
    application.include_router(health_router)
    return application


app = create_app()
