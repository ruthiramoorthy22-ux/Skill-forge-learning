import csv
import io
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import certificates, mailer, payments
from .certificate_image import to_pdf
from .catalog import CATEGORIES
from .config import settings
from .db import get_db
from .deps import require_admin
from .models import (ActivityEvent, AdminNotification, AuditLog, Certificate, CertificateDelivery, Challenge, CodeSubmission, Course, Enrollment, Lesson, Module,
                     Payment, Question, Quiz, QuizAttempt, StudentProfile, User, UserPresence)
from .notify import broadcast
from .progress import completion
from .routes_student import PROFILE_KEYS, profile_out

router = APIRouter(prefix="/api/admin")
public_router = APIRouter(prefix="/api")
SLUG = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
CATEGORY_IDS = {c["id"] for c in CATEGORIES}


def _now():
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    return None if dt is None else (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc))


def _iso(dt):
    d = _aware(dt)
    return d.isoformat() if d else None


def audit(db: Session, admin: User, action: str, target: str = "", detail: str = "") -> None:
    db.add(AuditLog(admin_id=admin.id, action=action, target=target[:120], detail=detail[:1000]))


def _is_online(p: Optional[UserPresence]) -> bool:
    seen = _aware(p.last_seen_at) if p else None
    return bool(seen and (_now() - seen).total_seconds() <= settings.online_timeout_seconds)


# --------------------------------------------------------------------------- overview
@router.get("/overview")
def overview(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    today = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    students = db.scalar(select(func.count()).select_from(User).where(User.role == "student")) or 0
    student_ids = select(User.id).where(User.role == "student")
    active = set(db.scalars(select(ActivityEvent.user_id).where(ActivityEvent.created_at >= today, ActivityEvent.user_id.in_(student_ids))).all())
    active |= set(db.scalars(select(UserPresence.user_id).where(UserPresence.last_seen_at >= today, UserPresence.user_id.in_(student_ids))).all())
    online = sum(1 for p in db.scalars(select(UserPresence)).all() if _is_online(p))
    completed = sum(1 for e in db.scalars(select(Enrollment)).all() if completion(db, e.user_id, e.course)["completed"])
    verified = db.scalar(select(func.count()).select_from(Payment).where(Payment.status == "verified")) or 0
    unread = db.scalar(select(func.count()).select_from(AdminNotification).where(AdminNotification.is_read.is_(False))) or 0
    return {
        "unread_notifications": unread,
        "total_students": students, "active_today": len(active), "online_now": online,
        "total_courses": db.scalar(select(func.count()).select_from(Course).where(Course.published.is_(True))) or 0,
        "total_enrollments": db.scalar(select(func.count()).select_from(Enrollment)) or 0,
        "completed_courses": completed,
        "quiz_attempts": db.scalar(select(func.count()).select_from(QuizAttempt).where(QuizAttempt.submitted_at.is_not(None))) or 0,
        "certificates_issued": db.scalar(select(func.count()).select_from(Certificate)) or 0,
        "verified_payments": verified if payments.configured() else None,
        "payments_connected": payments.configured(),
    }


# --------------------------------------------------------------------------- students
def _student_row(db: Session, u: User) -> dict:
    p = db.get(UserPresence, u.id)
    last = db.scalar(select(func.max(ActivityEvent.created_at)).where(ActivityEvent.user_id == u.id))
    enr = []
    for e in db.scalars(select(Enrollment).where(Enrollment.user_id == u.id)).all():
        c = completion(db, u.id, e.course)
        enr.append({"course": e.course.title, "slug": e.course.slug, "level": e.course.level,
                    "percent": c["percent"], "completed": c["completed"]})
    best = db.scalar(select(func.max(QuizAttempt.score_pct)).where(QuizAttempt.user_id == u.id, QuizAttempt.submitted_at.is_not(None)))
    prof = db.get(StudentProfile, u.id)
    return {"id": u.id, "display_name": u.display_name, "email": u.email, "status": u.status,
            "phone": prof.phone if prof else "", "college_name": prof.college_name if prof else "",
            "registered_at": _iso(u.created_at), "last_login_at": _iso(u.last_login_at), "last_activity_at": _iso(last),
            "last_seen_at": _iso(p.last_seen_at) if p else None, "last_logout_at": _iso(p.last_logout_at) if p else None,
            "online": _is_online(p), "enrollments": enr, "completed_courses": sum(1 for x in enr if x["completed"]),
            "quiz_attempts": db.scalar(select(func.count()).select_from(QuizAttempt).where(
                QuizAttempt.user_id == u.id, QuizAttempt.submitted_at.is_not(None))) or 0,
            "best_quiz_score": best,
            "certificates": db.scalar(select(func.count()).select_from(Certificate).where(Certificate.user_id == u.id)) or 0}


def _student_query(q, status, course, level):
    stmt = select(User).where(User.role == "student")
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(User.display_name).like(like), func.lower(User.email).like(like), User.id.like(like)))
    if status:
        stmt = stmt.where(User.status == status)
    if course or level:
        sub = select(Enrollment.user_id).join(Course, Course.id == Enrollment.course_id)
        if course:
            sub = sub.where(Course.slug == course)
        if level:
            sub = sub.where(Course.level == level)
        stmt = stmt.where(User.id.in_(sub))
    return stmt


