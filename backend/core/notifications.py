"""
core/notifications.py

Convenience helpers for creating system notifications.
Can be called from cron_worker, agents, or any background task.
"""

import logging
from datetime import datetime, timezone
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
    Persist a notification for a user.
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
    except Exception as e:
        logger.warning("Failed to create notification for user %s: %s", user_id, e)
