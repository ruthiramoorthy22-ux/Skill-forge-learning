from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ValidationError  # noqa: F401
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .deps import get_current_user
from .gamification import ACHIEVEMENTS, learner_stats, leaderboard
from .models import ActivityEvent, Course, Enrollment, Lesson, LessonProgress, User, UserAchievement, UserPresence, UserSettings
from .progress import completion
from .ratelimit import Limiter
from .routes_learning import lesson_counts

from fastapi import HTTPException
from typing import Literal, Optional

router = APIRouter(prefix="/api")
heartbeat_limiter = Limiter(30, 60)


def _now():
    return datetime.now(timezone.utc)


@router.post("/activity/heartbeat")
def heartbeat(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    heartbeat_limiter.check(user.id)
    p = db.get(UserPresence, user.id) or UserPresence(user_id=user.id)
    p.last_seen_at = _now()
    db.add(p)
    db.commit()
    return {"ok": True}


@router.get("/me/stats")
def my_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = learner_stats(db, user.id)
    earned = {a.code: a.earned_at for a in db.scalars(select(UserAchievement).where(UserAchievement.user_id == user.id)).all()}
    events = db.scalars(select(ActivityEvent).where(ActivityEvent.user_id == user.id).order_by(ActivityEvent.id.desc()).limit(10)).all()
    st = db.get(UserSettings, user.id)
    return {**s, "show_on_leaderboard": bool(st and st.show_on_leaderboard),
            "achievements": [{"code": c, "title": t, "description": d, "earned": c in earned}
                             for c, (t, d, _) in ACHIEVEMENTS.items()],
            "recent_activity": [{"kind": e.kind, "ref": e.ref, "at": (e.created_at.replace(tzinfo=timezone.utc)
                                                                      if e.created_at.tzinfo is None else e.created_at).isoformat()} for e in events]}


class PrivacyIn(BaseModel):
    show_on_leaderboard: bool


@router.patch("/me/privacy")
def set_privacy(body: PrivacyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    st = db.get(UserSettings, user.id) or UserSettings(user_id=user.id)
    st.show_on_leaderboard = body.show_on_leaderboard
    db.add(st)
    db.commit()
    return {"show_on_leaderboard": st.show_on_leaderboard}


@router.get("/leaderboard")
def get_leaderboard(db: Session = Depends(get_db)):
    return {"items": leaderboard(db), "note": "Only learners who opted in appear here."}


@router.get("/me/recommendations")
def recommendations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Next lesson in the most recently active unfinished course, plus available courses not yet joined."""
    items = []
    enrollments = db.scalars(select(Enrollment).where(Enrollment.user_id == user.id).order_by(Enrollment.last_activity_at.desc())).all()
    done_ids = set(db.scalars(select(LessonProgress.lesson_id).where(LessonProgress.user_id == user.id)).all())
    for e in enrollments:
        nxt = next((l for m in e.course.modules for l in m.lessons if l.published and l.id not in done_ids), None)
        if nxt:
            items.append({"type": "lesson", "course_slug": e.course.slug, "lesson_slug": nxt.slug, "title": nxt.title})
            break
    joined = {e.course_id for e in enrollments}
    counts = lesson_counts(db)
    for c in db.scalars(select(Course).where(Course.published.is_(True))).all():
        if c.id not in joined and counts.get(c.slug):
            items.append({"type": "course", "course_slug": c.slug, "title": c.title})
    return {"items": items[:4]}
