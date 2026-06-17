from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import FileResponse
from app.config import get_settings
from app.core.exceptions import AppException


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": None,
                "error": exc.message,
                "errors": getattr(exc, "details", None),
            },
        )

    # 统一捕获 HTTPException / StarletteHTTPException，确保所有路由里
    # 路由抛出的 HTTP 异常都返回统一契约 {success, data, error}，
    # 而不是 FastAPI 默认的 {"detail": "..."}。无条件注册，不依赖前端 dist 是否存在。
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        # API 路径统一返回 JSON 契约
        if request.url.path.startswith("/api"):
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "success": False,
                    "data": None,
                    "error": str(exc.detail) or "Not found",
                    "errors": None,
                },
            )
        # 非 API 路径：若前端 dist 存在，SPA 路由的 404 兜底返回 index.html
        frontend_dist: Path | None = app.state.frontend_dist
        if frontend_dist and exc.status_code == 404:
            index = frontend_dist / "index.html"
            if index.exists():
                return FileResponse(str(index))
        # 其余情况返回统一 JSON 契约
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": None,
                "error": str(exc.detail) or "Not found",
                "errors": None,
            },
        )

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(PydanticValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError | PydanticValidationError):
        errors = {}
        for err in exc.errors():
            field = ".".join(str(loc) for loc in err["loc"][1:]) if len(err["loc"]) > 1 else str(err["loc"][0])
            errors[field] = err["msg"]
        return JSONResponse(
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
        settings = get_settings()
        error_message = f"Internal server error: {str(exc)}" if settings.APP_DEBUG else "Internal server error"
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "data": None,
                "error": error_message,
                "errors": None,
            },
        )
