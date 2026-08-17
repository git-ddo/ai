from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel

from app.core.exceptions import (
    LLMConfigurationError,
    LLMProviderError,
    LLMStructuredOutputError,
)

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class GenerationMetadata:
    """Provider execution details collected around one structured generation."""

    duration_ms: int
    attempt_count: int


@dataclass(frozen=True)
class StructuredGeneration[T: BaseModel]:
    """A validated structured value and the metadata produced with it."""

    value: T
    metadata: GenerationMetadata


@dataclass(frozen=True)
class GenerationCall:
    """One invocation captured by the fake provider for test assertions."""

    system_prompt: str
    user_prompt: str
    response_model: type[BaseModel]


class LLMProvider(Protocol):
    """Provider-neutral asynchronous structured generation contract."""

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> StructuredGeneration[T]: ...

    async def aclose(self) -> None: ...


class FakeLLMProvider:
    """In-memory provider used to develop services without an external LLM."""

    def __init__(
        self,
        response: BaseModel | None = None,
        *,
        error: LLMProviderError | None = None,
    ) -> None:
        if response is None and error is None:
            raise LLMConfigurationError("Fake provider requires a response or an error.")

        self._response = response
        self._error = error
        self._calls: list[GenerationCall] = []
        self._closed = False

    @property
    def calls(self) -> Sequence[GenerationCall]:
        return tuple(self._calls)

    @property
    def call_count(self) -> int:
        return len(self._calls)

    @property
    def closed(self) -> bool:
        return self._closed

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> StructuredGeneration[T]:
        self._calls.append(
            GenerationCall(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=response_model,
            )
        )

        if self._error is not None:
            raise self._error

        if self._response is None or not isinstance(self._response, response_model):
            raise LLMStructuredOutputError(
                "Fake provider response does not match the requested response model.",
                attempt_count=1,
            )

        return StructuredGeneration(
            value=self._response,
            metadata=GenerationMetadata(duration_ms=0, attempt_count=1),
        )

    async def aclose(self) -> None:
        self._closed = True
