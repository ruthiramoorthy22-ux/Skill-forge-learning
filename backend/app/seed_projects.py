"""Starter project list (from the original catalog). Idempotent: existing rows are never overwritten, so admin edits stay."""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .catalog import PROJECTS
from .models import Project


def seed_projects(db: Session) -> None:
    if db.scalar(select(Project.id).limit(1)) is not None:
        return  # the admin owns the list from now on (including deleting items)
    for title in PROJECTS:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        db.add(Project(slug=slug, title=title, level="beginner", summary="Guided project. Steps are added by the admin.", body_md=""))
    db.commit()
