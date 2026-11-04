from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .deps import COOKIE, get_current_user, read_token
from .gamification import record_activity
from .models import Certificate, User, UserPresence
from .security import decode_token
from .ratelimit import auth_limiter
from .security import create_token, hash_password, verify_password

router = APIRouter(prefix="/api")


class RegisterIn(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("display_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("display name required")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ProfileIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)

    _strip = field_validator("display_name")(RegisterIn._strip.__func__)


def user_out(u: User) -> dict:
    created = u.created_at
    if created.tzinfo is None:  # SQLite drops the timezone; stored values are UTC
        created = created.replace(tzinfo=timezone.utc)
    return {"id": u.id, "email": u.email, "display_name": u.display_name,
            "role": u.role, "created_at": created.isoformat()}


def _out(request: Request, user: User) -> dict:
    out = user_out(user)
    if request.headers.get("x-client") == "app":  # the Android app stores this token; the website never receives it
        out["token"] = create_token(user.id)
    return out


def _start_session(response: Response, user: User) -> None:
    response.set_cookie(
        COOKIE,
        create_token(user.id),
        httponly=True,
        samesite="none",
        secure=True,
        max_age=settings.session_hours * 3600,
        path="/"
    )


def _authenticate(body: LoginIn, request: Request, db: Session) -> User:
    email = body.email.lower()
    auth_limiter.check(f"{request.client.host if request.client else '?'}:{email}")
    user = db.scalar(select(User).where(User.email == email))
    ok = verify_password(user.password_hash if user else None, body.password)
    if not (user and ok):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="This account is disabled.")
    return user


@router.post("/auth/register", status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    email = body.email.lower()
    auth_limiter.check(f"{request.client.host if request.client else '?'}:register")
    if email == settings.admin_email:
        raise HTTPException(status_code=400, detail="This email address is reserved.")
    user = User(email=email, display_name=body.display_name, password_hash=hash_password(body.password),
                role="student", last_login_at=datetime.now(timezone.utc))
    try:
        db.add(user)
        db.flush()
        record_activity(db, user.id, "login")
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    _start_session(response, user)
    return _out(request, user)


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    user = _authenticate(body, request, db)
    user.last_login_at = datetime.now(timezone.utc)
    record_activity(db, user.id, "login")
    db.commit()
    _start_session(response, user)
    return _out(request, user)


@router.post("/auth/admin/login")
def admin_login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    user = _authenticate(body, request, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="This account is not authorized for administrator access.")
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    _start_session(response, user)
    return _out(request, user)


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = read_token(request)
    uid = decode_token(token) if token else None
    if uid and db.get(User, uid):
        p = db.get(UserPresence, uid) or UserPresence(user_id=uid)
        p.last_logout_at = datetime.now(timezone.utc)
        db.add(p)
        db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(user: User = Depends(get_current_user)):
    return user_out(user)


@router.patch("/me")
def update_profile(body: ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.display_name != user.display_name and db.scalar(select(Certificate.id).where(Certificate.user_id == user.id).limit(1)):
        raise HTTPException(status_code=409, detail="Your name is locked because a certificate was issued with it.")
    user.display_name = body.display_name
    db.commit()
    return user_out(user)
