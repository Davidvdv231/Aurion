"""Request-scoped middleware for tracing and security."""

import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Injects a unique request ID into every request/response cycle."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        raw_id = request.headers.get("X-Request-Id", "")
        if raw_id:
            sanitized = re.sub(r"[^a-zA-Z0-9\-_]", "", raw_id)[:64]
            request_id = sanitized if sanitized else uuid.uuid4().hex
        else:
            request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response
