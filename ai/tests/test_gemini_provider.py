import asyncio
from typing import Any

import httpx
import pytest
from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from app.core.config import Settings
from app.core.exceptions import (
    LLMConfigurationError,
    LLMRateLimitError,
    LLMServiceError,
    LLMStructuredOutputError,
    LLMTimeoutError,
)
from app.llm import FakeLLMProvider, GeminiProvider


class ExampleResponse(BaseModel):
    summary: str


class OtherResponse(BaseModel):
    value: int


class StubModels:
    def __init__(self, outcomes: list[types.GenerateContentResponse | BaseException]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    async def generate_content(
        self,
        *,
        model: str,
        contents: str,
        config: types.GenerateContentConfig,
    ) -> types.GenerateContentResponse:
        self.calls.append({"model": model, "contents": contents, "config": config})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class BlockingModels(StubModels):
    async def generate_content(
        self,
        *,
        model: str,
        contents: str,
        config: types.GenerateContentConfig,
    ) -> types.GenerateContentResponse:
        self.calls.append({"model": model, "contents": contents, "config": config})
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class StubAsyncClient:
    def __init__(self, models: StubModels) -> None:
        self.models = models
        self.close_count = 0

    async def aclose(self) -> None:
        self.close_count += 1


def make_settings(
    *,
    api_key: str | None = "test-secret-key",
    model: str | None = "test-gemini-model",
    timeout: float = 1.0,
    max_retries: int = 2,
    thinking_level: str = "medium",
) -> Settings:
    values: dict[str, object] = {
        "GEMINI_API_KEY": api_key,
        "GEMINI_MODEL": model,
        "LLM_TIMEOUT_SECONDS": timeout,
        "LLM_MAX_RETRIES": max_retries,
        "GEMINI_THINKING_LEVEL": thinking_level,
    }
    return Settings.model_validate(values)


def response_with_text(text: str) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(parts=[types.Part(text=text)]),
            )
        ]
    )


def api_error(
    status_code: int,
    message: str = "upstream detail must stay private",
) -> errors.APIError:
    return errors.APIError(
        status_code,
        {"error": {"code": status_code, "message": message}},
    )


async def no_sleep(_: float) -> None:
    return None


@pytest.mark.asyncio
async def test_returns_parsed_pydantic_structured_output() -> None:
    models = StubModels([types.GenerateContentResponse(parsed=ExampleResponse(summary="grounded"))])
    provider = GeminiProvider(make_settings(), client=StubAsyncClient(models))

    result = await provider.generate_structured("system policy", "user data", ExampleResponse)

    assert result.value == ExampleResponse(summary="grounded")
    assert result.metadata.attempt_count == 1
    assert result.metadata.duration_ms >= 0


@pytest.mark.asyncio
async def test_falls_back_to_validating_response_text() -> None:
    models = StubModels([response_with_text('{"summary":"from text"}')])
    provider = GeminiProvider(make_settings(), client=StubAsyncClient(models))

    result = await provider.generate_structured("system", "user", ExampleResponse)

    assert result.value.summary == "from text"


@pytest.mark.asyncio
async def test_validates_parsed_json_object_as_requested_model() -> None:
    response = types.GenerateContentResponse.model_construct(parsed={"summary": "from object"})
    models = StubModels([response])
    provider = GeminiProvider(make_settings(), client=StubAsyncClient(models))

    result = await provider.generate_structured("system", "user", ExampleResponse)

    assert result.value == ExampleResponse(summary="from object")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        response_with_text(""),
        response_with_text("not-json"),
        response_with_text('{"unexpected":"field"}'),
        types.GenerateContentResponse(parsed=OtherResponse(value=1)),
    ],
)
async def test_rejects_empty_invalid_or_mismatched_structured_output(
    response: types.GenerateContentResponse,
) -> None:
    models = StubModels([response])
    provider = GeminiProvider(
        make_settings(max_retries=2),
        client=StubAsyncClient(models),
        sleep=no_sleep,
    )

    with pytest.raises(LLMStructuredOutputError) as raised:
        await provider.generate_structured("system", "user", ExampleResponse)

    assert raised.value.retryable is False
    assert raised.value.attempt_count == 1
    assert len(models.calls) == 1
    assert "not-json" not in str(raised.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [408, 429, 500, 503])
async def test_retries_retryable_api_errors_then_succeeds(status_code: int) -> None:
    models = StubModels(
        [
            api_error(status_code),
            types.GenerateContentResponse(parsed=ExampleResponse(summary="recovered")),
        ]
    )
    provider = GeminiProvider(
        make_settings(max_retries=2),
        client=StubAsyncClient(models),
        sleep=no_sleep,
    )

    result = await provider.generate_structured("system", "user", ExampleResponse)

    assert result.value.summary == "recovered"
    assert result.metadata.attempt_count == 2
    assert len(models.calls) == 2


