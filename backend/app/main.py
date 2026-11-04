from contextlib import asynccontextmanager
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from . import models  # noqa: F401  (registers tables)
from .catalog import CATEGORIES, COURSES
from .models import Project
from .config import settings
from .db import Base, SessionLocal, engine, get_db
from .routes_auth import router as auth_router
from .routes_learning import extra_courses, lesson_counts, pricing_map, router as learning_router
from .routes_admin import public_router as cert_router, router as admin_router
from .routes_admin_extra import router as admin_extra_router
from .routes_certs import router as certs_router
from .routes_me import router as me_router
from .routes_pay import router as pay_router
from .routes_notify import router as notify_router
from .routes_templates import router as templates_router
from .routes_quiz import router as quiz_router
from .routes_student import router as student_router
from .seed_assessments import seed_assessments
from .seed_content import seed_content
from .seed_projects import seed_projects


# Columns added after the first release. create_all() does not alter existing tables, so they are added here.
_PG = engine.dialect.name == "postgresql"
_TS = "TIMESTAMP WITH TIME ZONE" if _PG else "DATETIME"   # portable type names (SQLite and PostgreSQL)
_BLOB = "BYTEA" if _PG else "BLOB"
NEW_COLUMNS = [
    ("student_profiles", "tenth_mark", "VARCHAR(12) NOT NULL DEFAULT ''"),
    ("student_profiles", "twelfth_mark", "VARCHAR(12) NOT NULL DEFAULT ''"),
    ("quiz_attempts", "result_released", "BOOLEAN NOT NULL DEFAULT TRUE"),  # attempts made before this feature stay visible
    ("quiz_attempts", "released_at", _TS),
    # v7: pricing per course, the project the admin assigns, payment details, profile picture
    ("courses", "is_paid", "BOOLEAN NOT NULL DEFAULT TRUE"),   # existing courses keep charging for the certificate
    ("courses", "price_inr", "INTEGER"),
    ("courses", "project_title", "VARCHAR(160) NOT NULL DEFAULT ''"),
    ("courses", "project_description", "TEXT NOT NULL DEFAULT ''"),
    ("payments", "method", "VARCHAR(20) NOT NULL DEFAULT ''"),
    ("payments", "failure_reason", "VARCHAR(200) NOT NULL DEFAULT ''"),
    ("payments", "note", "VARCHAR(200) NOT NULL DEFAULT ''"),
    ("payments", "created_at", _TS),
    ("student_profiles", "avatar", _BLOB),
]


def add_missing_columns() -> None:
    insp = inspect(engine)
    for table, column, ddl in NEW_COLUMNS:
        if insp.has_table(table) and column not in {c["name"] for c in insp.get_columns(table)}:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)  # Alembic migrations come later
    add_missing_columns()
    with SessionLocal() as db:
        seed_content(db)  # idempotent: never overwrites existing courses
        seed_assessments(db)
        seed_projects(db)
    yield


app = FastAPI(title="Skill Learning API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"], allow_headers=["Content-Type", "Authorization", "X-Client"])
app.include_router(auth_router)
app.include_router(learning_router)
app.include_router(quiz_router)
app.include_router(me_router)
app.include_router(student_router)
app.include_router(certs_router)
app.include_router(admin_router)
app.include_router(admin_extra_router)
app.include_router(cert_router)
app.include_router(pay_router)
app.include_router(notify_router)
app.include_router(templates_router)


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        database = "connected"
    except Exception:
        database = "unavailable"
    return {"status": "ok", "database": database, "auth": "enabled",
            "code_execution": "not_connected"}


@app.get("/api/categories")
def categories():
    return {"items": CATEGORIES}


@app.get("/api/courses")
def courses(
    q: Optional[str] = Query(None, max_length=100),
    category: Optional[str] = Query(None, max_length=60),
    level: Optional[Literal["beginner", "intermediate", "advanced"]] = None,
    status: Optional[Literal["planned", "in_development", "available"]] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    db: Session = Depends(get_db),
):
    counts = lesson_counts(db)
    items = [{**c, "lesson_count": counts.get(c["slug"], 0),
              "status": "available" if counts.get(c["slug"]) else c["status"]} for c in COURSES]
    items += extra_courses(db, counts)
    prices = pricing_map(db)
    for it in items:
        if it["slug"] in prices:
            it.update(prices[it["slug"]])
    if q:
        needle = q.strip().lower()
        items = [c for c in items if needle in c["title"].lower()]
    if category:
        items = [c for c in items if c["category_id"] == category]
    if level:
        items = [c for c in items if c["level"] == level]
    if status:
        items = [c for c in items if c["status"] == status]
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "total": len(items),
            "page": page, "page_size": page_size}


@app.get("/api/projects")
def projects(db: Session = Depends(get_db)):
    rows = db.scalars(select(Project).where(Project.published.is_(True)).order_by(Project.id)).all()
    return {"items": [{"slug": p.slug, "title": p.title, "level": p.level, "summary": p.summary, "body_md": p.body_md,
                       "status": "available" if p.body_md.strip() else "planned"} for p in rows]}
