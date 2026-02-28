"""Authentication utilities: password hashing, session management, request dependencies."""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request


SESSION_COOKIE = "ulfweb_session"
SESSION_MAX_AGE_DAYS = 30


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with a random salt."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a stored hash."""
    try:
        salt, dk_hex = password_hash.split("$", 1)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
        return secrets.compare_digest(dk.hex(), dk_hex)
    except (ValueError, AttributeError):
        return False


def get_client_ip(request: Request) -> str:
    """Extract client IP from request (consolidated helper)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


async def get_session_user(request: Request) -> dict[str, Any] | None:
    """Look up user from session cookie. Returns user dict or None."""
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        return None

    from backend.database import get_db

    async with get_db() as db:
        cursor = await db.execute(
            """SELECT u.id, u.username, u.usertype, u.full_name
               FROM sessions s
               JOIN users u ON u.id = s.user_id
               WHERE s.id = ? AND s.expires_at > CURRENT_TIMESTAMP""",
            (session_id,),
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
    return None


async def get_single_user_mode() -> dict[str, Any] | None:
    """If single_user mode is set, return that user's info. Otherwise None."""
    from backend.database import get_db

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT single_user FROM admin_settings WHERE id = 1"
        )
        row = await cursor.fetchone()
        if not row or not row["single_user"]:
            return None

        username = row["single_user"]
        cursor = await db.execute(
            "SELECT id, username, usertype, full_name FROM users WHERE username = ?",
            (username,),
        )
        user_row = await cursor.fetchone()
        if user_row:
            return dict(user_row)
    return None


async def require_user(request: Request) -> dict[str, Any]:
    """FastAPI dependency: returns user dict or raises 401.

    Checks single-user mode first, then session cookie.
    """
    # Check single-user mode
    single_user = await get_single_user_mode()
    if single_user:
        return single_user

    # Check session cookie
    user = await get_session_user(request)
    if user:
        return user

    raise HTTPException(status_code=401, detail="Not authenticated")


async def require_admin(request: Request) -> dict[str, Any]:
    """FastAPI dependency: returns admin user dict or raises 403."""
    user = await require_user(request)
    if user["usertype"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def create_session(user_id: int) -> str:
    """Create a new session for a user, return session ID."""
    from backend.database import get_db

    session_id = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    expires = now + timedelta(days=SESSION_MAX_AGE_DAYS)

    async with get_db() as db:
        await db.execute(
            """INSERT INTO sessions (id, user_id, created_at, expires_at)
               VALUES (?, ?, ?, ?)""",
            (session_id, user_id, now, expires),
        )
        await db.commit()

    return session_id


async def delete_session(session_id: str) -> None:
    """Delete a session."""
    from backend.database import get_db

    async with get_db() as db:
        await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await db.commit()


async def cleanup_expired_sessions() -> None:
    """Remove all expired sessions."""
    from backend.database import get_db

    async with get_db() as db:
        await db.execute(
            "DELETE FROM sessions WHERE expires_at < CURRENT_TIMESTAMP"
        )
        await db.commit()
