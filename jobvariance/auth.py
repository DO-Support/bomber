"""App-level authentication: bcrypt-verified users + signed session cookies.

Users are supplied as `APP_USERS` (JSON: {username: bcrypt_hash}). The session
itself is a signed cookie managed by Starlette's SessionMiddleware; this module
only validates credentials and gates requests.

Passwords are handled with the `bcrypt` library directly. bcrypt operates on at
most 72 bytes, so inputs are truncated to 72 bytes (standard bcrypt behaviour).
"""

from __future__ import annotations

import bcrypt
from fastapi import Depends, HTTPException, Request, status

from .config import Settings, get_settings

# Pre-computed hash of a random value, used to keep timing uniform for unknown
# users (avoids leaking valid usernames via response time).
_DUMMY_HASH = bcrypt.hashpw(b"unused-placeholder", bcrypt.gensalt())


def _encode(password: str) -> bytes:
    return password.encode("utf-8")[:72]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_encode(plain), bcrypt.gensalt()).decode("ascii")


def verify_credentials(username: str, password: str, settings: Settings) -> bool:
    stored = settings.app_users.get(username)
    if stored is None:
        bcrypt.checkpw(_encode(password), _DUMMY_HASH)  # constant-ish time
        return False
    try:
        return bcrypt.checkpw(_encode(password), stored.encode("ascii"))
    except ValueError:
        return False  # malformed stored hash


def current_user(request: Request) -> str:
    """Dependency requiring an authenticated session; raises 401 otherwise so the
    frontend can redirect to /login."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    return user


def optional_user(request: Request) -> str | None:
    return request.session.get("user")


RequireUser = Depends(current_user)


def settings_dep() -> Settings:
    return get_settings()
