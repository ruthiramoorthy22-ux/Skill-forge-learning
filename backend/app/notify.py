"""Notifications for students: one row per student. Used for new courses, new challenges, project reviews, payments,
certificates and the admin's announcements."""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import User, UserNotification


def notify_user(db: Session, user_id: str, kind: str, title: str, message: str = "", link: str = "") -> None:
    db.add(UserNotification(user_id=user_id, kind=kind, title=title[:140], message=message, link=link[:200]))


def broadcast(db: Session, kind: str, title: str, message: str = "", link: str = "", user_ids: Optional[list] = None) -> int:
    """Sends the same notification to every active student (or to the given students). Returns how many got it."""
    if user_ids is None:
        user_ids = list(db.scalars(select(User.id).where(User.role == "student", User.status == "active")).all())
    for uid in user_ids:
        notify_user(db, uid, kind, title, message, link)
    return len(user_ids)
