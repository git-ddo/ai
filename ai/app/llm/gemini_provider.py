import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Protocol, cast

import httpx
from google import genai
from google.genai import errors, types
from pydantic import ValidationError
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.config import Settings
from app.core.exceptions import (
    LLMConfigurationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMServiceError,
    LLMStructuredOutputError,
    LLMTimeoutError,
)
from app.llm.provider import GenerationMetadata, StructuredGeneration, T

logger = logging.getLogger(__name__)

SleepCallable = Callable[[float], Awaitable[None]]
ClockCallable = Callable[[], float]


class _AsyncModels(Protocol):
    async def generate_content(
        self,
        *,
        model: str,
        contents: str,
        config: types.GenerateContentConfig,
    ) -> types.GenerateContentResponse: ...


class _AsyncGeminiClient(Protocol):
    @property
    def models(self) -> _AsyncModels: ...

    async def aclose(self) -> None: ...


class GeminiProvider:
    """Gemini implementation of the provider-neutral structured generation contract."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: _AsyncGeminiClient | None = None,
        sleep: SleepCallable = asyncio.sleep,
        clock: ClockCallable = time.perf_counter,
    ) -> None:
        api_key_secret = settings.gemini_api_key
        api_key = api_key_secret.get_secret_value().strip() if api_key_secret is not None else ""
        model = settings.gemini_model.strip() if settings.gemini_model is not None else ""
        if not api_key:
            raise LLMConfigurationError("Gemini API key is not configured.")
        if not model:
            raise LLMConfigurationError("Gemini model is not configured.")

        self._model = model
        self._thinking_level = types.ThinkingLevel(settings.gemini_thinking_level.upper())
        self._timeout_seconds = settings.llm_timeout_seconds
        self._max_attempts = settings.llm_max_retries + 1
        self._sleep = sleep
        self._clock = clock
        self._closed = False
        self._client_owner: genai.Client | None = None

        if client is None:
            self._client_owner = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    timeout=int(self._timeout_seconds * 1000),
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
            self._client = cast(_AsyncGeminiClient, self._client_owner.aio)
        else:
            self._client = client

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> StructuredGeneration[T]:
        if self._closed:
            raise LLMConfigurationError("Gemini provider is already closed.")

        started_at = self._clock()
        attempt_count = 0

        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception(self._is_retryable),
                stop=stop_after_attempt(self._max_attempts),
                wait=wait_exponential(multiplier=1, min=1, max=8),
                sleep=self._sleep,
                reraise=True,
            ):
                with attempt:
                    attempt_count = attempt.retry_state.attempt_number
                    value = await self._generate_once(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        response_model=response_model,
                        attempt_count=attempt_count,
                    )

            duration_ms = self._duration_ms(started_at)
            logger.info(
                "Gemini structured generation succeeded model=%s duration_ms=%d attempts=%d",
                self._model,
                duration_ms,
                attempt_count,
            )
            return StructuredGeneration(
                value=value,
                metadata=GenerationMetadata(
                    duration_ms=duration_ms,
                    attempt_count=attempt_count,
                ),
            )
        except LLMProviderError as exc:
            logger.warning(
                "Gemini structured generation failed model=%s duration_ms=%d attempts=%d "
                "status_code=%s error_type=%s",
                self._model,
                self._duration_ms(started_at),
                exc.attempt_count or attempt_count,
                exc.status_code,
                type(exc).__name__,
            )
            raise

    async def _generate_once(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        attempt_count: int,
    ) -> T:
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_json_schema=response_model.model_json_schema(),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            thinking_config=types.ThinkingConfig(thinking_level=self._thinking_level),
        )

        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._client.models.generate_content(
                    model=self._model,
                    contents=user_prompt,
                    config=config,
                )
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise LLMTimeoutError(
                "Gemini generation timed out.",
                retryable=True,
                attempt_count=attempt_count,
            ) from exc
        except httpx.TransportError as exc:
            raise LLMServiceError(
                "Gemini transport request failed.",
                retryable=False,
                attempt_count=attempt_count,
            ) from exc
        except errors.APIError as exc:
            raise self._translate_api_error(exc, attempt_count=attempt_count) from exc

        return self._parse_response(
            response=response,
            response_model=response_model,
            attempt_count=attempt_count,
        )

    @staticmethod
    def _parse_response(
        *,
        response: types.GenerateContentResponse,
        response_model: type[T],
        attempt_count: int,
    ) -> T:
        parsed = response.parsed
        if isinstance(parsed, response_model):
            return parsed
        if parsed is not None:
            try:
                return response_model.model_validate(parsed)
            except ValidationError as exc:
                raise LLMStructuredOutputError(
                    "Gemini returned an invalid structured response.",
                    attempt_count=attempt_count,
                ) from exc

        text = response.text
        if text is None or not text.strip():
            raise LLMStructuredOutputError(
                "Gemini returned an empty structured response.",
                attempt_count=attempt_count,
            )

        try:
            return response_model.model_validate_json(text)
        except ValidationError as exc:
            raise LLMStructuredOutputError(
                "Gemini returned an invalid structured response.",
                attempt_count=attempt_count,
            ) from exc

    @staticmethod
    def _translate_api_error(
        error: errors.APIError,
        *,
        attempt_count: int,
    ) -> LLMProviderError:
        status_code = error.code
        if status_code == 408:
            return LLMTimeoutError(
                "Gemini request timed out.",
                retryable=True,
                attempt_count=attempt_count,
                status_code=status_code,
            )
        if status_code == 429:
            return LLMRateLimitError(
                "Gemini rate limit was reached.",
                retryable=True,
                attempt_count=attempt_count,
                status_code=status_code,
            )
        if 500 <= status_code <= 599:
            return LLMServiceError(
                "Gemini service is temporarily unavailable.",
                retryable=True,
                attempt_count=attempt_count,
                status_code=status_code,
            )
        return LLMServiceError(
            "Gemini rejected the generation request.",
            retryable=False,
            attempt_count=attempt_count,
            status_code=status_code,
        )

    @staticmethod
    def _is_retryable(error: BaseException) -> bool:
        return isinstance(error, LLMProviderError) and error.retryable

    def _duration_ms(self, started_at: float) -> int:
        return max(0, round((self._clock() - started_at) * 1000))

    async def aclose(self) -> None:
        if self._closed:
            return

        self._closed = True
        try:
            await self._client.aclose()
        finally:
            if self._client_owner is not None:
                self._client_owner.close()
