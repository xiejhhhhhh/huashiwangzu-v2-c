"""Request ID middleware — 每个请求分配唯一 request_id，贯穿所有日志。

在模块日志格式中使用:
    %(asctime)s [%(name)s] %(levelname)s [%(request_id)s] %(message)s

request_id 通过 logging.LogRecord 的 request_id 属性注入。
请求通过 HTTP header X-Request-Id 传回（透传给客户端）。
"""

import uuid
import logging
from contextvars import ContextVar
from starlette.types import ASGIApp, Receive, Scope, Send


logger = logging.getLogger("v2.request_id")
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
_old_record_factory = logging.getLogRecordFactory()


def _record_factory(*args, **kwargs):
    record = _old_record_factory(*args, **kwargs)
    record.request_id = request_id_var.get()
    return record


logging.setLogRecordFactory(_record_factory)


class RequestIdMiddleware:
    """Add a unique request_id to each request and inject into logging."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())[:8]
        token = request_id_var.set(request_id)

        scope["request_id"] = request_id

        # Wrap send to add X-Request-Id header to response
        original_send = send
        headers_sent = False

        async def _send_with_id(message):
            nonlocal headers_sent
            if message["type"] == "http.response.start" and not headers_sent:
                headers_sent = True
                headers = list(message.get("headers", []))
                headers.append((b"X-Request-Id", request_id.encode()))
                message["headers"] = headers
            await original_send(message)

        try:
            await self.app(scope, receive, _send_with_id)
        finally:
            request_id_var.reset(token)
