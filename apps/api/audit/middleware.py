"""Request-scoped correlation id and structlog context."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from audit.request_id import generate_request_id_v7


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign UUIDv7 request_id, expose it on request.state, and bind structlog keys."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = generate_request_id_v7()
        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(
            request_id=str(request_id),
            http_method=request.method,
            http_path=request.url.path,
        )
        try:
            return await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars(
                "request_id",
                "http_method",
                "http_path",
            )
