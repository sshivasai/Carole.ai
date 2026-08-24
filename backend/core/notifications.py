"""
core/notifications.py

Convenience helpers for creating system notifications.
Can be called from cron_worker, agents, or any background task.
"""

import logging
from typing import Literal

from core.memory.database import async_session
from core.memory.models import Notification

logger = logging.getLogger("carole.notifications")

NotificationType = Literal["info", "success", "warning", "error"]


async def create_notification(
    user_id: str,
    title: str,
    message: str,
    type: NotificationType = "info",
) -> None:
    """
    Persist a notification for a user and push it in real-time via the
    user-scoped event bus topic ``user:<user_id>``.
    Non-blocking: errors are logged but not raised to the caller.
    """
    try:
        async with async_session() as db:
            notif = Notification(
                user_id=user_id,
                title=title,
                message=message,
                type=type,
            )
            db.add(notif)
            await db.commit()
            await db.refresh(notif)

        # Push to the user's personal WS topic so the browser receives it
        # instantly without any polling.
        from core.chat.event_bus import event_bus
        await event_bus.publish(f"user:{user_id}", {
            "type": "notification",
            "action": "new",
            "notification": {
                "id": str(notif.id),
                "title": notif.title,
                "message": notif.message,
                "type": notif.type,
                "is_read": notif.is_read,
                "created_at": notif.created_at.isoformat() if notif.created_at else None,
            },
        })
    except Exception as e:
        logger.warning("Failed to create notification for user %s: %s", user_id, e)
