import logging
import time
import uuid
from starlette.types import ASGIApp, Receive, Scope, Send

from app.services import trace_store


logger = logging.getLogger("v2.request")


class RequestLoggingMiddleware:
    """Log every request with method, path, status code, and duration.

    Also generates/extracts a trace_id from the X-Request-Id header,
    creates a root span, and stores the trace context in trace_store's
    contextvar for full-trace propagation through call_capability /
    emit_module_event.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "?")
        path = scope.get("path", "?")
        start = time.time()

        # ---- trace_id: read from header or generate ----
        headers = dict(scope.get("headers", []))
        trace_id = None
        for k, v in headers.items():
            if k.decode("utf-8", errors="replace").lower() == "x-request-id":
                trace_id = v.decode("utf-8", errors="replace").strip()
                break
        if not trace_id:
            trace_id = uuid.uuid4().hex[:16]

        # Create root span for this request
        root_span_id = await trace_store.start_span(
            span_name=f"{method} {path}",
            trace_id=trace_id,
            metadata={"method": method, "path": path},
            owner_id=0,
        )

        # Store trace context so call_capability / emit_module_event pick it up
        ctx = trace_store.SpanContext(trace_id=trace_id, span_id=root_span_id)
        token = trace_store.set_trace_ctx(ctx)

        scope["trace_id"] = trace_id

        async def _send_with_log(message):
            if message["type"] == "http.response.start":
                status = message["status"]
                elapsed_ms = int((time.time() - start) * 1000)
                logger.info("%s %s %s %dms", method, path, status, elapsed_ms)
            await send(message)

        try:
            await self.app(scope, receive, _send_with_log)
        except Exception as exc:
            await trace_store.end_span(root_span_id, status="error", error=str(exc))
            raise
        else:
            await trace_store.end_span(root_span_id, status="ok")
        finally:
            trace_store.reset_trace_ctx(token)