@router.get("/students")
def students(q: Optional[str] = Query(None, max_length=100), status: Optional[Literal["active", "disabled"]] = None,
             course: Optional[str] = Query(None, max_length=80), level: Optional[Literal["beginner", "intermediate", "advanced"]] = None,
             sort: Literal["registered", "activity"] = "registered", order: Literal["asc", "desc"] = "desc",
             page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
             _: User = Depends(require_admin), db: Session = Depends(get_db)):
    stmt = _student_query(q, status, course, level)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    if sort == "activity":
        la = select(ActivityEvent.user_id.label("uid"), func.max(ActivityEvent.created_at).label("la")).group_by(ActivityEvent.user_id).subquery()
        stmt = stmt.outerjoin(la, la.c.uid == User.id)
        key = func.coalesce(la.c.la, User.created_at)
    else:
        key = User.created_at
    stmt = stmt.order_by(key.desc() if order == "desc" else key.asc()).offset((page - 1) * page_size).limit(page_size)
    return {"items": [_student_row(db, u) for u in db.scalars(stmt).all()], "total": total, "page": page, "page_size": page_size}


def _csv_safe(v) -> str:
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s  # blocks spreadsheet formula injection


@router.get("/students/export.csv")
def export_students(q: Optional[str] = None, status: Optional[Literal["active", "disabled"]] = None,
                    admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["id", "display_name", "email", "status", "registered_at", "last_login_at", "last_activity_at",
                "courses_enrolled", "completed_courses", "quiz_attempts", "best_quiz_score", "phone", "college_name", "school_name", "tenth_mark", "twelfth_mark", "degree", "year_of_study", "city"])
    for u in db.scalars(_student_query(q, status, None, None).order_by(User.created_at)).all():
        r = _student_row(db, u)
        w.writerow([_csv_safe(x) for x in [r["id"], r["display_name"], r["email"], r["status"], r["registered_at"], r["last_login_at"],
                                           r["last_activity_at"], len(r["enrollments"]), r["completed_courses"], r["quiz_attempts"], r["best_quiz_score"],
                                           *[profile_out(db, u)[k] for k in PROFILE_KEYS]]])
    audit(db, admin, "student.export", "students", f"filters q={q!r} status={status!r}")
    db.commit()
    return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=students.csv"})


