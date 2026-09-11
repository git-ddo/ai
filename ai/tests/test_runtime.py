from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.exceptions import LLMConfigurationError
from app.core.runtime import ReportRuntime
from app.domain import InternalPortfolioInput, InternalPortfolioReport
from app.llm import StructuredGeneration
from app.main import create_app
from app.mappers import RequestWireMapper, ResponseWireMapper
from app.prompts import SYSTEM_PROMPT_VERSION


class _UnusedReportService:
    async def generate(
        self,
        portfolio: InternalPortfolioInput,
        *,
        question_count: int = 5,
        statement_count: int = 6,
    ) -> InternalPortfolioReport:
        raise AssertionError("Report service must not be called in this lifecycle test")


class _TrackingProvider:
    def __init__(self) -> None:
        self.close_count = 0

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[Any],
    ) -> StructuredGeneration[Any]:
        raise AssertionError("Gemini generation must not run in this lifecycle test")

    async def aclose(self) -> None:
        self.close_count += 1


def _settings(*, api_key: str = "test-api-key", model: str = "test-model") -> Settings:
    return Settings(
        _env_file=None,
        GEMINI_API_KEY=api_key,
        GEMINI_MODEL=model,
        AI_ANALYSIS_DEADLINE_SECONDS=120,
    )


def _injected_runtime() -> ReportRuntime:
    return ReportRuntime(
        report_service=_UnusedReportService(),
        request_mapper=RequestWireMapper(),
        response_mapper=ResponseWireMapper(),
        evaluator_version="injected-model:prompt-version",
    )


def test_provider_is_created_only_during_lifespan_and_closed_once() -> None:
    provider = _TrackingProvider()
    factory_calls: list[Settings] = []

    def factory(settings: Settings) -> _TrackingProvider:
        factory_calls.append(settings)
        return provider

    app = create_app(settings=_settings(), provider_factory=factory)
    assert factory_calls == []

    with TestClient(app) as client:
        assert len(factory_calls) == 1
        runtime = client.app.state.report_runtime
        first_runtime_id = id(runtime)
        assert client.get("/health").status_code == 200
        assert client.get("/health").status_code == 200
        assert id(client.app.state.report_runtime) == first_runtime_id
        assert provider.close_count == 0

    assert provider.close_count == 1


def test_production_runtime_uses_model_prompt_version_and_safe_deadline() -> None:
    provider = _TrackingProvider()
    settings = _settings(api_key="never-expose-this-key", model="gemini-test-model")
    app = create_app(settings=settings, provider_factory=lambda _settings: provider)

    with TestClient(app) as client:
        runtime = client.app.state.report_runtime
        assert runtime.evaluator_version == f"gemini-test-model:{SYSTEM_PROMPT_VERSION}"
        assert "never-expose-this-key" not in repr(runtime)


def test_injected_runtime_skips_provider_and_needs_no_api_key() -> None:
    factory_calls = 0

    def forbidden_factory(_settings: Settings) -> _TrackingProvider:
        nonlocal factory_calls
        factory_calls += 1
        raise AssertionError("Injected runtime must bypass provider creation")

    settings = Settings(_env_file=None, GEMINI_API_KEY=None, GEMINI_MODEL=None)
    with TestClient(
        create_app(
            runtime=_injected_runtime(),
            settings=settings,
            provider_factory=forbidden_factory,
        )
    ) as client:
        assert client.get("/health").json() == {"status": "UP"}

    assert factory_calls == 0


def test_blank_evaluator_version_is_rejected_without_sensitive_data() -> None:
    with pytest.raises(LLMConfigurationError) as captured:
        ReportRuntime(
            report_service=_UnusedReportService(),
            request_mapper=RequestWireMapper(),
            response_mapper=ResponseWireMapper(),
            evaluator_version="   ",
        )

    assert "test-api-key" not in str(captured.value)


def test_startup_configuration_error_does_not_expose_api_key() -> None:
    api_key = "startup-secret-api-key"
    app = create_app(settings=_settings(api_key=api_key, model=""))

    with pytest.raises(LLMConfigurationError) as captured:
        with TestClient(app):
            pass

    assert api_key not in str(captured.value)


def test_provider_is_closed_when_runtime_build_fails_after_creation() -> None:
    provider = _TrackingProvider()
    app = create_app(
        settings=_settings(model=""),
        provider_factory=lambda _settings: provider,
    )

    with pytest.raises(LLMConfigurationError):
        with TestClient(app):
            pass

    assert provider.close_count == 1
