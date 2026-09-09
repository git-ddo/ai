from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.mappers import ErrorWireMapper, MappedAnalysisError


def register_exception_handlers(
    app: FastAPI,
    *,
    mapper: ErrorWireMapper | None = None,
) -> None:
    """Register safe Backend error-envelope handlers on one FastAPI app."""

    error_mapper = mapper if mapper is not None else ErrorWireMapper()

    async def request_validation_handler(
        _request: Request,
        error: Exception,
    ) -> JSONResponse:
        return _to_json_response(error_mapper.to_wire(error, analysis_id=None))

    async def internal_exception_handler(
        request: Request,
        error: Exception,
    ) -> JSONResponse:
        analysis_id = _get_trusted_analysis_id(request)
        return _to_json_response(error_mapper.to_wire(error, analysis_id=analysis_id))

    app.add_exception_handler(RequestValidationError, request_validation_handler)
    app.add_exception_handler(Exception, internal_exception_handler)


def _get_trusted_analysis_id(request: Request) -> UUID | None:
    analysis_id = getattr(request.state, "analysis_id", None)
    return analysis_id if isinstance(analysis_id, UUID) else None


def _to_json_response(mapped: MappedAnalysisError) -> JSONResponse:
    return JSONResponse(
        status_code=mapped.status_code,
        content=mapped.body.model_dump(mode="json", by_alias=True),
    )


__all__ = ["register_exception_handlers"]