@pytest.mark.asyncio
async def test_timeout_is_retried_then_succeeds() -> None:
    models = StubModels(
        [
            TimeoutError(),
            types.GenerateContentResponse(parsed=ExampleResponse(summary="after timeout")),
        ]
    )
    provider = GeminiProvider(
        make_settings(max_retries=1),
        client=StubAsyncClient(models),
        sleep=no_sleep,
    )

    result = await provider.generate_structured("system", "user", ExampleResponse)

    assert result.metadata.attempt_count == 2
    assert result.value.summary == "after timeout"


@pytest.mark.asyncio
async def test_httpx_timeout_is_converted_and_retried() -> None:
    models = StubModels(
        [
            httpx.ReadTimeout("transport timeout"),
            types.GenerateContentResponse(
                parsed=ExampleResponse(summary="after transport timeout")
            ),
        ]
    )
    provider = GeminiProvider(
        make_settings(max_retries=1),
        client=StubAsyncClient(models),
        sleep=no_sleep,
    )

    result = await provider.generate_structured("system", "user", ExampleResponse)

    assert result.metadata.attempt_count == 2
    assert result.value.summary == "after transport timeout"


@pytest.mark.asyncio
async def test_httpx_connection_error_is_converted_without_retry() -> None:
    models = StubModels([httpx.ConnectError("connection failed")])
    provider = GeminiProvider(
        make_settings(max_retries=2),
        client=StubAsyncClient(models),
        sleep=no_sleep,
    )

    with pytest.raises(LLMServiceError) as raised:
        await provider.generate_structured("system", "user", ExampleResponse)

    assert raised.value.retryable is False
    assert raised.value.attempt_count == 1
    assert len(models.calls) == 1
    assert "connection failed" not in str(raised.value)


@pytest.mark.asyncio
async def test_async_timeout_guard_raises_internal_timeout_error() -> None:
    models = BlockingModels([])
    provider = GeminiProvider(
        make_settings(timeout=0.001, max_retries=0),
        client=StubAsyncClient(models),
        sleep=no_sleep,
    )

    with pytest.raises(LLMTimeoutError) as raised:
        await provider.generate_structured("system", "user", ExampleResponse)

    assert raised.value.attempt_count == 1
    assert raised.value.retryable is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [(408, LLMTimeoutError), (429, LLMRateLimitError), (500, LLMServiceError)],
)
async def test_retry_limit_is_honored(
    status_code: int,
    expected_error: type[LLMRateLimitError] | type[LLMServiceError],
) -> None:
    models = StubModels([api_error(status_code), api_error(status_code), api_error(status_code)])
    provider = GeminiProvider(
        make_settings(max_retries=2),
        client=StubAsyncClient(models),
        sleep=no_sleep,
    )

    with pytest.raises(expected_error) as raised:
        await provider.generate_structured("system", "user", ExampleResponse)

    assert raised.value.attempt_count == 3
    assert len(models.calls) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 401, 403, 404])
async def test_non_retryable_api_errors_fail_immediately(status_code: int) -> None:
    models = StubModels([api_error(status_code)])
    provider = GeminiProvider(
        make_settings(max_retries=2),
        client=StubAsyncClient(models),
        sleep=no_sleep,
    )

    with pytest.raises(LLMServiceError) as raised:
        await provider.generate_structured("system", "user", ExampleResponse)

    assert raised.value.retryable is False
    assert raised.value.status_code == status_code
    assert raised.value.attempt_count == 1
    assert len(models.calls) == 1


@pytest.mark.asyncio
async def test_passes_separate_prompts_and_json_schema_to_gemini() -> None:
    models = StubModels([types.GenerateContentResponse(parsed=ExampleResponse(summary="ok"))])
    provider = GeminiProvider(make_settings(), client=StubAsyncClient(models))

    await provider.generate_structured("system policy", "untrusted user data", ExampleResponse)

    call = models.calls[0]
    config = call["config"]
    assert call["model"] == "test-gemini-model"
    assert call["contents"] == "untrusted user data"
    assert config.system_instruction == "system policy"
    assert config.response_mime_type == "application/json"
    assert config.response_schema is None
    assert config.response_json_schema == ExampleResponse.model_json_schema()
    assert config.automatic_function_calling is not None
    assert config.automatic_function_calling.disable is True
    assert config.thinking_config is not None
    assert config.thinking_config.thinking_level is types.ThinkingLevel.MEDIUM


@pytest.mark.asyncio
async def test_passes_configured_thinking_level_to_gemini() -> None:
    models = StubModels([types.GenerateContentResponse(parsed=ExampleResponse(summary="ok"))])
    provider = GeminiProvider(
        make_settings(thinking_level="minimal"),
        client=StubAsyncClient(models),
    )

    await provider.generate_structured("system", "user", ExampleResponse)

    thinking_config = models.calls[0]["config"].thinking_config
    assert thinking_config is not None
    assert thinking_config.thinking_level is types.ThinkingLevel.MINIMAL


