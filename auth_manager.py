"""
auth_manager.py
Visibility Platform — Authentication Manager

Handles all auth state: users, sessions, IP whitelist, access log.
No FastAPI dependencies — pure Python, fully testable standalone.

Storage layout (all under chest/auth/):
  users.json          — registered users + hashed passwords
  sessions.json       — active sessions
  ip_whitelist.json   — allowed IPs (empty list = allow all)
  access_log.csv      — every login attempt + every request
"""

import json
import csv
import os
import secrets
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import bcrypt


# ============================================================
# CONFIG
# ============================================================

SESSION_TTL_HOURS   = 12     # session expires after 12h idle
MAX_LOGIN_ATTEMPTS  = 5      # lockout after N failures
LOCKOUT_MINUTES     = 15     # lockout duration
AUTH_DIR            = None   # set by init_auth()


# ============================================================
# INIT
# ============================================================

def init_auth(chest_path: str) -> None:
    """
    Call once at startup — creates auth directory and default files.
    chest_path: the root chest directory (same as FUNDS_PATH parent).
    """
    global AUTH_DIR
    AUTH_DIR = Path(chest_path) / "admin" / "auth"
    AUTH_DIR.mkdir(parents=True, exist_ok=True)

    # Create default files if they don't exist
    _ensure_file("users.json",       {})
    _ensure_file("sessions.json",    {})
    _ensure_file("ip_whitelist.json", [])

    # Create access log with header if needed
    log_path = AUTH_DIR / "access_log.csv"
    if not log_path.exists():
        with open(log_path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=[
                "timestamp", "event", "username", "ip",
                "endpoint", "success", "detail"
            ]).writeheader()

    print(f">>> AUTH INITIALIZED | {AUTH_DIR}")


def _ensure_file(name: str, default) -> None:
    path = AUTH_DIR / name
    if not path.exists():
        with open(path, "w") as f:
            json.dump(default, f, indent=2)


# ============================================================
# USER MANAGEMENT
# ============================================================

def _load_users() -> dict:
    with open(AUTH_DIR / "users.json") as f:
        return json.load(f)

def _save_users(users: dict) -> None:
    with open(AUTH_DIR / "users.json", "w") as f:
        json.dump(users, f, indent=2)


def create_user(username: str, password: str, role: str = "user",
                created_by: str = "admin") -> dict:
    """
    Create a new user. Password is hashed with bcrypt.
    Roles: 'admin' | 'user'
    """
    users = _load_users()
    if username in users:
        raise ValueError(f"User '{username}' already exists")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    users[username] = {
        "username":    username,
        "password":    hashed,
        "role":        role,
        "created_at":  datetime.now().isoformat(),
        "created_by":  created_by,
        "active":      True,
        "last_login":  None,
        "login_attempts": 0,
        "locked_until":   None,
    }
    _save_users(users)
    print(f">>> USER CREATED | {username} | role={role}")
    return {"username": username, "role": role}


def set_password(username: str, new_password: str) -> None:
    """Reset a user's password."""
    users = _load_users()
    if username not in users:
        raise ValueError(f"User '{username}' not found")
    if len(new_password) < 8:
        raise ValueError("Password must be at least 8 characters")
    hashed = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    users[username]["password"]       = hashed
    users[username]["login_attempts"] = 0
    users[username]["locked_until"]   = None
    _save_users(users)
    print(f">>> PASSWORD RESET | {username}")


def deactivate_user(username: str) -> None:
    """Deactivate a user — they can no longer log in."""
    users = _load_users()
    if username not in users:
        raise ValueError(f"User '{username}' not found")
    users[username]["active"] = False
    _save_users(users)
    # Revoke all their sessions
    _revoke_user_sessions(username)
    print(f">>> USER DEACTIVATED | {username}")


def list_users() -> list:
    """Return all users (without password hashes)."""
    users = _load_users()
    return [
        {k: v for k, v in u.items() if k != "password"}
        for u in users.values()
    ]


# ============================================================
# AUTHENTICATION
# ============================================================