@router.get("/students/{student_id}")
def student_detail(student_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.get(User, student_id)
    if u is None or u.role != "student":
        raise HTTPException(status_code=404, detail="Student not found")
    history = [{"course": e.course.title, "enrolled_at": _iso(e.enrolled_at), "last_activity_at": _iso(e.last_activity_at),
                **completion(db, u.id, e.course)} for e in db.scalars(select(Enrollment).where(Enrollment.user_id == u.id)).all()]
    attempts = [{"quiz": a.quiz.title, "score_pct": a.score_pct, "passed": a.passed, "submitted_at": _iso(a.submitted_at)}
                for a in db.scalars(select(QuizAttempt).where(QuizAttempt.user_id == u.id, QuizAttempt.submitted_at.is_not(None))
                                    .order_by(QuizAttempt.id.desc()).limit(100)).all()]
    subs = db.scalar(select(func.count()).select_from(CodeSubmission).where(CodeSubmission.user_id == u.id)) or 0
    return {**_student_row(db, u), "profile": profile_out(db, u), "course_history": history, "assessment_history": attempts, "code_submissions": subs}


class StatusIn(BaseModel):
    status: Literal["active", "disabled"]


@router.patch("/students/{student_id}/status")
def set_student_status(student_id: str, body: StatusIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.get(User, student_id)
    if u is None or u.role != "student":
        raise HTTPException(status_code=404, detail="Student not found")
    u.status = body.status
    audit(db, admin, "student.status", u.id, f"set to {body.status}")
    db.commit()
    return {"id": u.id, "status": u.status}


@router.get("/live")
def live(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    online = [{"id": u.id, "display_name": u.display_name, "last_seen_at": _iso(p.last_seen_at)}
              for p, u in db.execute(select(UserPresence, User).join(User, User.id == UserPresence.user_id)
                                     .order_by(UserPresence.last_seen_at.desc())).all() if _is_online(p)]
    events = db.execute(select(ActivityEvent, User.display_name).join(User, User.id == ActivityEvent.user_id)
                        .order_by(ActivityEvent.id.desc()).limit(50)).all()
    return {"online_timeout_seconds": settings.online_timeout_seconds, "online": online,
            "recent_activity": [{"student": n, "kind": e.kind, "ref": e.ref, "at": _iso(e.created_at)} for e, n in events]}


@router.get("/enrollments")
def enrollments(course: Optional[str] = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                _: User = Depends(require_admin), db: Session = Depends(get_db)):
    stmt = select(Enrollment, User, Course).join(User, User.id == Enrollment.user_id).join(Course, Course.id == Enrollment.course_id)
    if course:
        stmt = stmt.where(Course.slug == course)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Enrollment.enrolled_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [{"student": u.display_name, "student_id": u.id, "course": c.title, "enrolled_at": _iso(e.enrolled_at),
                       **{k: v for k, v in completion(db, u.id, c).items() if k in ("percent", "completed")}} for e, u, c in rows]}


# --------------------------------------------------------------------------- content management
class CourseIn(BaseModel):
    slug: str = Field(pattern=SLUG, min_length=2, max_length=80)
    title: str = Field(min_length=2, max_length=120)
    category_id: str
    level: Literal["beginner", "intermediate", "advanced"]
    summary: str = Field("", max_length=2000)
    objectives: List[str] = Field(default_factory=list, max_length=20)
    est_minutes: int = Field(0, ge=0, le=6000)
    published: bool = False
    is_paid: bool = True                                   # False = free course, no payment before the certificate
    price_inr: Optional[int] = Field(None, ge=1, le=100_000)  # None = the default price from Settings
    project_title: str = Field("", max_length=160)
    project_description: str = Field("", max_length=3000)

    @model_validator(mode="after")
    def _check(self):
        if self.category_id not in CATEGORY_IDS:
            raise ValueError("unknown category_id")
        if any(len(o) > 200 for o in self.objectives):
            raise ValueError("objective too long")
        return self


class CoursePatch(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=120)
    category_id: Optional[str] = Field(None, max_length=60)
    level: Optional[Literal["beginner", "intermediate", "advanced"]] = None
    summary: Optional[str] = Field(None, max_length=2000)
    objectives: Optional[List[str]] = Field(None, max_length=20)
    est_minutes: Optional[int] = Field(None, ge=0, le=6000)
    published: Optional[bool] = None
    is_paid: Optional[bool] = None
    price_inr: Optional[int] = Field(None, ge=1, le=100_000)   # send null to go back to the default price
    project_title: Optional[str] = Field(None, max_length=160)
    project_description: Optional[str] = Field(None, max_length=3000)


def _announce_course(db: Session, c: Course) -> None:
    """Tells every student about a course that was just published (only when it has lessons to open)."""
    if any(l.published for m in c.modules for l in m.lessons):
        broadcast(db, "new_course", f"New course: {c.title}", c.summary[:200] or "A new course is available now.", f"/courses/{c.slug}")


@router.get("/courses")
def admin_courses(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    items = []
    for c in db.scalars(select(Course).order_by(Course.id)).all():
        lessons = [l for m in c.modules for l in m.lessons]
        enr = db.scalars(select(Enrollment).where(Enrollment.course_id == c.id)).all()
        done = sum(1 for e in enr if completion(db, e.user_id, c)["completed"])
        items.append({"id": c.id, "slug": c.slug, "title": c.title, "level": c.level, "published": c.published, "status": c.status,
                      "category_id": c.category_id, "summary": c.summary, "objectives": c.objectives, "est_minutes": c.est_minutes,
                      "is_paid": c.is_paid, "price_inr": c.price_inr, "effective_price_inr": certificates.price_for(db, c),
                      "project_title": c.project_title, "project_description": c.project_description,
                      "modules": [{"id": m.id, "title": m.title} for m in c.modules], "lessons": len(lessons),
                      "enrollments": len(enr), "completion_rate_pct": round(100 * done / len(enr)) if enr else None})
    return {"items": items}


@router.post("/courses/publish-all")
def publish_all_courses(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    courses = db.scalars(select(Course)).all()
    for course in courses:
        course.published = True
        course.status = "available"
    audit(db, admin, "course.publish_all", "all courses", f"{len(courses)} courses")
    db.commit()
    return {"updated": len(courses)}


@router.post("/courses", status_code=201)
def create_course(body: CourseIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.scalar(select(Course.id).where(Course.slug == body.slug)):
        raise HTTPException(status_code=409, detail="A course with this slug already exists.")
    values = body.model_dump()
    values["status"] = "available" if body.published else "planned"
    c = Course(**values)
    db.add(c)
    db.flush()
    audit(db, admin, "course.create", c.slug)
    if c.published:
        _announce_course(db, c)
    db.commit()
    return {"id": c.id, "slug": c.slug}


@router.patch("/courses/{course_id}")
def update_course(course_id: int, body: CoursePatch, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    c = db.get(Course, course_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Course not found")
    changes = body.model_dump(exclude_unset=True)
    if "category_id" in changes and changes["category_id"] not in CATEGORY_IDS:
        raise HTTPException(status_code=422, detail="Unknown category.")
    was_published = c.published
    if "published" in changes:
        if changes["published"]:
            changes["status"] = "available"
        else:
            has_lessons = any(m.lessons for m in c.modules)
            changes["status"] = "in_development" if has_lessons else "planned"
    for k, v in changes.items():
        setattr(c, k, v)
    audit(db, admin, "course.update", c.slug, ", ".join(sorted(changes)))
    if c.published and not was_published:
        _announce_course(db, c)
    db.commit()
    return {"id": c.id, "published": c.published, "is_paid": c.is_paid}


class ModuleIn(BaseModel):
    course_id: int
    title: str = Field(min_length=2, max_length=120)


@router.post("/modules", status_code=201)
def create_module(body: ModuleIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    c = db.get(Course, body.course_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Course not found")
    m = Module(course_id=c.id, title=body.title, position=len(c.modules) + 1)
    db.add(m)
    db.flush()
    audit(db, admin, "module.create", f"{c.slug}/{m.title}")
    db.commit()
    return {"id": m.id}


class LessonIn(BaseModel):
    module_id: int
    slug: str = Field(pattern=SLUG, min_length=2, max_length=80)
    title: str = Field(min_length=2, max_length=160)
    body_md: str = Field("", max_length=50_000)
    example_code: str = Field("", max_length=10_000)
    example_lang: Literal["python", "java", "c", "cpp", "html", "css", "javascript"] = "python"
    expected_output: str = Field("", max_length=5_000)
    published: bool = False


class LessonPatch(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=160)
    body_md: Optional[str] = Field(None, max_length=50_000)
    example_code: Optional[str] = Field(None, max_length=10_000)
    example_lang: Optional[Literal["python", "java", "c", "cpp", "html", "css", "javascript"]] = None
    expected_output: Optional[str] = Field(None, max_length=5_000)
    published: Optional[bool] = None


@router.post("/lessons", status_code=201)
def create_lesson(body: LessonIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    m = db.get(Module, body.module_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Module not found")
    if any(l.slug == body.slug for mod in m.course.modules for l in mod.lessons):
        raise HTTPException(status_code=409, detail="A lesson with this slug already exists in the course.")
    data = body.model_dump()
    data.pop("module_id")
    l = Lesson(module_id=m.id, position=len(m.lessons) + 1, **data)
    db.add(l)
    db.flush()
    audit(db, admin, "lesson.create", f"{m.course.slug}/{l.slug}")
    db.commit()
    return {"id": l.id}


@router.patch("/lessons/{lesson_id}")
def update_lesson(lesson_id: int, body: LessonPatch, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    l = db.get(Lesson, lesson_id)
    if l is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(l, k, v)  # progress rows reference the lesson id, so student progress is preserved
    audit(db, admin, "lesson.update", f"{l.module.course.slug}/{l.slug}", ", ".join(sorted(changes)))
    db.commit()
    return {"id": l.id, "published": l.published}


class OptionIn(BaseModel):
    id: str = Field(min_length=1, max_length=10)
    text: str = Field(min_length=1, max_length=300)


class QuestionIn(BaseModel):
    qtype: Literal["single", "multiple", "short"]
    prompt: str = Field(min_length=3, max_length=2000)
    options: List[OptionIn] = Field(default_factory=list, max_length=8)
    answer: List[str] = Field(min_length=1, max_length=8)
    explanation: str = Field("", max_length=2000)

    @model_validator(mode="after")
    def _check(self):
        ids = {o.id for o in self.options}
        if self.qtype == "short":
            if self.options:
                raise ValueError("short questions take no options")
        else:
            if len(self.options) < 2 or len(ids) != len(self.options):
                raise ValueError("need at least two options with unique ids")
            if not set(self.answer) <= ids or (self.qtype == "single" and len(self.answer) != 1):
                raise ValueError("answer must reference option ids (exactly one for single)")
        return self


class QuizIn(BaseModel):
    course_slug: str
    title: str = Field(min_length=2, max_length=160)
    kind: Literal["chapter", "final", "practice"] = "chapter"
    pass_mark: int = Field(70, ge=1, le=100)
    time_limit_minutes: Optional[int] = Field(None, ge=1, le=240)
    published: bool = False
    questions: List[QuestionIn] = Field(min_length=1, max_length=100)


class QuizPatch(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=160)
    pass_mark: Optional[int] = Field(None, ge=1, le=100)
    time_limit_minutes: Optional[int] = Field(None, ge=1, le=240)
    published: Optional[bool] = None


@router.post("/quizzes", status_code=201)
def create_quiz(body: QuizIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    c = db.scalar(select(Course).where(Course.slug == body.course_slug))
    if c is None:
        raise HTTPException(status_code=404, detail="Course not found")
    quiz = Quiz(course_id=c.id, title=body.title, kind=body.kind, pass_mark=body.pass_mark,
                time_limit_minutes=body.time_limit_minutes, published=body.published)
    for i, q in enumerate(body.questions, 1):
        quiz.questions.append(Question(position=i, qtype=q.qtype, prompt=q.prompt, options=[o.model_dump() for o in q.options],
                                       answer=q.answer, explanation=q.explanation))
    db.add(quiz)
    db.flush()
    audit(db, admin, "quiz.create", f"{c.slug}/{quiz.title}")
    db.commit()
    return {"id": quiz.id}


@router.patch("/quizzes/{quiz_id}")
def update_quiz(quiz_id: int, body: QuizPatch, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(quiz, k, v)
    audit(db, admin, "quiz.update", str(quiz.id), ", ".join(sorted(changes)))
    db.commit()
    return {"id": quiz.id, "published": quiz.published}


@router.get("/courses/{course_id}")
def admin_course(course_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    c = db.get(Course, course_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return {"id": c.id, "slug": c.slug, "title": c.title, "published": c.published,
            "modules": [{"id": m.id, "title": m.title,
                         "lessons": [{"id": l.id, "slug": l.slug, "title": l.title, "published": l.published} for l in m.lessons]}
                        for m in c.modules]}


@router.get("/lessons/{lesson_id}")
def admin_lesson(lesson_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    l = db.get(Lesson, lesson_id)
    if l is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return {"id": l.id, "slug": l.slug, "title": l.title, "body_md": l.body_md, "example_code": l.example_code,
            "example_lang": l.example_lang, "expected_output": l.expected_output, "published": l.published}


@router.get("/quizzes")
def admin_quizzes(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {"items": [{"id": q.id, "title": q.title, "course": q.course.title, "course_slug": q.course.slug, "kind": q.kind,
                       "pass_mark": q.pass_mark, "time_limit_minutes": q.time_limit_minutes, "published": q.published,
                       "question_count": len(q.questions)} for q in db.scalars(select(Quiz).order_by(Quiz.id)).all()]}


@router.get("/quizzes/{quiz_id}")
def admin_quiz(quiz_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    q = db.get(Quiz, quiz_id)
    if q is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return {"id": q.id, "title": q.title, "kind": q.kind, "pass_mark": q.pass_mark, "published": q.published,
            "questions": [{"id": x.id, "position": x.position, "qtype": x.qtype, "prompt": x.prompt, "options": x.options,
                           "answer": x.answer, "explanation": x.explanation} for x in q.questions]}


@router.post("/quizzes/{quiz_id}/questions", status_code=201)
def add_question(quiz_id: int, body: QuestionIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    if len(quiz.questions) >= 100:
        raise HTTPException(status_code=409, detail="A quiz can have at most 100 questions.")
    quiz.questions.append(Question(position=len(quiz.questions) + 1, qtype=body.qtype, prompt=body.prompt,
                                   options=[o.model_dump() for o in body.options], answer=body.answer, explanation=body.explanation))
    audit(db, admin, "question.create", f"quiz {quiz.id}")
    db.commit()
    return {"question_count": len(quiz.questions)}


class TestIn(BaseModel):
    stdin: str = Field("", max_length=5000)
    expected: str = Field(max_length=5000)
    hidden: bool = False


class ChallengeIn(BaseModel):
    slug: str = Field(pattern=SLUG, min_length=2, max_length=80)
    title: str = Field(min_length=2, max_length=160)
    language: Literal["python", "java", "c", "cpp"] = "python"
    difficulty: Literal["easy", "medium", "hard"] = "easy"
    topic: str = Field("", max_length=60)
    statement_md: str = Field("", max_length=10_000)
    input_format: str = Field("", max_length=2000)
    output_format: str = Field("", max_length=2000)
    constraints: str = Field("", max_length=2000)
    starter_code: str = Field("", max_length=10_000)
    hints: List[str] = Field(default_factory=list, max_length=10)
    explanation: str = Field("", max_length=5000)
    tests: List[TestIn] = Field(min_length=1, max_length=50)
    published: bool = False


@router.post("/challenges", status_code=201)
def create_challenge(body: ChallengeIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.scalar(select(Challenge.id).where(Challenge.slug == body.slug)):
        raise HTTPException(status_code=409, detail="A challenge with this slug already exists.")
    data = body.model_dump()
    c = Challenge(**data)
    db.add(c)
    audit(db, admin, "challenge.create", body.slug)
    if c.published:
        broadcast(db, "new_challenge", f"New challenge: {c.title}", f"{c.difficulty.title()} {c.language} challenge. Try it now.", f"/challenges/{c.slug}")
    db.commit()
    return {"slug": body.slug}


class PublishIn(BaseModel):
    published: bool


@router.patch("/challenges/{slug}")
def publish_challenge(slug: str, body: PublishIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    c = db.scalar(select(Challenge).where(Challenge.slug == slug))
    if c is None:
        raise HTTPException(status_code=404, detail="Challenge not found")
    was = c.published
    c.published = body.published
    audit(db, admin, "challenge.update", slug, f"published={body.published}")
    if c.published and not was:
        broadcast(db, "new_challenge", f"New challenge: {c.title}", f"{c.difficulty.title()} {c.language} challenge. Try it now.", f"/challenges/{c.slug}")
    db.commit()
    return {"slug": slug, "published": c.published}


# --------------------------------------------------------------------------- audit, analytics, payments, certificates
@router.get("/audit-logs")
def audit_logs(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
               _: User = Depends(require_admin), db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(AuditLog)) or 0
    rows = db.execute(select(AuditLog, User.email).join(User, User.id == AuditLog.admin_id)
                      .order_by(AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [{"at": _iso(a.created_at), "admin": e, "action": a.action, "target": a.target, "detail": a.detail} for a, e in rows]}


DEFINITIONS = {
    "registrations": "Student accounts created per UTC day.",
    "daily_active": "Distinct students with at least one recorded event (login, lesson completed, quiz submitted, challenge submitted) per UTC day. Heartbeats are not counted.",
    "monthly_active": "Distinct students with at least one recorded event in the 30 days ending on the range end date.",
    "enrollments": "Enrollments created per UTC day.",
    "completion": "Per course: students who finished every published lesson (and passed the final exam, if one is published) divided by enrolled students. All time.",
    "quiz_performance": "Per quiz, submitted attempts in the range: average score and share that passed.",
    "challenges": "Submissions in the range, distinct students who submitted, and fully accepted submissions.",
    "popular_courses": "Courses ranked by total enrollments, all time.",
    "retention_7d": "Among students registered in the range at least 7 days ago: share with a recorded event on a later day within 7 days of registering.",
    "certificates_issued": "Certificates issued after course completion and a verified payment.",
    "revenue": "Sum of verified Razorpay payments (paid_at inside the range), in rupees. Pending or failed orders are never counted.",
}


@router.get("/analytics")
def analytics(from_: Optional[date] = Query(None, alias="from"), to: Optional[date] = None,
              _: User = Depends(require_admin), db: Session = Depends(get_db)):
    to = to or _now().date()
    from_ = from_ or to - timedelta(days=29)
    if from_ > to or (to - from_).days > 366:
        raise HTTPException(status_code=422, detail="Choose a range of at most 366 days, with from on or before to.")
    start = datetime.combine(from_, time.min, tzinfo=timezone.utc)
    end = datetime.combine(to + timedelta(days=1), time.min, tzinfo=timezone.utc)
    days = [from_ + timedelta(days=i) for i in range((to - from_).days + 1)]

    def series(dates):
        counts: Dict[date, int] = {}
        for d in dates:
            counts[d] = counts.get(d, 0) + 1
        return [{"date": d.isoformat(), "count": counts.get(d, 0)} for d in days]

    day = lambda dt: _aware(dt).date()
    regs = db.scalars(select(User.created_at).where(User.role == "student", User.created_at >= start, User.created_at < end)).all()
    enr = db.scalars(select(Enrollment.enrolled_at).where(Enrollment.enrolled_at >= start, Enrollment.enrolled_at < end)).all()
    student_ids = select(User.id).where(User.role == "student")
    ev = db.execute(select(ActivityEvent.user_id, ActivityEvent.created_at).where(
        ActivityEvent.created_at >= start, ActivityEvent.created_at < end, ActivityEvent.user_id.in_(student_ids))).all()
    dau_pairs = {(u, day(t)) for u, t in ev}
    mau_start = datetime.combine(to - timedelta(days=29), time.min, tzinfo=timezone.utc)
    mau = len(set(db.scalars(select(ActivityEvent.user_id).where(
        ActivityEvent.created_at >= mau_start, ActivityEvent.created_at < end, ActivityEvent.user_id.in_(student_ids))).all()))

    cutoff = _now() - timedelta(days=7)
    eligible = db.execute(select(User.id, User.created_at).where(User.role == "student", User.created_at >= start,
                                                                 User.created_at < end, User.created_at <= cutoff)).all()
    returned = 0
    for uid, created in eligible:
        r = day(created)
        stamps = db.scalars(select(ActivityEvent.created_at).where(ActivityEvent.user_id == uid)).all()
        returned += any(r < day(t) <= r + timedelta(days=7) for t in stamps)

    courses = []
    for c in db.scalars(select(Course).where(Course.published.is_(True))).all():
        es = db.scalars(select(Enrollment).where(Enrollment.course_id == c.id)).all()
        done = sum(1 for e in es if completion(db, e.user_id, c)["completed"])
        courses.append({"course": c.title, "enrolled": len(es), "completed": done,
                        "completion_rate_pct": round(100 * done / len(es)) if es else None})
    quizzes = []
    for qz in db.scalars(select(Quiz)).all():
        at = db.scalars(select(QuizAttempt).where(QuizAttempt.quiz_id == qz.id, QuizAttempt.submitted_at >= start,
                                                  QuizAttempt.submitted_at < end)).all()
        quizzes.append({"quiz": qz.title, "attempts": len(at),
                        "average_score_pct": round(sum(a.score_pct or 0 for a in at) / len(at)) if at else None,
                        "pass_rate_pct": round(100 * sum(1 for a in at if a.passed) / len(at)) if at else None})
    paid = [Payment.status == "verified", Payment.paid_at >= start, Payment.paid_at < end]
    rev = db.scalar(select(func.coalesce(func.sum(Payment.amount_minor), 0)).where(*paid)) or 0
    rev_n = db.scalar(select(func.count()).select_from(Payment).where(*paid)) or 0
    subs = db.execute(select(CodeSubmission.user_id, CodeSubmission.status).where(CodeSubmission.created_at >= start, CodeSubmission.created_at < end)).all()
    return {
        "range": {"from": from_.isoformat(), "to": to.isoformat()},
        "registrations": series([day(t) for t in regs]), "enrollments": series([day(t) for t in enr]),
        "daily_active": series([d for _, d in dau_pairs]), "monthly_active": mau,
        "completion": courses, "quiz_performance": quizzes,
        "challenges": {"submissions": len(subs), "students": len({u for u, _ in subs}), "accepted": sum(1 for _, s in subs if s == "accepted")},
        "popular_courses": sorted(courses, key=lambda x: -x["enrolled"])[:5],
        "retention_7d": {"eligible": len(eligible), "returned": returned,
                         "rate_pct": round(100 * returned / len(eligible)) if eligible else None},
        "certificates_issued": db.scalar(select(func.count()).select_from(Certificate)) or 0,
        "revenue": {"connected": payments.configured(), "verified_payments": rev_n, "verified_revenue_inr": rev / 100,
                    "message": "Revenue is the sum of verified payments only." if payments.configured() else "Payments are not configured, so no revenue is shown."},
        "definitions": DEFINITIONS,
    }


@router.get("/payments")
def admin_payments(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.execute(select(Payment, User.display_name, User.email, Course.title)
                      .join(User, User.id == Payment.user_id).outerjoin(Course, Course.id == Payment.course_id)
                      .order_by(Payment.paid_at.desc().nullslast(), Payment.id.desc()).limit(200)).all()
    total = db.scalar(select(func.coalesce(func.sum(Payment.amount_minor), 0)).where(Payment.status == "verified")) or 0
    return {"connected": payments.configured(), "verified_revenue_inr": total / 100,
            "message": None if payments.configured() else "Payments are not configured: add the Razorpay keys to backend/.env.",
            "items": [{"order_id": p.id, "student": n, "email": e, "course": c, "amount_inr": p.amount_minor / 100, "status": p.status,
                       "transaction_ref": p.transaction_ref, "paid_at": _iso(p.paid_at), "gateway": p.gateway, "method": p.method,
                       "failure_reason": p.failure_reason, "created_at": _iso(p.created_at) if p.created_at else None}
                      for p, n, e, c in rows]}


@router.get("/certificates")
def admin_certificates(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.execute(select(Certificate, User.display_name, User.email, Course.title)
                      .join(User, User.id == Certificate.user_id).join(Course, Course.id == Certificate.course_id)
                      .order_by(Certificate.issued_at.desc())).all()
    items = []
    for c, n, e, t in rows:
        d = db.get(CertificateDelivery, c.id)
        items.append({"id": c.id, "student": n, "email": e, "course": t, "issued_at": _iso(c.issued_at),
                      "delivered": None if d is None else {"method": d.method, "sent_at": _iso(d.sent_at)}})
    return {"email_configured": mailer.configured(), "items": items}


def _cert_or_404(db: Session, cid: str) -> Certificate:
    c = db.get(Certificate, cid)
    if c is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return c


def _mark_delivered(db: Session, cid: str, method: str, admin: User) -> None:
    d = db.get(CertificateDelivery, cid) or CertificateDelivery(certificate_id=cid, method=method, by_admin_id=admin.id)
    d.method, d.sent_at, d.by_admin_id = method, _now(), admin.id
    db.add(d)


@router.post("/certificates/{cid}/send-email")
def send_certificate_email(cid: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    cert = _cert_or_404(db, cid)
    student, course = db.get(User, cert.user_id), db.get(Course, cert.course_id)
    img, base = certificates.render_for(db, cert)
    try:
        mailer.send_mail(student.email, f"Your SkillForge Learning certificate: {course.title}",
                         f"Hello {student.display_name},\n\nCongratulations on completing {course.title}. "
                         f"Your certificate is attached.\n\nSkillForge Learning", [(f"{base}.pdf", to_pdf(img), "application/pdf")])
    except mailer.MailUnavailable as e:
        raise HTTPException(status_code=503, detail=f"{e} Download the certificate and email it manually, then use Mark as sent.")
    _mark_delivered(db, cid, "email", admin)
    audit(db, admin, "certificate.email", cid, f"to {student.email}")
    db.commit()
    return {"sent": True}


@router.post("/certificates/{cid}/mark-sent")
def mark_certificate_sent(cid: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _cert_or_404(db, cid)
    _mark_delivered(db, cid, "manual", admin)
    audit(db, admin, "certificate.mark_sent", cid)
    db.commit()
    return {"sent": True}


@router.get("/notifications")
def notifications(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(AdminNotification).order_by(AdminNotification.id.desc()).limit(50)).all()
    return {"unread": sum(1 for n in rows if not n.is_read),
            "items": [{"id": n.id, "kind": n.kind, "message": n.message, "ref": n.ref, "read": n.is_read,
                       "emailed": n.emailed, "at": _iso(n.created_at)} for n in rows]}


@router.post("/notifications/read-all")
def read_all_notifications(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    for n in db.scalars(select(AdminNotification).where(AdminNotification.is_read.is_(False))).all():
        n.is_read = True
    db.commit()
    return {"ok": True}


@router.patch("/questions/{question_id}")
def edit_question(question_id: int, body: QuestionIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    q = db.get(Question, question_id)
    if q is None:
        raise HTTPException(status_code=404, detail="Question not found")
    q.qtype, q.prompt, q.options = body.qtype, body.prompt, [o.model_dump() for o in body.options]
    q.answer, q.explanation = body.answer, body.explanation
    audit(db, admin, "question.update", f"quiz {q.quiz_id} / question {q.id}")
    db.commit()
    return {"id": q.id}


@router.delete("/questions/{question_id}")
def delete_question(question_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    q = db.get(Question, question_id)
    if q is None:
        raise HTTPException(status_code=404, detail="Question not found")
    quiz = q.quiz
    quiz.questions.remove(q)
    for i, x in enumerate(quiz.questions, 1):
        x.position = i
    audit(db, admin, "question.delete", f"quiz {quiz.id}", q.prompt[:200])
    db.commit()
    return {"question_count": len(quiz.questions)}


@public_router.get("/certificates/verify/{certificate_id}")
def verify_certificate(certificate_id: str, db: Session = Depends(get_db)):
    c = db.get(Certificate, certificate_id)
    if c is None or c.status != "valid":
        raise HTTPException(status_code=404, detail="Certificate not found")
    u = db.get(User, c.user_id)
    return {"valid": True, "student": u.display_name if u else "", "course": db.get(Course, c.course_id).title, "issued_at": _iso(c.issued_at)}
