"""Admin controls added on top of routes_admin: settings (price), certificate unlock, delete/edit for courses, modules,
lessons, quizzes, challenges, and projects. Every change is written to the audit log."""
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from . import app_settings, certificates, mailer
from .certificate_image import to_pdf
from .db import get_db
from .deps import require_admin
from .models import (Certificate, CertificateGrant, Challenge, CodeSubmission, Course, Enrollment, Lesson, LessonProgress,
                     Module, Payment, Project, ProjectSubmission, Quiz, QuizAttempt, StudentProfile, User)
from .notify import broadcast, notify_user
from .progress import completion
from .routes_admin import SLUG, ChallengeIn, _iso, audit
from .routes_student import PROFILE_KEYS, ProfileFields, _clean, profile_out, save_profile, submission_out

router = APIRouter(prefix="/api/admin")


# --------------------------------------------------------------------------- settings: one price for every course
class SettingsIn(BaseModel):
    certificate_price_inr: Optional[int] = Field(None, ge=1, le=app_settings.MAX_PRICE)
    certificate_release: Optional[Literal["auto", "admin"]] = None
    project_required: Optional[bool] = None


def _settings_out(db: Session) -> dict:
    return {"certificate_price_inr": app_settings.get_price(db), "certificate_release": app_settings.get_release_mode(db),
            "project_required": app_settings.get_project_required(db)}