def authenticate(username: str, password: str, ip: str) -> dict:
    """
    Verify credentials. Returns session token on success.
    Raises ValueError with reason on failure.
    Logs every attempt.
    """
    users = _load_users()

    # Unknown user
    if username not in users:
        _log("LOGIN_FAIL", username, ip, "/login", False, "unknown user")
        raise ValueError("Invalid credentials")

    user = users[username]

    # Inactive user
    if not user.get("active", True):
        _log("LOGIN_FAIL", username, ip, "/login", False, "account inactive")
        raise ValueError("Account is inactive")

    # Locked out
    locked_until = user.get("locked_until")
    if locked_until:
        lu = datetime.fromisoformat(locked_until)
        if datetime.now() < lu:
            remaining = int((lu - datetime.now()).total_seconds() / 60) + 1
            _log("LOGIN_FAIL", username, ip, "/login", False, "account locked")
            raise ValueError(f"Account locked — try again in {remaining} minute(s)")
        else:
            # Lockout expired — reset
            user["locked_until"]   = None
            user["login_attempts"] = 0

    # Check password
    if not bcrypt.checkpw(password.encode("utf-8"), user["password"].encode("utf-8")):
        user["login_attempts"] = user.get("login_attempts", 0) + 1
        if user["login_attempts"] >= MAX_LOGIN_ATTEMPTS:
            user["locked_until"] = (datetime.now() + timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
            _save_users(users)
            _log("LOGIN_FAIL", username, ip, "/login", False,
                 f"locked after {MAX_LOGIN_ATTEMPTS} attempts")
            raise ValueError(f"Too many failed attempts — account locked for {LOCKOUT_MINUTES} minutes")
        _save_users(users)
        remaining = MAX_LOGIN_ATTEMPTS - user["login_attempts"]
        _log("LOGIN_FAIL", username, ip, "/login", False,
             f"wrong password ({remaining} attempts remaining)")
        raise ValueError("Invalid credentials")

    # Success — reset attempt counter, update last login
    user["login_attempts"] = 0
    user["locked_until"]   = None
    user["last_login"]     = datetime.now().isoformat()
    _save_users(users)

    # Create session
    token = _create_session(username, ip)
    _log("LOGIN_OK", username, ip, "/login", True, "")
    print(f">>> LOGIN OK | {username} | {ip}")
    return {"token": token, "username": username, "role": user["role"]}


# ============================================================
# SESSION MANAGEMENT
# ============================================================

def _load_sessions() -> dict:
    with open(AUTH_DIR / "sessions.json") as f:
        return json.load(f)

def _save_sessions(sessions: dict) -> None:
    with open(AUTH_DIR / "sessions.json", "w") as f:
        json.dump(sessions, f, indent=2)


def _create_session(username: str, ip: str) -> str:
    sessions = _load_sessions()
    token    = secrets.token_urlsafe(32)
    sessions[token] = {
        "username":   username,
        "ip":         ip,
        "created_at": datetime.now().isoformat(),
        "last_seen":  datetime.now().isoformat(),
    }
    _save_sessions(sessions)
    return token


def validate_session(token: str, ip: str) -> Optional[dict]:
    """
    Validate a session token. Returns user dict or None.
    Updates last_seen. Expires idle sessions.
    """
    if not token:
        return None

    sessions = _load_sessions()
    session  = sessions.get(token)

    if not session:
        return None

    # Check TTL
    last_seen = datetime.fromisoformat(session["last_seen"])
    if datetime.now() - last_seen > timedelta(hours=SESSION_TTL_HOURS):
        del sessions[token]
        _save_sessions(sessions)
        return None

    # Update last_seen
    session["last_seen"] = datetime.now().isoformat()
    _save_sessions(sessions)

    # Get user record
    users = _load_users()
    user  = users.get(session["username"])
    if not user or not user.get("active", True):
        return None

    return {
        "username": session["username"],
        "role":     user.get("role", "user"),
        "ip":       session.get("ip"),
    }


def logout(token: str, username: str, ip: str) -> None:
    """Revoke a session token."""
    sessions = _load_sessions()
    if token in sessions:
        del sessions[token]
        _save_sessions(sessions)
    _log("LOGOUT", username, ip, "/logout", True, "")
    print(f">>> LOGOUT | {username} | {ip}")


def _revoke_user_sessions(username: str) -> None:
    """Revoke all sessions for a user."""
    sessions = _load_sessions()
    to_remove = [t for t, s in sessions.items() if s["username"] == username]
    for t in to_remove:
        del sessions[t]
    _save_sessions(sessions)


def list_sessions() -> list:
    """Return all active sessions — for admin view."""
    sessions = _load_sessions()
    now      = datetime.now()
    active   = []
    for token, s in sessions.items():
        last_seen = datetime.fromisoformat(s["last_seen"])
        if now - last_seen <= timedelta(hours=SESSION_TTL_HOURS):
            active.append({
                "username":   s["username"],
                "ip":         s["ip"],
                "created_at": s["created_at"],
                "last_seen":  s["last_seen"],
                "token_hint": token[:8] + "...",
            })
    return active


# ============================================================
# IP WHITELIST
# ============================================================

def _load_whitelist() -> list:
    with open(AUTH_DIR / "ip_whitelist.json") as f:
        return json.load(f)


def check_ip(ip: str) -> bool:
    """
    Returns True if IP is allowed.
    Empty whitelist = allow all.
    Supports exact match and CIDR prefix (e.g. "192.168.1.")
    """
    whitelist = _load_whitelist()
    if not whitelist:
        return True
    for entry in whitelist:
        if ip == entry or ip.startswith(entry):
            return True
    return False


def add_to_whitelist(ip: str) -> None:
    whitelist = _load_whitelist()
    if ip not in whitelist:
        whitelist.append(ip)
        with open(AUTH_DIR / "ip_whitelist.json", "w") as f:
            json.dump(whitelist, f, indent=2)
        print(f">>> IP WHITELISTED | {ip}")


def remove_from_whitelist(ip: str) -> None:
    whitelist = _load_whitelist()
    whitelist = [x for x in whitelist if x != ip]
    with open(AUTH_DIR / "ip_whitelist.json", "w") as f:
        json.dump(whitelist, f, indent=2)
    print(f">>> IP REMOVED FROM WHITELIST | {ip}")


# ============================================================
# ACCESS LOG
# ============================================================

def _log(event: str, username: str, ip: str,
         endpoint: str, success: bool, detail: str) -> None:
    log_path = AUTH_DIR / "access_log.csv"
    row = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "event":     event,
        "username":  username or "",
        "ip":        ip or "",
        "endpoint":  endpoint or "",
        "success":   "1" if success else "0",
        "detail":    detail or "",
    }
    with open(log_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        writer.writerow(row)


def log_request(username: str, ip: str, endpoint: str) -> None:
    """Log a normal authenticated request — called by middleware."""
    _log("REQUEST", username, ip, endpoint, True, "")


def get_access_log(limit: int = 100, username: str = None) -> list:
    """Read access log — for admin view."""
    log_path = AUTH_DIR / "access_log.csv"
    if not log_path.exists():
        return []
    rows = []
    with open(log_path, newline="") as f:
        for row in csv.DictReader(f):
            if username and row.get("username") != username:
                continue
            rows.append(dict(row))
    return rows[-limit:]  # most recent N


# ============================================================
# ADMIN BOOTSTRAP
# ============================================================

def bootstrap_admin(password: str) -> None:
    """
    Create the initial admin user.
    Call once from command line: python auth_manager.py bootstrap
    """
    users = _load_users()
    if "admin" in users:
        print("Admin user already exists — use set_password() to change password")
        return
    create_user("admin", password, role="admin", created_by="bootstrap")
    print(f">>> ADMIN USER CREATED")
    print(f">>> Login at /login with username: admin")


if __name__ == "__main__":
    import sys
    # Usage: python auth_manager.py bootstrap <chest_path> <password>
    if len(sys.argv) >= 4 and sys.argv[1] == "bootstrap":
        chest = sys.argv[2]
        pwd   = sys.argv[3]
        init_auth(chest)
        bootstrap_admin(pwd)
    elif len(sys.argv) >= 3 and sys.argv[1] == "create":
        # python auth_manager.py create <chest_path> <username> <password> [role]
        chest    = sys.argv[2]
        uname    = sys.argv[3]
        pwd      = sys.argv[4]
        role     = sys.argv[5] if len(sys.argv) > 5 else "user"
        init_auth(chest)
        create_user(uname, pwd, role=role)
    elif len(sys.argv) >= 4 and sys.argv[1] == "resetpw":
        chest = sys.argv[2]
        uname = sys.argv[3]
        pwd   = sys.argv[4]
        init_auth(chest)
        set_password(uname, pwd)
    else:
        print("Usage:")
        print("  python auth_manager.py bootstrap <chest_path> <password>")
        print("  python auth_manager.py create <chest_path> <username> <password> [role]")
        print("  python auth_manager.py resetpw <chest_path> <username> <new_password>")