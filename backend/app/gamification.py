from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select

from .models import (ActivityEvent, CodeSubmission, Course, Enrollment, LessonProgress, Quiz, QuizAttempt, UserAchievement,
                     UserSettings, User, XPEvent)
from .progress import completion

XP_POINTS = {"lesson": 10, "quiz_pass": 50, "challenge": 30, "course": 100}
LEARNING_KINDS = ("lesson_complete", "quiz_submit", "practice_submit", "challenge_submit")
DAILY_GOAL_LESSONS = 1

ACHIEVEMENTS = {
    "first_lesson": ("First lesson", "Complete your first lesson.", lambda s: s["lessons"] >= 1),
    "five_lessons": ("Five lessons", "Complete five lessons.", lambda s: s["lessons"] >= 5),
    "quiz_pass": ("Quiz passed", "Pass a quiz.", lambda s: s["quizzes_passed"] >= 1),
    "first_challenge": ("Challenge solved", "Solve a coding challenge.", lambda s: s["challenges_solved"] >= 1),
    "course_complete": ("Course complete", "Complete every requirement of a course.", lambda s: s["courses_completed"] >= 1),
    "streak_3": ("3-day streak", "Learn on three days in a row.", lambda s: s["streak"] >= 3),
}


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def record_activity(db, user_id: str, kind: str, ref=None) -> None:
    db.add(ActivityEvent(user_id=user_id, kind=kind, ref=None if ref is None else str(ref)))


def grant_xp(db, user_id: str, kind: str, ref) -> bool:
    """Each (user, kind, ref) pays out once, so replaying a request cannot farm points."""
    ref = str(ref)
    if db.scalar(select(XPEvent.id).where(XPEvent.user_id == user_id, XPEvent.kind == kind, XPEvent.ref == ref)):
        return False
    db.add(XPEvent(user_id=user_id, kind=kind, ref=ref, points=XP_POINTS[kind]))
    db.flush()
    return True


def streak_from_days(days: set, today: date) -> int:
    cur = today if today in days else today - timedelta(days=1)
    n = 0
    while cur in days:
        n += 1
        cur -= timedelta(days=1)
    return n


def learner_stats(db, user_id: str) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=400)
    stamps = db.scalars(select(ActivityEvent.created_at).where(
        ActivityEvent.user_id == user_id, ActivityEvent.kind.in_(LEARNING_KINDS), ActivityEvent.created_at >= since)).all()
    days = {_utc(t).date() for t in stamps}
    today = datetime.now(timezone.utc).date()
    day_start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    courses_done = sum(1 for e in db.scalars(select(Enrollment).where(Enrollment.user_id == user_id)).all()
                       if completion(db, user_id, e.course)["completed"])
    return {
        "xp": db.scalar(select(func.coalesce(func.sum(XPEvent.points), 0)).where(XPEvent.user_id == user_id)),
        "lessons": db.scalar(select(func.count()).select_from(LessonProgress).where(LessonProgress.user_id == user_id)),
        "quizzes_passed": db.scalar(select(func.count(func.distinct(QuizAttempt.quiz_id))).join(Quiz, Quiz.id == QuizAttempt.quiz_id).where(
            QuizAttempt.user_id == user_id, QuizAttempt.passed.is_(True), Quiz.kind != "practice")),
        "challenges_solved": db.scalar(select(func.count(func.distinct(CodeSubmission.challenge_id))).where(
            CodeSubmission.user_id == user_id, CodeSubmission.status == "accepted", CodeSubmission.challenge_id.is_not(None))),
        "courses_completed": courses_done,
        "streak": streak_from_days(days, today),
        "today_lessons": db.scalar(select(func.count()).select_from(LessonProgress).where(
            LessonProgress.user_id == user_id, LessonProgress.completed_at >= day_start)),
        "daily_goal": DAILY_GOAL_LESSONS,
    }


def after_learning_event(db, user: User) -> list:
    """Call after saving progress. Grants course XP and achievements; returns newly earned achievement codes."""
    db.flush()
    for e in db.scalars(select(Enrollment).where(Enrollment.user_id == user.id)).all():
        if completion(db, user.id, e.course)["completed"]:
            grant_xp(db, user.id, "course", e.course_id)
    stats = learner_stats(db, user.id)
    have = set(db.scalars(select(UserAchievement.code).where(UserAchievement.user_id == user.id)).all())
    new = [code for code, (_, _, check) in ACHIEVEMENTS.items() if code not in have and check(stats)]
    for code in new:
        db.add(UserAchievement(user_id=user.id, code=code))
    db.flush()
    return new


def leaderboard(db, limit: int = 10) -> list:
    rows = db.execute(
        select(User.display_name, func.sum(XPEvent.points).label("xp"))
        .join(XPEvent, XPEvent.user_id == User.id).join(UserSettings, UserSettings.user_id == User.id)
        .where(UserSettings.show_on_leaderboard.is_(True)).group_by(User.id, User.display_name)
        .order_by(func.sum(XPEvent.points).desc()).limit(limit)).all()
    return [{"display_name": n, "xp": int(x)} for n, x in rows]
