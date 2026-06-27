import logging
import time
from starlette.types import ASGIApp, Receive, Scope, Send


logger = logging.getLogger("v2.request")


class RequestLoggingMiddleware:
    """Log every request with method, path, status code, and duration."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "?")
        path = scope.get("path", "?")
        start = time.time()

        async def _send_with_log(message):
            if message["type"] == "http.response.start":
                status = message["status"]
                elapsed_ms = int((time.time() - start) * 1000)
                logger.info("%s %s %s %dms", method, path, status, elapsed_ms)
            await send(message)

        await self.app(scope, receive, _send_with_log)