@pytest.mark.asyncio
async def test_does_not_log_api_key_prompts_or_upstream_response(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "test-secret-key"
    system_prompt = "private-system-prompt"
    user_prompt = "private-user-prompt"
    models = StubModels([api_error(400, f"upstream contained {secret}")])
    provider = GeminiProvider(make_settings(api_key=secret), client=StubAsyncClient(models))
    caplog.set_level("INFO")

    with pytest.raises(LLMServiceError):
        await provider.generate_structured(system_prompt, user_prompt, ExampleResponse)

    assert secret not in caplog.text
    assert system_prompt not in caplog.text
    assert user_prompt not in caplog.text
    assert "upstream contained" not in caplog.text


def test_initializes_official_client_with_secret_and_sdk_retries_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    async_client = StubAsyncClient(StubModels([]))

    class StubClientOwner:
        aio = async_client

        def close(self) -> None:
            return None

    def client_factory(**kwargs: object) -> StubClientOwner:
        captured.update(kwargs)
        return StubClientOwner()

    monkeypatch.setattr(genai, "Client", client_factory)

    GeminiProvider(make_settings(api_key="  test-secret-key  ", timeout=12.5))

    assert captured["api_key"] == "test-secret-key"
    http_options = captured["http_options"]
    assert isinstance(http_options, types.HttpOptions)
    assert http_options.timeout == 12_500
    assert http_options.retry_options is not None
    assert http_options.retry_options.attempts == 1


@pytest.mark.parametrize(
    "settings",
    [
        make_settings(api_key=None),
        make_settings(api_key=""),
        make_settings(model=None),
        make_settings(model=""),
    ],
)
def test_rejects_missing_api_key_or_model_without_leaking_secret(settings: Settings) -> None:
    with pytest.raises(LLMConfigurationError) as raised:
        GeminiProvider(settings)

    assert "test-secret-key" not in str(raised.value)
    assert "test-secret-key" not in repr(settings)


@pytest.mark.asyncio
async def test_aclose_closes_injected_async_client_once() -> None:
    client = StubAsyncClient(StubModels([]))
    provider = GeminiProvider(make_settings(), client=client)

    await provider.aclose()
    await provider.aclose()

    assert client.close_count == 1
    with pytest.raises(LLMConfigurationError):
        await provider.generate_structured("system", "user", ExampleResponse)


@pytest.mark.asyncio
async def test_fake_provider_returns_configured_value_and_records_calls() -> None:
    response = ExampleResponse(summary="fake")
    provider = FakeLLMProvider(response)

    result = await provider.generate_structured("system", "user", ExampleResponse)
    await provider.aclose()

    assert result.value is response
    assert result.metadata.duration_ms == 0
    assert result.metadata.attempt_count == 1
    assert provider.call_count == 1
    assert provider.calls[0].system_prompt == "system"
    assert provider.calls[0].user_prompt == "user"
    assert provider.calls[0].response_model is ExampleResponse
    assert provider.closed is True


@pytest.mark.asyncio
async def test_fake_provider_raises_configured_error() -> None:
    configured_error = LLMTimeoutError(
        "simulated timeout",
        retryable=True,
        attempt_count=1,
    )
    provider = FakeLLMProvider(error=configured_error)

    with pytest.raises(LLMTimeoutError) as raised:
        await provider.generate_structured("system", "user", ExampleResponse)

    assert raised.value is configured_error
    assert provider.call_count == 1


@pytest.mark.asyncio
async def test_fake_provider_rejects_response_model_mismatch() -> None:
    provider = FakeLLMProvider(OtherResponse(value=1))

    with pytest.raises(LLMStructuredOutputError):
        await provider.generate_structured("system", "user", ExampleResponse)


@pytest.mark.parametrize(
    "values",
    [
        {"LLM_TIMEOUT_SECONDS": 0},
        {"LLM_MAX_RETRIES": -1},
        {"LLM_MAX_RETRIES": 6},
        {"GEMINI_THINKING_LEVEL": "invalid"},
    ],
)
def test_settings_reject_invalid_timeout_and_retry_bounds(values: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        Settings.model_validate(values)


@pytest.mark.asyncio
async def test_duration_uses_total_elapsed_time() -> None:
    clock_values = iter([10.0, 10.125])

    def clock() -> float:
        return next(clock_values)

    provider = GeminiProvider(
        make_settings(),
        client=StubAsyncClient(
            StubModels([types.GenerateContentResponse(parsed=ExampleResponse(summary="timed"))])
        ),
        clock=clock,
    )

    result = await provider.generate_structured("system", "user", ExampleResponse)

    assert result.metadata.duration_ms == 125
