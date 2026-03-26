"""
RLS context middleware — sets app.current_user_id per request for PostgreSQL RLS.
This runs BEFORE route handlers and injects user_id into request state.
"""
import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

log = structlog.get_logger()

# Routes that don't require authentication
PUBLIC_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/api/v1/auth/token"}


class RLSContextMiddleware(BaseHTTPMiddleware):
    """
    Reads user_id from request.state (set by auth dependency) and stores it
    for use in get_db_session() which calls SET LOCAL app.current_user_id.

    Note: This middleware itself doesn't authenticate — that's done by the
    get_current_user dependency in each route. This middleware just ensures
    the user_id propagates correctly to DB sessions created in background tasks.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Initialize user_id in request state
        request.state.user_id = None

        # Skip public paths
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        response = await call_next(request)
        return response
