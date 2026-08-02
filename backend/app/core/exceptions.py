"""业务异常基类与常用异常"""
from  http import HTTPStatus


class AppException(Exception):
    """业务异常基类"""

    code: str = "internal_error"
    message: str = "服务内部错误"
    http_status: int = HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        super().__init__(message)

class NotFoundError(AppException):
    code = "not_found"
    message = "资源不存在"
    http_status = HTTPStatus.NOT_FOUND

class PermissionError(AppException):
    code = "permission_denied"
    message = "无权访问资源"
    http_status = HTTPStatus.FORBIDDEN

class ConfigurationError(AppException):
    code = "configuration_error"
    message = "服务器配置缺失"
    http_status = HTTPStatus.SERVICE_UNAVAILABLE