"""Per-IP rate limiting for the API surface.

Cloudflare's zone-scoped rate limiting (15 req/min per IP on ``/api/*``)
cannot be applied to ``*.pages.dev`` hostnames, which share a single
Cloudflare-managed zone. The limit is therefore enforced at the application
layer so the guarantee holds even when the origin is reachable directly
(e.g. through the ``cloudflared`` tunnel). The real client IP is taken from
Cloudflare's ``CF-Connecting-IP`` header when present.
"""

from __future__ import annotations

from collections import deque
from time import monotonic
from typing import TYPE_CHECKING

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

MAX_REQUESTS_PER_MINUTE = 15
_WINDOW_SECONDS = 60.0
_API_PREFIX = "/api/"

# GET endpoints polled by the browser on connect / message send. Exempted from
# the limiter so normal UI usage never trips a 429; state-changing requests
# (POST/DELETE) keep the full protection.
_POLLED_GET_PATHS = frozenset({"/api/v1/models", "/api/v1/documents"})

_hits: dict[str, deque[float]] = {}


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("cf-connecting-ip")
    if not forwarded:
        forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Reject HTTP requests to ``/api/*`` that exceed the per-IP limit."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not request.url.path.startswith(_API_PREFIX):
            return await call_next(request)
        if request.method == "GET" and request.url.path in _POLLED_GET_PATHS:
            return await call_next(request)

        ip = _client_ip(request)
        now = monotonic()
        window = _hits.setdefault(ip, deque())
        while window and now - window[0] >= _WINDOW_SECONDS:
            window.popleft()
        if len(window) >= MAX_REQUESTS_PER_MINUTE:
            return Response(
                status_code=429,
                content='{"detail": "Rate limit exceeded: 15 requests per minute"}',
                media_type="application/json",
            )
        window.append(now)
        if len(_hits) > 10_000:
            _prune_expired(now)
        return await call_next(request)


def _prune_expired(now: float) -> None:
    stale = [
        ip
        for ip, hits in _hits.items()
        if not hits or now - hits[-1] >= _WINDOW_SECONDS
    ]
    for ip in stale:
        _hits.pop(ip, None)
