from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse
from pydantic import ValidationError as PydanticValidationError
from app.core.exceptions import AppException


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        return ORJSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": None,
                "error": exc.message,
                "errors": getattr(exc, "details", None),
            },
        )

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(PydanticValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError | PydanticValidationError):
        errors = {}
        for err in exc.errors():
            field = ".".join(str(loc) for loc in err["loc"][1:]) if len(err["loc"]) > 1 else str(err["loc"][0])
            errors[field] = err["msg"]
        return ORJSONResponse(
            status_code=422,
            content={
                "success": False,
                "data": None,
                "error": "Validation failed",
                "errors": errors,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        return ORJSONResponse(
            status_code=500,
            content={
                "success": False,
                "data": None,
                "error": f"Internal server error: {str(exc)}",
                "errors": None,
            },
        )
