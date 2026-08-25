from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or a local .env file."""

    app_name: str = Field(default="git-ddo-ai", validation_alias="APP_NAME")
    app_env: str = Field(default="local", validation_alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", validation_alias="APP_HOST")
    app_port: int = Field(default=8000, validation_alias="APP_PORT")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    gemini_api_key: SecretStr | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    gemini_model: str | None = Field(default=None, validation_alias="GEMINI_MODEL")
    llm_timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        le=600,
        validation_alias="LLM_TIMEOUT_SECONDS",
    )
    llm_max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        validation_alias="LLM_MAX_RETRIES",
    )
    ai_analysis_deadline_seconds: float = Field(
        default=270.0,
        gt=0,
        le=300,
        validation_alias="AI_ANALYSIS_DEADLINE_SECONDS",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return one cached settings instance for the application process."""

    return Settings()
