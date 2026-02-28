"""Admin user management endpoints."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.auth import get_client_ip, hash_password, require_admin
from backend.database import get_db
from backend.services.storage import log_activity

router = APIRouter(prefix="/users", tags=["users"])


class UserCreate(BaseModel):
    username: str
    password: str
    usertype: str = "normal"
    full_name: str = ""
    description: str = ""


class UserUpdate(BaseModel):
    username: str | None = None
    usertype: str | None = None
    full_name: str | None = None
    description: str | None = None


class UserPasswordSet(BaseModel):
    password: str


@router.get("")
async def list_users(request: Request):
    """List all users (admin only)."""
    await require_admin(request)

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, username, usertype, full_name, description, created_at FROM users ORDER BY id"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


@router.post("")
async def create_user(data: UserCreate, request: Request):
    """Create a new user (admin only)."""
    admin = await require_admin(request)

    if data.usertype not in ("normal", "admin"):
        raise HTTPException(status_code=400, detail="usertype must be 'normal' or 'admin'")

    password_hash = hash_password(data.password)

    async with get_db() as db:
        try:
            cursor = await db.execute(
                """INSERT INTO users (username, usertype, full_name, description, password_hash)
                   VALUES (?, ?, ?, ?, ?)""",
                (data.username, data.usertype, data.full_name, data.description, password_hash),
            )
            await db.commit()
            user_id = cursor.lastrowid
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                raise HTTPException(status_code=400, detail="Username already exists")
            raise

    ip = get_client_ip(request)
    await log_activity(ip, "admin.user.create", f"Created user '{data.username}' ({data.usertype})", admin["id"])

    return {"id": user_id, "username": data.username, "usertype": data.usertype,
            "full_name": data.full_name, "description": data.description}


@router.put("/{user_id}")
async def update_user(user_id: int, data: UserUpdate, request: Request):
    """Update user details (admin only)."""
    admin = await require_admin(request)

    updates = data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    if "usertype" in updates and updates["usertype"] not in ("normal", "admin"):
        raise HTTPException(status_code=400, detail="usertype must be 'normal' or 'admin'")

    async with get_db() as db:
        # Check user exists
        cursor = await db.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="User not found")

        set_clauses = []
        values = []
        for key, value in updates.items():
            set_clauses.append(f"{key} = ?")
            values.append(value)

        values.append(user_id)
        try:
            await db.execute(
                f"UPDATE users SET {', '.join(set_clauses)} WHERE id = ?",
                values,
            )
            await db.commit()
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                raise HTTPException(status_code=400, detail="Username already exists")
            raise

        cursor = await db.execute(
            "SELECT id, username, usertype, full_name, description, created_at FROM users WHERE id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()

    ip = get_client_ip(request)
    await log_activity(ip, "admin.user.update", f"Updated user ID {user_id}", admin["id"])
    return dict(row)


@router.put("/{user_id}/password")
async def set_user_password(user_id: int, data: UserPasswordSet, request: Request):
    """Set a user's password (admin only)."""
    admin = await require_admin(request)

    async with get_db() as db:
        cursor = await db.execute("SELECT id, username FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")

        new_hash = hash_password(data.password)
        await db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_hash, user_id),
        )
        await db.commit()

    ip = get_client_ip(request)
    await log_activity(ip, "admin.user.password", f"Set password for user '{row['username']}'", admin["id"])
    return {"status": "ok"}


@router.delete("/{user_id}")
async def delete_user(user_id: int, request: Request):
    """Delete a user (admin only, cannot self-delete)."""
    admin = await require_admin(request)

    if admin["id"] == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    async with get_db() as db:
        cursor = await db.execute("SELECT id, username FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")

        username = row["username"]

        # Delete user's sessions
        await db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        # Delete user
        await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await db.commit()

    ip = get_client_ip(request)
    await log_activity(ip, "admin.user.delete", f"Deleted user '{username}'", admin["id"])
    return {"status": "deleted"}
