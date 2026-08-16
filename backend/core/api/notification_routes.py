"""
core/api/notification_routes.py

REST API for notification history center.
Endpoints:
  GET  /api/notifications        - List current user's notifications (paged)
  POST /api/notifications/read   - Mark one or all as read
  DELETE /api/notifications/{id} - Delete a single notification
  DELETE /api/notifications      - Clear all notifications
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
import uuid

from core.memory.database import get_db
from core.auth.auth_middleware import require_auth
from core.memory.models import Notification

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


# ─── Helper ─────────────────────────────────────────────────────────
def _fmt(n: Notification) -> dict:
    return {
        "id": str(n.id),
        "title": n.title,
        "message": n.message,
        "type": n.type,
        "is_read": n.is_read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


# ─── List ────────────────────────────────────────────────────────────
@router.get("")
async def list_notifications(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth),
):
    user_id = user["sub"]
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    notifications = result.scalars().all()
    unread_count = sum(1 for n in notifications if not n.is_read)
    return {"notifications": [_fmt(n) for n in notifications], "unread_count": unread_count}


# ─── Mark Read ───────────────────────────────────────────────────────
class MarkReadBody(BaseModel):
    notification_id: Optional[str] = None  # None = mark all


@router.post("/read")
async def mark_read(
    body: MarkReadBody,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth),
):
    user_id = user["sub"]
    if body.notification_id:
        await db.execute(
            update(Notification)
            .where(Notification.id == uuid.UUID(body.notification_id), Notification.user_id == user_id)
            .values(is_read=True)
        )
    else:
        # Mark all as read
        await db.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read == False)
            .values(is_read=True)
        )
    await db.commit()
    return {"status": "ok"}


# ─── Delete One ──────────────────────────────────────────────────────
@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth),
):
    user_id = user["sub"]
    result = await db.execute(
        select(Notification)
        .where(Notification.id == uuid.UUID(notification_id), Notification.user_id == user_id)
    )
    n = result.scalar_one_or_none()
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")
    await db.delete(n)
    await db.commit()
    return {"status": "deleted"}


# ─── Clear All ───────────────────────────────────────────────────────
@router.delete("")
async def clear_all_notifications(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth),
):
    user_id = user["sub"]
    await db.execute(
        delete(Notification).where(Notification.user_id == user_id)
    )
    await db.commit()
    return {"status": "cleared"}
