# Auth Setup — Wire-in Instructions

## 1. Bootstrap admin user (run once from command line)

```
cd chest
python auth_manager.py bootstrap C:/path/to/chest yourpassword
```

This creates `chest/auth/` and the admin user.

## 2. Add to main.py

```python
# ── AUTH ──────────────────────────────────────────────────
from auth_manager    import init_auth
from auth_middleware import AuthMiddleware
from auth_routes     import auth_router
from fastapi.responses import FileResponse

# Initialise auth (after app = FastAPI())
init_auth("C:/path/to/chest")   # same as your CHEST_PATH in v_config.py

# Add middleware (before any routes)
app.add_middleware(AuthMiddleware)

# Register auth routes
app.include_router(auth_router)

# Serve login page
@app.get("/login")
def login_page():
    return FileResponse("login.html")
# ──────────────────────────────────────────────────────────
```

## 3. File locations

Put these four files alongside your other app files:
- `auth_manager.py`
- `auth_middleware.py`
- `auth_routes.py`
- `login.html`

## 4. Create additional users (admin only)

Via command line:
```
python auth_manager.py create C:/path/to/chest username password user
python auth_manager.py create C:/path/to/chest username password admin
```

Via API (must be logged in as admin):
```
POST /api/v1/auth/users
{"username": "john", "password": "password123", "role": "user"}
```

## 5. Admin endpoints

All require admin login:

| Endpoint | Method | Description |
|---|---|---|
| /api/v1/auth/users | GET | List all users |
| /api/v1/auth/users | POST | Create user |
| /api/v1/auth/users/{u}/deactivate | POST | Deactivate user |
| /api/v1/auth/users/{u}/resetpw | POST | Reset password |
| /api/v1/auth/sessions | GET | Active sessions |
| /api/v1/auth/log | GET | Access log |
| /api/v1/auth/whitelist | GET | View IP whitelist |
| /api/v1/auth/whitelist | POST | Add IP (?ip=x.x.x.x) |
| /api/v1/auth/whitelist/{ip} | DELETE | Remove IP |

## 6. IP Whitelist

Empty list = allow all IPs (default).
Add IPs to restrict access:
```
POST /api/v1/auth/whitelist?ip=192.168.1.100
POST /api/v1/auth/whitelist?ip=192.168.1.   ← entire subnet prefix
```

## 7. User tips storage

Once auth is wired, user tips move from localStorage to server.
Tips stored at: `chest/user_data/{username}/tips.json`
Admin can read any user's tips file directly.

## 8. Storage layout created automatically

```
chest/
  auth/
    users.json           ← hashed passwords, roles, lockout state
    sessions.json        ← active session tokens
    ip_whitelist.json    ← allowed IPs (empty = all allowed)
    access_log.csv       ← every login attempt + request
```