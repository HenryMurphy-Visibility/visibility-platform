"""
auth_middleware.py
Visibility Platform — Authentication Middleware

Runs on every request. Checks session token, validates IP,
redirects to /login if not authenticated.

Add to main FastAPI app:
    from auth_middleware import AuthMiddleware
    app.add_middleware(AuthMiddleware)
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, JSONResponse
import auth_manager


# Routes that never require auth
PUBLIC_PATHS = {
    "/login",
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/favicon.ico",
}

# Path prefixes that never require auth (static assets etc)
PUBLIC_PREFIXES = (
    "/static/",
)


class AuthMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        ip   = _get_ip(request)

        # Always allow public paths
        if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
            return await call_next(request)

        # Check IP whitelist first — blocks before even checking session
        if not auth_manager.check_ip(ip):
            # API request — return 403
            if path.startswith("/api/"):
                return JSONResponse(
                    status_code=403,
                    content={"detail": f"IP {ip} not permitted"}
                )
            # Browser request — redirect to login with message
            return RedirectResponse(url="/login?blocked=1", status_code=302)

        # Get session token from cookie
        token = request.cookies.get("visibility_session")

        # Validate session
        user = auth_manager.validate_session(token, ip) if token else None

        if not user:
            # API request — return 401
            if path.startswith("/api/"):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Not authenticated"}
                )
            # Browser request — redirect to login
            return RedirectResponse(
                url=f"/login?next={path}",
                status_code=302
            )

        # Attach user to request state so routes can access it
        request.state.user     = user
        request.state.username = user["username"]
        request.state.role     = user["role"]
        request.state.ip       = ip

        # Log the request (skip high-frequency polling endpoints)
        if not _is_noisy(path):
            auth_manager.log_request(user["username"], ip, path)

        response = await call_next(request)
        return response


def _get_ip(request: Request) -> str:
    """Extract real IP, respecting reverse proxy headers."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def _is_noisy(path: str) -> bool:
    """Skip logging for high-frequency endpoints to keep log clean."""
    noisy = [
        "/api/v1/ops/portfolios",
        "/api/v1/tips",
    ]
    return any(path.startswith(n) for n in noisy)