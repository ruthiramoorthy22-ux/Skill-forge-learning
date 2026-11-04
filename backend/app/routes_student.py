"""Student side: profile details and the project submission for a course."""
import base64
import io
import re
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .deps import get_current_user
from .models import AdminNotification, Certificate, Course, Enrollment, ProjectSubmission, StudentProfile, User
from .progress import completion
from .routes_learning import _require_course

router = APIRouter(prefix="/api")
_now = lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc)  # noqa: E731


def _clean(v: str) -> str:
    return re.sub(r"\s+", " ", v or "").strip()


def _phone(v: str) -> str:
    v = _clean(v)
    if v and not re.fullmatch(r"\+?[0-9][0-9 \-]{5,18}[0-9]", v):
        raise ValueError("Enter a valid phone number, digits only (a leading + is allowed).")
    return v


def _mark(v: str) -> str:
    """10th / 12th mark: a number up to 100 (percentage) or a total like 475/500; an optional % sign is kept."""
    v = _clean(v)
    if not v:
        return ""
    if not re.fullmatch(r"\d{1,4}(\.\d{1,2})?\s*(%|/\s*\d{1,4})?", v):
        raise ValueError("Enter the mark as a percentage (for example 85.5) or as marks out of total (for example 475/500).")
    return v


class ProfileFields(BaseModel):
    phone: str = Field("", max_length=20)
    college_name: str = Field("", max_length=160)
    school_name: str = Field("", max_length=160)
    tenth_mark: str = Field("", max_length=12)
    twelfth_mark: str = Field("", max_length=12)
    degree: str = Field("", max_length=120)
    year_of_study: str = Field("", max_length=30)
    city: str = Field("", max_length=80)

    @field_validator("phone")
    @classmethod
    def _p(cls, v):
        return _phone(v)

    @field_validator("tenth_mark", "twelfth_mark")
    @classmethod
    def _m(cls, v):
        return _mark(v)

    @field_validator("college_name", "school_name", "degree", "year_of_study", "city")
    @classmethod
    def _c(cls, v):
        return _clean(v)


class ProfileUpdate(ProfileFields):
    display_name: str = Field(min_length=1, max_length=80)

    @field_validator("display_name")
    @classmethod
    def _n(cls, v):
        v = _clean(v)
        if not v:
            raise ValueError("Name cannot be empty.")
        return v


PROFILE_KEYS = ("phone", "college_name", "school_name", "tenth_mark", "twelfth_mark", "degree", "year_of_study", "city")


def avatar_url(p: Optional[StudentProfile]) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(p.avatar).decode() if p is not None and p.avatar else ""


def profile_out(db: Session, user: User) -> dict:
    p = db.get(StudentProfile, user.id)
    return {"display_name": user.display_name, "email": user.email, **{k: (getattr(p, k) if p else "") for k in PROFILE_KEYS},
            "avatar": avatar_url(p)}


def save_profile(db: Session, user_id: str, data: dict) -> None:
    p = db.get(StudentProfile, user_id)
    if p is None:
        p = StudentProfile(user_id=user_id)
        db.add(p)
    for k in PROFILE_KEYS:
        if k in data:
            setattr(p, k, data[k])
    p.updated_at = _now()


@router.get("/me/profile")
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return profile_out(db, user)


