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

        # 来源(从哪来):优先 referer 路径(前端哪个页面),否则客户端IP。便于日志聚合看"谁调谁"。
        来源 = "-"
        try:
            headers = dict(scope.get("headers") or [])
            ref = headers.get(b"referer") or headers.get(b"referrer")
            if ref:
                from urllib.parse import urlparse
                来源 = urlparse(ref.decode("latin-1", "ignore")).path or "-"
            elif scope.get("client"):
                来源 = str(scope["client"][0])
        except Exception:  # noqa: BLE001
            来源 = "-"

        async def _send_with_log(message):
            if message["type"] == "http.response.start":
                status = message["status"]
                elapsed_ms = int((time.time() - start) * 1000)
                # 格式:从<来源> <method> <path> <status> <ms> —— grep 聚合可看 来源→去向 次数
                logger.info("从%s %s %s %s %dms", 来源, method, path, status, elapsed_ms)
            await send(message)

        await self.app(scope, receive, _send_with_log)
