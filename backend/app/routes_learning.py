from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .catalog import CATEGORIES, COURSES
from .db import get_db
from .deps import get_current_user
from .gamification import after_learning_event, grant_xp, record_activity
from .models import Course, Enrollment, Lesson, LessonProgress, Module, User
from .progress import completion

router = APIRouter(prefix="/api")


def _iso(dt: datetime) -> str:
    return (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt).isoformat()


def lesson_counts(db: Session) -> dict:
    rows = db.execute(
        select(Course.slug, func.count(Lesson.id)).join(Module, Module.course_id == Course.id)
        .join(Lesson, Lesson.module_id == Module.id)
        .where(Course.published.is_(True), Lesson.published.is_(True)).group_by(Course.slug)
    ).all()
    return {slug: n for slug, n in rows}


def pricing_map(db: Session) -> dict:
    """slug -> {is_free, price_inr} for every published course. price_inr is 0 for a free course."""
    from . import app_settings
    default = app_settings.get_price(db)
    return {c.slug: {"is_free": not c.is_paid, "price_inr": 0 if not c.is_paid else (c.price_inr or default)}
            for c in db.scalars(select(Course).where(Course.published.is_(True))).all()}


def _course(db: Session, slug: str) -> Optional[Course]:
    return db.scalar(select(Course).where(Course.slug == slug, Course.published.is_(True)))


def _lessons(course: Course) -> list:
    return [l for m in course.modules for l in m.lessons if l.published]


def _enrollment(db: Session, user: User, course: Course) -> Optional[Enrollment]:
    return db.scalar(select(Enrollment).where(Enrollment.user_id == user.id, Enrollment.course_id == course.id))


def _progress(db: Session, user: User, course: Course) -> dict:
    lessons = _lessons(course)
    enr = _enrollment(db, user, course)
    ids = [l.id for l in lessons]
    done = set(db.scalars(select(LessonProgress.lesson_id).where(
        LessonProgress.user_id == user.id, LessonProgress.lesson_id.in_(ids)))) if ids else set()
    last = next((l.slug for l in lessons if enr and l.id == enr.last_lesson_id), None)
    return {"enrolled": enr is not None, "completed": [l.slug for l in lessons if l.id in done],
            "total": len(lessons), "percent": round(100 * len(done) / len(lessons)) if lessons else 0,
            "last_lesson": last, "course_completed": completion(db, user.id, course)["completed"]}


def _require_course(db: Session, slug: str) -> Course:
    course = _course(db, slug)
    if course is None or not _lessons(course):
        raise HTTPException(status_code=404, detail="This course has no published lessons yet.")
    return course


def _require_enrolled(db: Session, user: User, course: Course) -> Enrollment:
    enr = _enrollment(db, user, course)
    if enr is None:
        raise HTTPException(status_code=403, detail="Enroll in this course to open its lessons.")
    return enr


@router.get("/courses/{slug}")
def course_detail(slug: str, db: Session = Depends(get_db)):
    base = next((c for c in COURSES if c["slug"] == slug), None)
    course = _course(db, slug)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if base is None:
        base = {"slug": course.slug, "title": course.title, "category_id": course.category_id,
                "category_name": next((c["name"] for c in CATEGORIES if c["id"] == course.category_id), course.category_id),
                "level": course.level, "status": "planned"}
    lessons = _lessons(course)
    out = {**base, "lesson_count": len(lessons), "outline": None, **pricing_map(db).get(slug, {})}
    out["status"] = course.status
    out.update(duration_value=course.duration_value, duration_unit=course.duration_unit,
               est_minutes=course.est_minutes)
    if lessons:
        out.update(status=course.status, summary=course.summary, objectives=course.objectives,
                   outline=[{"title": m.title, "lessons": [{"slug": l.slug, "title": l.title} for l in m.lessons if l.published]}
                            for m in course.modules if any(l.published for l in m.lessons)])
    return out


@router.get("/courses/{slug}/progress")
def course_progress(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _progress(db, user, _require_course(db, slug))


@router.post("/courses/{slug}/enroll")
def enroll(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    course = _require_course(db, slug)
    if _enrollment(db, user, course) is None:
        db.add(Enrollment(user_id=user.id, course_id=course.id))
        try:
            db.commit()
        except IntegrityError:  # double click / race: already enrolled
            db.rollback()
    return _progress(db, user, course)


@router.get("/courses/{slug}/lessons/{lesson_slug}")
def get_lesson(slug: str, lesson_slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    course = _require_course(db, slug)
    enr = _require_enrolled(db, user, course)
    lessons = _lessons(course)
    idx = next((i for i, l in enumerate(lessons) if l.slug == lesson_slug), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    lesson = lessons[idx]
    enr.last_lesson_id, enr.last_activity_at = lesson.id, datetime.now(timezone.utc)
    db.commit()
    done = db.scalar(select(LessonProgress.id).where(LessonProgress.user_id == user.id, LessonProgress.lesson_id == lesson.id))
    return {"slug": lesson.slug, "title": lesson.title, "module_title": lesson.module.title, "body_md": lesson.body_md,
            "example_code": lesson.example_code, "example_lang": lesson.example_lang,
            "expected_output": lesson.expected_output, "completed": done is not None,
            "prev": lessons[idx - 1].slug if idx > 0 else None,
            "next": lessons[idx + 1].slug if idx + 1 < len(lessons) else None}


@router.post("/courses/{slug}/lessons/{lesson_slug}/complete")
def complete_lesson(slug: str, lesson_slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    course = _require_course(db, slug)
    enr = _require_enrolled(db, user, course)
    lesson = next((l for l in _lessons(course) if l.slug == lesson_slug), None)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    exists = db.scalar(select(LessonProgress.id).where(LessonProgress.user_id == user.id, LessonProgress.lesson_id == lesson.id))
    new_achievements = []
    if exists is None:
        db.add(LessonProgress(user_id=user.id, lesson_id=lesson.id))
        record_activity(db, user.id, "lesson_complete", f"{slug}/{lesson_slug}")
        grant_xp(db, user.id, "lesson", lesson.id)
        new_achievements = after_learning_event(db, user)
    enr.last_lesson_id, enr.last_activity_at = lesson.id, datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return {**_progress(db, user, course), "new_achievements": new_achievements}


@router.get("/me/enrollments")
def my_enrollments(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Enrollment).join(Course).where(
        Enrollment.user_id == user.id, Course.status == "available"
    ).order_by(Enrollment.last_activity_at.desc())).all()
    items = []
    for e in rows:
        p = _progress(db, user, e.course)
        items.append({"course_slug": e.course.slug, "title": e.course.title, "level": e.course.level,
                      "total": p["total"], "completed": len(p["completed"]), "percent": p["percent"],
                      "last_lesson": p["last_lesson"], "enrolled_at": _iso(e.enrolled_at)})
    return {"items": items}


def extra_courses(db: Session, counts: dict) -> list:
    """Published admin-created courses that are not part of the static catalog."""
    known = {c["slug"] for c in COURSES}
    names = {c["id"]: c["name"] for c in CATEGORIES}
    return [{"slug": c.slug, "title": c.title, "category_id": c.category_id, "category_name": names.get(c.category_id, c.category_id),
             "level": c.level, "status": "available", "lesson_count": counts[c.slug]}
            for c in db.scalars(select(Course).where(Course.published.is_(True))).all()
            if c.slug not in known and counts.get(c.slug)]
