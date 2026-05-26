"""
auth_routes.py
Visibility Platform — Authentication Routes

Endpoints:
  POST /api/v1/auth/login       — authenticate, set session cookie
  POST /api/v1/auth/logout      — clear session cookie
  GET  /api/v1/auth/me          — current user info
  GET  /api/v1/auth/sessions    — admin: all active sessions
  GET  /api/v1/auth/log         — admin: access log
  GET  /api/v1/auth/users       — admin: all users
  POST /api/v1/auth/users       — admin: create user
  POST /api/v1/auth/users/{u}/deactivate  — admin: deactivate user
  POST /api/v1/auth/users/{u}/resetpw     — admin: reset password
  GET  /api/v1/auth/whitelist   — admin: view IP whitelist
  POST /api/v1/auth/whitelist   — admin: add IP
  DELETE /api/v1/auth/whitelist/{ip}      — admin: remove IP

Add to main FastAPI app:
    from auth_routes import auth_router
    app.include_router(auth_router)
"""

from fastapi import APIRouter, Request, Response, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
import auth_manager

auth_router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


# ============================================================
# MODELS
# ============================================================

class LoginRequest(BaseModel):
    username: str
    password: str

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role:     str = "user"

class ResetPasswordRequest(BaseModel):
    new_password: str


# ============================================================
# HELPERS
# ============================================================

def _require_admin(request: Request) -> None:
    role = getattr(request.state, "role", None)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ============================================================
# LOGIN / LOGOUT
# ============================================================

@auth_router.post("/login")
def login(body: LoginRequest, request: Request, response: Response):
    ip = _get_ip(request)
    try:
        result = auth_manager.authenticate(body.username, body.password, ip)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    # Set session cookie — httponly so JS can't read it
    response.set_cookie(
        key      = "visibility_session",
        value    = result["token"],
        httponly = True,
        samesite = "lax",
        max_age  = auth_manager.SESSION_TTL_HOURS * 3600,
    )

    return {
        "status":   "ok",
        "username": result["username"],
        "role":     result["role"],
    }


@auth_router.post("/logout")
def logout(request: Request, response: Response):
    token    = request.cookies.get("visibility_session")
    username = getattr(request.state, "username", "unknown")
    ip       = _get_ip(request)

    if token:
        auth_manager.logout(token, username, ip)

    response.delete_cookie("visibility_session")
    return {"status": "logged out"}


# ============================================================
# CURRENT USER
# ============================================================

@auth_router.get("/me")
def get_me(request: Request):
    return {
        "username": getattr(request.state, "username", None),
        "role":     getattr(request.state, "role",     None),
        "ip":       getattr(request.state, "ip",       None),
    }


# ============================================================
# ADMIN — SESSIONS
# ============================================================

@auth_router.get("/sessions")
def get_sessions(request: Request):
    _require_admin(request)
    return {"sessions": auth_manager.list_sessions()}


# ============================================================
# ADMIN — ACCESS LOG
# ============================================================

@auth_router.get("/log")
def get_log(request: Request,
            limit:    int           = Query(100, ge=1, le=10000),
            username: Optional[str] = Query(None)):
    _require_admin(request)
    return {"log": auth_manager.get_access_log(limit=limit, username=username)}


# ============================================================
# ADMIN — USER MANAGEMENT
# ============================================================

@auth_router.get("/users")
def get_users(request: Request):
    _require_admin(request)
    return {"users": auth_manager.list_users()}


@auth_router.post("/users")
def create_user(body: CreateUserRequest, request: Request):
    _require_admin(request)
    try:
        result = auth_manager.create_user(
            username   = body.username,
            password   = body.password,
            role       = body.role,
            created_by = request.state.username,
        )
        return {"status": "created", "user": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@auth_router.post("/users/{username}/deactivate")
def deactivate_user(username: str, request: Request):
    _require_admin(request)
    if username == request.state.username:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
    try:
        auth_manager.deactivate_user(username)
        return {"status": "deactivated", "username": username}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@auth_router.post("/users/{username}/resetpw")
def reset_password(username: str, body: ResetPasswordRequest, request: Request):
    _require_admin(request)
    try:
        auth_manager.set_password(username, body.new_password)
        return {"status": "password reset", "username": username}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================
# ADMIN — IP WHITELIST
# ============================================================

@auth_router.get("/whitelist")
def get_whitelist(request: Request):
    _require_admin(request)
    from pathlib import Path
    import json
    wl_path = auth_manager.AUTH_DIR / "ip_whitelist.json"
    with open(wl_path) as f:
        whitelist = json.load(f)
    return {"whitelist": whitelist, "note": "Empty list means allow all IPs"}


@auth_router.post("/whitelist")
def add_whitelist(request: Request, ip: str = Query(...)):
    _require_admin(request)
    auth_manager.add_to_whitelist(ip)
    return {"status": "added", "ip": ip}


@auth_router.delete("/whitelist/{ip}")
def remove_whitelist(ip: str, request: Request):
    _require_admin(request)
    auth_manager.remove_from_whitelist(ip)
    return {"status": "removed", "ip": ip}