@router.put("/me/profile")
def put_profile(body: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.display_name != user.display_name:
        if db.scalar(select(Certificate.id).where(Certificate.user_id == user.id).limit(1)):
            raise HTTPException(status_code=409, detail="Your name is locked because a certificate was issued with it. Ask the admin to change it.")
        user.display_name = body.display_name
    save_profile(db, user.id, body.model_dump())
    db.commit()
    return profile_out(db, user)


# --------------------------------------------------------------------------- profile picture
class AvatarIn(BaseModel):
    image: str = Field(max_length=900_000)   # a data URL (png, jpeg or webp), made smaller in the browser first


def make_avatar(data_url: str) -> bytes:
    """Decodes the upload, checks it really is an image, and re-encodes it as a 256x256 JPEG. Nothing the user sent is stored as is."""
    m = re.fullmatch(r"data:image/(png|jpeg|jpg|webp);base64,([A-Za-z0-9+/=\s]+)", data_url.strip())
    if not m:
        raise HTTPException(status_code=422, detail="Choose a PNG, JPG or WebP picture.")
    try:
        raw = base64.b64decode(m.group(2), validate=False)
        if len(raw) > 600_000:
            raise HTTPException(status_code=413, detail="The picture is too large. Choose a smaller one.")
        img = Image.open(io.BytesIO(raw))
        if img.format not in ("PNG", "JPEG", "WEBP") or img.width * img.height > 16_000_000:
            raise HTTPException(status_code=422, detail="Choose a PNG, JPG or WebP picture.")
        img = ImageOps.exif_transpose(img).convert("RGB")
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(status_code=422, detail="That file is not a valid picture.")
    img = ImageOps.fit(img, (256, 256), method=Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85, optimize=True)
    return buf.getvalue()


@router.get("/me/avatar")
def get_avatar(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"avatar": avatar_url(db.get(StudentProfile, user.id))}


@router.put("/me/avatar")
def put_avatar(body: AvatarIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = make_avatar(body.image)
    p = db.get(StudentProfile, user.id)
    if p is None:
        p = StudentProfile(user_id=user.id)
        db.add(p)
    p.avatar, p.updated_at = data, _now()
    db.commit()
    return {"avatar": avatar_url(p)}


@router.delete("/me/avatar")
def delete_avatar(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.get(StudentProfile, user.id)
    if p is not None:
        p.avatar = None
        db.commit()
    return {"avatar": ""}


# --------------------------------------------------------------------------- project submission
def _url(v: str) -> str:
    v = (v or "").strip()
    if not v:
        return ""
    u = urlparse(v)
    if u.scheme not in ("http", "https") or not u.netloc:
        raise ValueError("Links must start with http:// or https://")
    return v


class SubmissionIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=20, max_length=3000)
    repo_url: str = Field("", max_length=300)
    demo_url: str = Field("", max_length=300)

    @field_validator("title")
    @classmethod
    def _t(cls, v):
        return _clean(v)

    @field_validator("repo_url", "demo_url")
    @classmethod
    def _u(cls, v):
        return _url(v)


def submission_out(s: Optional[ProjectSubmission]) -> Optional[dict]:
    if s is None:
        return None
    return {"id": s.id, "title": s.title, "description": s.description, "repo_url": s.repo_url, "demo_url": s.demo_url,
            "status": s.status, "admin_feedback": s.admin_feedback, "submitted_at": s.submitted_at.isoformat(),
            "reviewed_at": s.reviewed_at.isoformat() if s.reviewed_at else None}


def _enrolled(db: Session, user: User, slug: str) -> Course:
    course = _require_course(db, slug)
    if db.scalar(select(Enrollment.id).where(Enrollment.user_id == user.id, Enrollment.course_id == course.id)) is None:
        raise HTTPException(status_code=403, detail="Enroll in this course first.")
    return course


@router.get("/courses/{slug}/project")
def my_project(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    course = _enrolled(db, user, slug)
    sub = db.scalar(select(ProjectSubmission).where(ProjectSubmission.user_id == user.id, ProjectSubmission.course_id == course.id))
    return {"can_submit": completion(db, user.id, course)["completed"], "submission": submission_out(sub),
            "assigned": {"title": course.project_title, "description": course.project_description} if course.project_title else None}


@router.put("/courses/{slug}/project")
def submit_project(slug: str, body: SubmissionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    course = _enrolled(db, user, slug)
    if not completion(db, user.id, course)["completed"]:
        raise HTTPException(status_code=403, detail="Finish every lesson and pass the final exam before submitting your project.")
    sub = db.scalar(select(ProjectSubmission).where(ProjectSubmission.user_id == user.id, ProjectSubmission.course_id == course.id))
    if sub is not None and sub.status == "approved":
        raise HTTPException(status_code=409, detail="Your project was already approved. Ask the admin if something must change.")
    if course.project_title:  # the admin chose the project name for this course
        body.title = course.project_title
    first = sub is None
    if first:
        sub = ProjectSubmission(user_id=user.id, course_id=course.id)
        db.add(sub)
    sub.title, sub.description, sub.repo_url, sub.demo_url = body.title, body.description, body.repo_url, body.demo_url
    sub.status, sub.admin_feedback, sub.reviewed_at, sub.reviewed_by, sub.submitted_at = "submitted", "", None, None, _now()
    db.flush()
    db.add(AdminNotification(kind="project_submitted", ref=str(sub.id), message=(
        f"{user.display_name} ({user.email}) {'submitted' if first else 're-submitted'} the project \"{sub.title}\" for {course.title}. "
        f"Open Admin > Submissions to review it.")))
    db.commit()
    return {"submission": submission_out(sub)}
