"""Authentication endpoints: login, logout, current user, password change."""

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from backend.auth import (
    SESSION_COOKIE,
    SESSION_MAX_AGE_DAYS,
    create_session,
    delete_session,
    get_client_ip,
    get_session_user,
    get_single_user_mode,
    hash_password,
    require_user,
    verify_password,
)
from backend.database import get_db
from backend.services.storage import log_activity

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/login")
async def login(data: LoginRequest, request: Request, response: Response):
    """Validate credentials and set session cookie."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, username, usertype, full_name, password_hash FROM users WHERE username = ?",
            (data.username,),
        )
        row = await cursor.fetchone()

    if not row or not verify_password(data.password, row["password_hash"]):
        ip = get_client_ip(request)
        await log_activity(ip, "auth.login.fail", f"Failed login attempt for '{data.username}'")
        raise HTTPException(status_code=401, detail="Invalid username or password")

    session_id = await create_session(row["id"])

    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=SESSION_MAX_AGE_DAYS * 86400,
        path="/",
    )

    ip = get_client_ip(request)
    await log_activity(ip, "auth.login", f"User '{data.username}' logged in", row["id"])

    return {
        "id": row["id"],
        "username": row["username"],
        "usertype": row["usertype"],
        "full_name": row["full_name"],
    }


@router.post("/logout")
async def logout(request: Request, response: Response):
    """Delete session and clear cookie."""
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        await delete_session(session_id)

    response.delete_cookie(key=SESSION_COOKIE, path="/")

    ip = get_client_ip(request)
    await log_activity(ip, "auth.logout", "User logged out")
    return {"status": "ok"}


@router.get("/me")
async def get_current_user(request: Request):
    """Return current user info, or 401 if not authenticated."""
    user = await require_user(request)
    return user


@router.get("/mode")
async def get_auth_mode():
    """Public endpoint: returns whether single-user mode is active."""
    single_user = await get_single_user_mode()
    return {"single_user": single_user is not None}


@router.put("/password")
async def change_password(data: PasswordChangeRequest, request: Request):
    """Change own password (requires current password)."""
    user = await require_user(request)

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user["id"],)
        )
        row = await cursor.fetchone()

    if not row or not verify_password(data.current_password, row["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    new_hash = hash_password(data.new_password)
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_hash, user["id"]),
        )
        await db.commit()

    ip = get_client_ip(request)
    await log_activity(ip, "auth.password.change", f"User '{user['username']}' changed password", user["id"])
    return {"status": "ok"}
