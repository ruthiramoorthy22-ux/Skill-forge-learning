"""Student notifications (the bell) and the admin's announcements."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .deps import get_current_user, require_admin
from .models import User, UserNotification
from .notify import broadcast
from .routes_admin import _iso, audit

router = APIRouter(prefix="/api")


@router.get("/me/notifications")
def my_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(UserNotification).where(UserNotification.user_id == user.id).order_by(UserNotification.id.desc()).limit(50)).all()
    unread = db.scalar(select(func.count()).select_from(UserNotification).where(UserNotification.user_id == user.id, UserNotification.is_read.is_(False))) or 0
    return {"unread": unread, "items": [{"id": n.id, "kind": n.kind, "title": n.title, "message": n.message, "link": n.link,
                                         "read": n.is_read, "at": _iso(n.created_at)} for n in rows]}


@router.post("/me/notifications/read-all")
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for n in db.scalars(select(UserNotification).where(UserNotification.user_id == user.id, UserNotification.is_read.is_(False))).all():
        n.is_read = True
    db.commit()
    return {"ok": True}


@router.post("/me/notifications/{notification_id}/read")
def read_one(notification_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.get(UserNotification, notification_id)
    if n is None or n.user_id != user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    n.is_read = True
    db.commit()
    return {"ok": True}


class AnnouncementIn(BaseModel):
    title: str = Field(min_length=3, max_length=140)
    message: str = Field("", max_length=1000)
    link: str = Field("", max_length=200)

    @field_validator("link")
    @classmethod
    def _link(cls, v):
        v = v.strip()
        if v and not v.startswith("/"):  # only pages inside the app, never an outside address
            raise ValueError("The link must be a page of this app, like /courses/python.")
        return v


@router.post("/admin/announcements", status_code=201)
def announce(body: AnnouncementIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """A new update for every student: a course change, a new feature, anything."""
    n = broadcast(db, "announcement", body.title.strip(), body.message.strip(), body.link)
    audit(db, admin, "announcement.send", body.title.strip()[:100], f"to {n} students")
    db.commit()
    return {"sent_to": n}
