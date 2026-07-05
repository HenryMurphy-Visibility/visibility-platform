"""
auth_manager.py
Visibility Platform — Authentication Manager

Handles all auth state: users, sessions, IP whitelist, access log.
No FastAPI dependencies — pure Python, fully testable standalone.

Storage layout (all under chest/admin/auth/):
  users.json          — registered users + hashed passwords + api keys
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

SESSION_TTL_HOURS   = 12
MAX_LOGIN_ATTEMPTS  = 5
LOCKOUT_MINUTES     = 15
AUTH_DIR            = None


# ============================================================
# INIT
# ============================================================

def init_auth(chest_path: str) -> None:
    global AUTH_DIR
    AUTH_DIR = Path(chest_path) / "admin" / "auth"
    AUTH_DIR.mkdir(parents=True, exist_ok=True)

    _ensure_file("users.json",        {})
    _ensure_file("sessions.json",     {})
    _ensure_file("ip_whitelist.json", [])

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
    users = _load_users()
    if username in users:
        raise ValueError(f"User '{username}' already exists")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")

    hashed  = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    api_key = secrets.token_urlsafe(32)

    users[username] = {
        "username":       username,
        "password":       hashed,
        "role":           role,
        "api_key":        api_key,
        "created_at":     datetime.now().isoformat(),
        "created_by":     created_by,
        "active":         True,
        "last_login":     None,
        "login_attempts": 0,
        "locked_until":   None,
    }
    _save_users(users)
    print(f">>> USER CREATED | {username} | role={role} | api_key={api_key}")
    return {"username": username, "role": role, "api_key": api_key}


def generate_api_key(username: str) -> str:
    """Generate a new API key for an existing user."""
    users = _load_users()
    if username not in users:
        raise ValueError(f"User '{username}' not found")
    api_key = secrets.token_urlsafe(32)
    users[username]["api_key"] = api_key
    _save_users(users)
    print(f">>> API KEY GENERATED | {username} | {api_key}")
    return api_key


def validate_api_key(key: str) -> Optional[dict]:
    """Validate an API key. Returns user dict or None."""
    if not key:
        return None
    users = _load_users()
    for username, user in users.items():
        if user.get("api_key") == key and user.get("active", True):
            return {
                "username": username,
                "role":     user.get("role", "user"),
                "ip":       "api-key",
            }
    return None


def get_api_key(username: str) -> Optional[str]:
    """Get the API key for a user."""
    users = _load_users()
    if username not in users:
        raise ValueError(f"User '{username}' not found")
    return users[username].get("api_key")


def set_password(username: str, new_password: str) -> None:
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
    users = _load_users()
    if username not in users:
        raise ValueError(f"User '{username}' not found")
    users[username]["active"] = False
    _save_users(users)
    _revoke_user_sessions(username)
    print(f">>> USER DEACTIVATED | {username}")


def list_users() -> list:
    users = _load_users()
    return [
        {k: v for k, v in u.items() if k != "password"}
        for u in users.values()
    ]


# ============================================================
# AUTHENTICATION
# ============================================================

def authenticate(username: str, password: str, ip: str) -> dict:
    users = _load_users()

    if username not in users:
        _log("LOGIN_FAIL", username, ip, "/login", False, "unknown user")
        raise ValueError("Invalid credentials")

    user = users[username]

    if not user.get("active", True):
        _log("LOGIN_FAIL", username, ip, "/login", False, "account inactive")
        raise ValueError("Account is inactive")

    locked_until = user.get("locked_until")
    if locked_until:
        lu = datetime.fromisoformat(locked_until)
        if datetime.now() < lu:
            remaining = int((lu - datetime.now()).total_seconds() / 60) + 1
            _log("LOGIN_FAIL", username, ip, "/login", False, "account locked")
            raise ValueError(f"Account locked — try again in {remaining} minute(s)")
        else:
            user["locked_until"]   = None
            user["login_attempts"] = 0

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

    user["login_attempts"] = 0
    user["locked_until"]   = None
    user["last_login"]     = datetime.now().isoformat()
    _save_users(users)

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
    if not token:
        return None

    sessions = _load_sessions()
    session  = sessions.get(token)

    if not session:
        return None

    last_seen = datetime.fromisoformat(session["last_seen"])
    if datetime.now() - last_seen > timedelta(hours=SESSION_TTL_HOURS):
        del sessions[token]
        _save_sessions(sessions)
        return None

    session["last_seen"] = datetime.now().isoformat()
    _save_sessions(sessions)

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
    sessions = _load_sessions()
    if token in sessions:
        del sessions[token]
        _save_sessions(sessions)
    _log("LOGOUT", username, ip, "/logout", True, "")
    print(f">>> LOGOUT | {username} | {ip}")


def _revoke_user_sessions(username: str) -> None:
    sessions = _load_sessions()
    to_remove = [t for t, s in sessions.items() if s["username"] == username]
    for t in to_remove:
        del sessions[t]
    _save_sessions(sessions)


def list_sessions() -> list:
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
    _log("REQUEST", username, ip, endpoint, True, "")


def get_access_log(limit: int = 100, username: str = None) -> list:
    log_path = AUTH_DIR / "access_log.csv"
    if not log_path.exists():
        return []
    rows = []
    with open(log_path, newline="") as f:
        for row in csv.DictReader(f):
            if username and row.get("username") != username:
                continue
            rows.append(dict(row))
    return rows[-limit:]


# ============================================================
# ADMIN BOOTSTRAP
# ============================================================

def bootstrap_admin(password: str) -> None:
    users = _load_users()
    if "admin" in users:
        print("Admin user already exists — use set_password() to change password")
        return
    result = create_user("admin", password, role="admin", created_by="bootstrap")
    print(f">>> ADMIN USER CREATED")
    print(f">>> API Key: {result['api_key']}")
    print(f">>> Login at /login with username: admin")


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 4 and sys.argv[1] == "bootstrap":
        chest = sys.argv[2]
        pwd   = sys.argv[3]
        init_auth(chest)
        bootstrap_admin(pwd)
    elif len(sys.argv) >= 5 and sys.argv[1] == "create":
        chest = sys.argv[2]
        uname = sys.argv[3]
        pwd   = sys.argv[4]
        role  = sys.argv[5] if len(sys.argv) > 5 else "user"
        init_auth(chest)
        create_user(uname, pwd, role=role)
    elif len(sys.argv) >= 4 and sys.argv[1] == "resetpw":
        chest = sys.argv[2]
        uname = sys.argv[3]
        pwd   = sys.argv[4]
        init_auth(chest)
        set_password(uname, pwd)
    elif len(sys.argv) >= 3 and sys.argv[1] == "apikey":
        chest = sys.argv[2]
        uname = sys.argv[3]
        init_auth(chest)
        key = generate_api_key(uname)
        print(f"API Key for {uname}: {key}")
    else:
        print("Usage:")
        print("  python auth_manager.py bootstrap <chest_path> <password>")
        print("  python auth_manager.py create <chest_path> <username> <password> [role]")
        print("  python auth_manager.py resetpw <chest_path> <username> <new_password>")
        print("  python auth_manager.py apikey <chest_path> <username>")