@router.get("/settings")
def get_settings(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _settings_out(db)


@router.patch("/settings")
def patch_settings(body: SettingsIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if body.certificate_price_inr is not None:
        old = app_settings.get_price(db)
        app_settings.set_price(db, body.certificate_price_inr)
        audit(db, admin, "settings.price", "all courses", f"{old} -> {body.certificate_price_inr}")
    if body.certificate_release is not None:
        app_settings.set_release_mode(db, body.certificate_release)
        audit(db, admin, "settings.release", body.certificate_release)
    if body.project_required is not None:
        app_settings.set_project_required(db, body.project_required)
        audit(db, admin, "settings.project_required", "on" if body.project_required else "off")
    db.commit()
    return _settings_out(db)


# --------------------------------------------------------------------------- certificate requests and unlock
@router.get("/certificate-requests")
def certificate_requests(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Students who finished a course but have no certificate yet (waiting for payment or for the admin)."""
    items = []
    for enr, user, course in db.execute(select(Enrollment, User, Course).join(User, User.id == Enrollment.user_id)
                                        .join(Course, Course.id == Enrollment.course_id).order_by(Enrollment.id.desc())).all():
        if certificates.get_certificate(db, user.id, course.id) or not completion(db, user.id, course)["completed"]:
            continue
        items.append({"user_id": user.id, "student": user.display_name, "email": user.email, "course_id": course.id,
                      "course": course.title, "paid": certificates.has_verified_payment(db, user.id, course.id),
                      "project_approved": certificates.project_ok(db, user.id, course.id)})
    return {"items": items, "release_mode": app_settings.get_release_mode(db), "email_configured": mailer.configured()}


class UnlockIn(BaseModel):
    user_id: str = Field(max_length=36)
    course_id: int
    send_email: bool = False
    note: str = Field("", max_length=200)


@router.post("/certificate-unlock")
def unlock_certificate(body: UnlockIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    student, course = db.get(User, body.user_id), db.get(Course, body.course_id)
    if student is None or course is None:
        raise HTTPException(status_code=404, detail="Student or course not found")
    if not completion(db, student.id, course)["completed"]:
        raise HTTPException(status_code=409, detail="This student has not completed the course yet.")
    if not certificates.project_ok(db, student.id, course.id):
        raise HTTPException(status_code=409, detail="Review and approve this student's project first (Admin > Submissions), or turn the project requirement off in Settings.")
    if not certificates.has_grant(db, student.id, course.id):
        db.add(CertificateGrant(user_id=student.id, course_id=course.id, admin_id=admin.id, note=body.note))
        db.flush()
    cert = certificates.issue_if_eligible(db, student.id, course)
    paid = certificates.has_verified_payment(db, student.id, course.id)
    audit(db, admin, "certificate.unlock", f"{student.email} / {course.slug}", "paid" if paid else "unlocked without payment")
    db.commit()
    emailed, email_error = False, None
    if body.send_email and cert is not None:
        try:
            img, base = certificates.render_for(db, cert)
            mailer.send_mail(student.email, f"Your SkillForge Learning certificate: {course.title}",
                             f"Hello {student.display_name},\n\nCongratulations on completing {course.title}. "
                             f"Your certificate is attached and also available in your account.\n\nSkillForge Learning",
                             [(f"{base}.pdf", to_pdf(img), "application/pdf")])
            emailed = True
        except mailer.MailUnavailable as e:
            email_error = str(e)
    return {"unlocked": True, "certificate_id": cert.id if cert else None, "emailed": emailed, "email_error": email_error}


# --------------------------------------------------------------------------- delete / edit helpers
def _drop_lessons(db: Session, lesson_ids: List[int]) -> None:
    if lesson_ids:
        db.execute(delete(LessonProgress).where(LessonProgress.lesson_id.in_(lesson_ids)))
        db.execute(update(Enrollment).where(Enrollment.last_lesson_id.in_(lesson_ids)).values(last_lesson_id=None))


def _drop_quizzes(db: Session, quiz_ids: List[int]) -> None:
    if quiz_ids:
        db.execute(delete(QuizAttempt).where(QuizAttempt.quiz_id.in_(quiz_ids)))


@router.delete("/lessons/{lesson_id}")
def delete_lesson(lesson_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    l = db.get(Lesson, lesson_id)
    if l is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    module, label = l.module, f"{l.module.course.slug}/{l.slug}"
    _drop_lessons(db, [l.id])
    module.lessons.remove(l)
    db.flush()
    for i, x in enumerate(module.lessons, 1):
        x.position = i
    audit(db, admin, "lesson.delete", label)
    db.commit()
    return {"deleted": True}


class ModulePatch(BaseModel):
    title: str = Field(min_length=2, max_length=120)


@router.patch("/modules/{module_id}")
def rename_module(module_id: int, body: ModulePatch, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    m = db.get(Module, module_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Module not found")
    audit(db, admin, "module.update", f"{m.course.slug}/{m.title}", f"-> {body.title}")
    m.title = body.title
    db.commit()
    return {"id": m.id}


@router.delete("/modules/{module_id}")
def delete_module(module_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    m = db.get(Module, module_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Module not found")
    course = m.course
    _drop_lessons(db, [l.id for l in m.lessons])
    course.modules.remove(m)
    db.flush()
    for i, x in enumerate(course.modules, 1):
        x.position = i
    audit(db, admin, "module.delete", f"{course.slug}/{m.title}")
    db.commit()
    return {"deleted": True}


@router.delete("/quizzes/{quiz_id}")
def delete_quiz(quiz_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    q = db.get(Quiz, quiz_id)
    if q is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    _drop_quizzes(db, [q.id])
    audit(db, admin, "quiz.delete", f"{q.course.slug}/{q.title}", q.kind)
    db.delete(q)
    db.commit()
    return {"deleted": True}


@router.delete("/courses/{course_id}")
def delete_course(course_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    c = db.get(Course, course_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if db.scalar(select(Certificate.id).where(Certificate.course_id == c.id).limit(1)) or db.scalar(
            select(Payment.id).where(Payment.course_id == c.id, Payment.status == "verified").limit(1)):
        raise HTTPException(status_code=409, detail="Students already hold certificates or paid for this course. Unpublish it instead of deleting it.")
    _drop_lessons(db, [l.id for m in c.modules for l in m.lessons])
    quizzes = db.scalars(select(Quiz).where(Quiz.course_id == c.id)).all()
    _drop_quizzes(db, [q.id for q in quizzes])
    for q in quizzes:
        db.delete(q)
    db.execute(delete(Enrollment).where(Enrollment.course_id == c.id))
    db.execute(delete(CertificateGrant).where(CertificateGrant.course_id == c.id))
    db.execute(update(Payment).where(Payment.course_id == c.id).values(course_id=None))
    audit(db, admin, "course.delete", c.slug)
    db.delete(c)
    db.commit()
    return {"deleted": True}


# --------------------------------------------------------------------------- coding challenges (list, read, edit, delete)
def _challenge_out(c: Challenge) -> dict:
    return {"slug": c.slug, "title": c.title, "language": c.language, "difficulty": c.difficulty, "topic": c.topic,
            "statement_md": c.statement_md, "input_format": c.input_format, "output_format": c.output_format,
            "constraints": c.constraints, "starter_code": c.starter_code, "hints": c.hints, "explanation": c.explanation,
            "tests": c.tests, "published": c.published}


@router.get("/challenges")
def admin_challenges(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {"items": [{"slug": c.slug, "title": c.title, "language": c.language, "difficulty": c.difficulty,
                       "topic": c.topic, "tests": len(c.tests), "published": c.published}
                      for c in db.scalars(select(Challenge).order_by(Challenge.id)).all()]}


@router.get("/challenges/{slug}")
def admin_challenge(slug: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    c = db.scalar(select(Challenge).where(Challenge.slug == slug))
    if c is None:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return _challenge_out(c)


@router.put("/challenges/{slug}")
def replace_challenge(slug: str, body: ChallengeIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    c = db.scalar(select(Challenge).where(Challenge.slug == slug))
    if c is None:
        raise HTTPException(status_code=404, detail="Challenge not found")
    if body.slug != slug:
        raise HTTPException(status_code=422, detail="The slug of an existing challenge cannot be changed.")
    was = c.published
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    audit(db, admin, "challenge.edit", slug)
    if c.published and not was:
        broadcast(db, "new_challenge", f"New challenge: {c.title}", f"{c.difficulty.title()} {c.language} challenge. Try it now.", f"/challenges/{c.slug}")
    db.commit()
    return {"slug": slug}


@router.delete("/challenges/{slug}")
def delete_challenge(slug: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    c = db.scalar(select(Challenge).where(Challenge.slug == slug))
    if c is None:
        raise HTTPException(status_code=404, detail="Challenge not found")
    db.execute(update(CodeSubmission).where(CodeSubmission.challenge_id == c.id).values(challenge_id=None))
    audit(db, admin, "challenge.delete", slug)
    db.delete(c)
    db.commit()
    return {"deleted": True}


# --------------------------------------------------------------------------- projects
class ProjectIn(BaseModel):
    slug: str = Field(pattern=SLUG, min_length=2, max_length=80)
    title: str = Field(min_length=2, max_length=160)
    level: Literal["beginner", "intermediate", "advanced"] = "beginner"
    summary: str = Field("", max_length=1000)
    body_md: str = Field("", max_length=30_000)
    published: bool = True


class ProjectPatch(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=160)
    level: Optional[Literal["beginner", "intermediate", "advanced"]] = None
    summary: Optional[str] = Field(None, max_length=1000)
    body_md: Optional[str] = Field(None, max_length=30_000)
    published: Optional[bool] = None


def _project_out(p: Project) -> dict:
    return {"id": p.id, "slug": p.slug, "title": p.title, "level": p.level, "summary": p.summary,
            "body_md": p.body_md, "published": p.published}


@router.get("/projects")
def admin_projects(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {"items": [_project_out(p) for p in db.scalars(select(Project).order_by(Project.id)).all()]}


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.scalar(select(Project.id).where(Project.slug == body.slug)):
        raise HTTPException(status_code=409, detail="A project with this slug already exists.")
    p = Project(**body.model_dump())
    db.add(p)
    db.flush()
    audit(db, admin, "project.create", p.slug)
    db.commit()
    return {"id": p.id}


@router.patch("/projects/{project_id}")
def update_project(project_id: int, body: ProjectPatch, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Project not found")
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(p, k, v)
    audit(db, admin, "project.update", p.slug, ", ".join(sorted(changes)))
    db.commit()
    return _project_out(p)


@router.delete("/projects/{project_id}")
def delete_project(project_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Project not found")
    audit(db, admin, "project.delete", p.slug)
    db.delete(p)
    db.commit()
    return {"deleted": True}


# --------------------------------------------------------------------------- project submissions: review
def _sub_row(db: Session, s: ProjectSubmission) -> dict:
    u, c = db.get(User, s.user_id), db.get(Course, s.course_id)
    prof = db.get(StudentProfile, s.user_id)
    return {**submission_out(s), "student": u.display_name, "email": u.email, "user_id": u.id, "course": c.title, "course_id": c.id,
            "college_name": prof.college_name if prof else "", "paid": certificates.has_verified_payment(db, u.id, c.id),
            "certificate_issued": certificates.get_certificate(db, u.id, c.id) is not None}


@router.get("/project-submissions")
def project_submissions(status: Optional[Literal["submitted", "approved", "changes_requested"]] = None,
                        _: User = Depends(require_admin), db: Session = Depends(get_db)):
    stmt = select(ProjectSubmission).order_by(ProjectSubmission.submitted_at.desc())
    if status:
        stmt = stmt.where(ProjectSubmission.status == status)
    return {"items": [_sub_row(db, s) for s in db.scalars(stmt).all()]}


class ReviewIn(BaseModel):
    decision: Literal["approved", "changes_requested"]
    feedback: str = Field("", max_length=2000)
    release: bool = False     # approve AND unlock the certificate now (skips the payment)
    send_email: bool = False


@router.patch("/project-submissions/{submission_id}/review")
def review_submission(submission_id: int, body: ReviewIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    s = db.get(ProjectSubmission, submission_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    if body.decision == "changes_requested" and not body.feedback.strip():
        raise HTTPException(status_code=422, detail="Write what the student must change.")
    from datetime import datetime, timezone
    s.status, s.admin_feedback = body.decision, body.feedback.strip()
    s.reviewed_at, s.reviewed_by = datetime.now(timezone.utc), admin.id
    student, course = db.get(User, s.user_id), db.get(Course, s.course_id)
    cert = None
    if body.decision == "approved" and body.release:
        if not completion(db, student.id, course)["completed"]:
            raise HTTPException(status_code=409, detail="This student has not completed the course yet.")
        if not certificates.has_grant(db, student.id, course.id):
            db.add(CertificateGrant(user_id=student.id, course_id=course.id, admin_id=admin.id, note="released with project approval"))
            db.flush()
    db.flush()
    if body.decision == "approved":
        cert = certificates.issue_if_eligible(db, student.id, course)
    audit(db, admin, "project.review", f"{student.email} / {course.slug}", f"{body.decision}{', released' if body.release else ''}")
    if body.decision == "approved":
        price = certificates.price_for(db, course)
        if cert is not None:
            notify_user(db, student.id, "project", "Project approved", f"Your project was approved and your {course.title} certificate is ready.", "/certificates")
        elif price and not certificates.has_verified_payment(db, student.id, course.id):
            notify_user(db, student.id, "project", "Project approved: pay now", f"Your project \"{s.title}\" was approved. Pay Rs {price} to get your {course.title} certificate.", f"/courses/{course.slug}/pay")
        else:
            notify_user(db, student.id, "project", "Project approved", f"Your project \"{s.title}\" was approved.", f"/courses/{course.slug}")
    else:
        notify_user(db, student.id, "project", "Changes requested on your project", s.admin_feedback[:300], f"/courses/{course.slug}/pay")
    db.commit()
    emailed, email_error = False, None
    if body.send_email:
        try:
            if cert is not None:
                img, base = certificates.render_for(db, cert)
                mailer.send_mail(student.email, f"Your SkillForge Learning certificate: {course.title}",
                                 f"Hello {student.display_name},\n\nYour project \"{s.title}\" was approved. Your certificate is attached and also in your account.\n\nSkillForge Learning",
                                 [(f"{base}.pdf", to_pdf(img), "application/pdf")])
            else:
                msg = ("approved. You can now pay for and receive your certificate in your account." if body.decision == "approved"
                       else "reviewed. Please change the following and submit it again:\n\n" + s.admin_feedback)
                mailer.send_mail(student.email, f"Your project review: {s.title}", f"Hello {student.display_name},\n\nYour project \"{s.title}\" was {msg}\n\nSkillForge Learning")
            emailed = True
        except mailer.MailUnavailable as e:
            email_error = str(e)
    return {**_sub_row(db, s), "certificate_id": cert.id if cert else None, "emailed": emailed, "email_error": email_error}


# --------------------------------------------------------------------------- admin edits a student's details
class StudentEdit(ProfileFields):
    display_name: str = Field(min_length=1, max_length=80)
    email: EmailStr

    @field_validator("display_name")
    @classmethod
    def _n(cls, v):
        v = _clean(v)
        if not v:
            raise ValueError("Name cannot be empty.")
        return v


@router.put("/students/{student_id}/profile")
def edit_student(student_id: str, body: StudentEdit, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.get(User, student_id)
    if u is None or u.role != "student":
        raise HTTPException(status_code=404, detail="Student not found")
    email = str(body.email).strip().lower()
    if email != u.email and db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Another account already uses this email.")
    changed = [k for k, new in (("name", body.display_name), ("email", email)) if new != (u.display_name if k == "name" else u.email)]
    u.display_name, u.email = body.display_name, email
    data = body.model_dump()
    old = profile_out(db, u)
    changed += [k for k in PROFILE_KEYS if data[k] != old[k]]
    save_profile(db, u.id, data)
    audit(db, admin, "student.edit", u.id, "changed: " + (", ".join(changed) or "nothing"))
    db.commit()
    return profile_out(db, u)


# --------------------------------------------------------------------------- final exam results (hidden from students until released)
@router.get("/final-results")
def final_results(released: Optional[bool] = None, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    q = (select(QuizAttempt).join(Quiz, Quiz.id == QuizAttempt.quiz_id)
         .where(Quiz.kind == "final", QuizAttempt.submitted_at.is_not(None), QuizAttempt.score_pct.is_not(None)))
    if released is not None:
        q = q.where(QuizAttempt.result_released.is_(released))
    out = []
    for a in db.scalars(q.order_by(QuizAttempt.result_released, QuizAttempt.id.desc()).limit(300)).all():
        u = db.get(User, a.user_id)
        out.append({"attempt_id": a.id, "student_id": u.id, "student": u.display_name, "email": u.email,
                    "course": a.quiz.course.title, "score_pct": a.score_pct, "passed": bool(a.passed), "pass_mark": a.quiz.pass_mark,
                    "released": bool(a.result_released), "submitted_at": _iso(a.submitted_at)})
    return {"items": out}


@router.post("/final-results/{attempt_id}/release")
def release_final_result(attempt_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from datetime import datetime, timezone
    from .gamification import after_learning_event, grant_xp
    a = db.get(QuizAttempt, attempt_id)
    if a is None or a.quiz.kind != "final" or a.submitted_at is None or a.score_pct is None:
        raise HTTPException(status_code=404, detail="Final exam result not found")
    if not a.result_released:
        a.result_released, a.released_at = True, datetime.now(timezone.utc)
        u = db.get(User, a.user_id)
        if a.passed:
            grant_xp(db, u.id, "quiz_pass", a.quiz_id)
        after_learning_event(db, u)
        audit(db, admin, "final_result.release", str(a.id), f"{u.email} {a.quiz.course.slug} {a.score_pct}%")
        notify_user(db, u.id, "result", "Your final exam result is ready", f"{a.quiz.course.title}: open your result.", f"/courses/{a.quiz.course.slug}/result")
        db.commit()
    return {"attempt_id": a.id, "released": True}
