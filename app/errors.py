"""CRM V2 错误处理模块。

定义 ApiError 异常类及其处理器，用于统一错误响应格式。
"""

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Any


class ApiError(HTTPException):
    """CRM 通用异常类，用于封装业务错误。

    Args:
        status_code: HTTP 状态码
        code: 错误码，用于前端分支处理
        message: 错误信息，人类可读
        **extra: 额外的错误信息
    """

    def __init__(self, status_code: int, code: str, message: str, **extra: Any):
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.extra = extra


def install_error_handler(app) -> None:
    """为 FastAPI 应用安装全局错误处理器。

    Args:
        app: FastAPI 应用实例
    """
    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        """处理 ApiError 异常，返回统一格式的错误响应。"""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "code": exc.code,
                **exc.extra,
            }
        )