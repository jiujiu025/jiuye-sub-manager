"""统一业务异常与全局异常响应。"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class BusinessError(Exception):
    """业务层异常，message 会安全地返回给前端。"""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器，避免向客户端暴露 traceback。"""

    @app.exception_handler(BusinessError)
    async def handle_business_error(_: Request, exc: BusinessError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": "请求参数校验失败", "errors": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        # 记录完整异常供排查，但只返回通用错误信息
        logger.exception("未处理异常", exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})
