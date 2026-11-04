"""Admin: upload a certificate design, place the name / course / date on it, preview it with sample data, and switch it on.
Every certificate (download, email, sample on the course page) is drawn on the active design. With no active design the
built-in SkillForge Learning design is used."""
import base64
import io
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .certificate_image import DEFAULT_FIELDS, FONTS, clean_fields, default_template, render_certificate
from .db import get_db
from .deps import require_admin
from .models import CertificateTemplate, User
from .routes_admin import _iso, audit

router = APIRouter(prefix="/api/admin")
MAX_BYTES = 8_000_000


def _data_url(img: Image.Image, width: int = 1000) -> str:
    img = img.convert("RGB")
    img.thumbnail((width, width))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _row(t: CertificateTemplate) -> dict:
    return {"id": t.id, "name": t.name, "width": t.width, "height": t.height, "active": t.active, "created_at": _iso(t.created_at),
            "fields": clean_fields(t.fields)}


class UploadIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    image: str = Field(max_length=12_000_000)   # data URL, png or jpeg
    fields: Optional[dict] = None


def _decode(data_url: str):
    head, _, b64 = data_url.partition(",")
    if not head.startswith("data:image/") or "base64" not in head:
        raise HTTPException(status_code=422, detail="Upload a PNG or JPG image of the certificate design.")
    try:
        raw = base64.b64decode(b64, validate=False)
    except ValueError:
        raise HTTPException(status_code=422, detail="That file could not be read.")
    if len(raw) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="The image is larger than 8 MB. Export it smaller.")
    try:
        img = Image.open(io.BytesIO(raw))
        if img.format not in ("PNG", "JPEG"):
            raise HTTPException(status_code=422, detail="Upload a PNG or JPG image.")
        if img.width * img.height > 30_000_000 or img.width < 600 or img.height < 400:
            raise HTTPException(status_code=422, detail="The image must be at least 600 x 400 pixels and not huge (up to about 5000 x 5000).")
        return ImageOps.exif_transpose(img).convert("RGB")
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(status_code=422, detail="That file is not a valid image.")


@router.get("/certificate-templates")
def list_templates(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(CertificateTemplate).order_by(CertificateTemplate.id.desc())).all()
    builtin_active = not any(t.active for t in rows)
    return {"builtin": {"active": builtin_active, "fields": DEFAULT_FIELDS, "fonts": list(FONTS),
                        "image": _data_url(default_template(), 700)},
            "items": [_row(t) for t in rows], "fonts": list(FONTS)}


@router.get("/certificate-templates/{template_id}/image")
def template_image(template_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    t = db.get(CertificateTemplate, template_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Design not found")
    return {"image": _data_url(Image.open(io.BytesIO(t.image)), 1200)}


@router.post("/certificate-templates", status_code=201)
def upload_template(body: UploadIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    img = _decode(body.image)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    data, mime = buf.getvalue(), "image/png"
    if len(data) > 3_000_000:  # photos and gradients are far smaller as JPEG
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=92)
        data, mime = buf.getvalue(), "image/jpeg"
    t = CertificateTemplate(name=body.name.strip(), image=data, mime=mime, width=img.width, height=img.height,
                            fields=clean_fields(body.fields), active=False, created_by=admin.id)
    db.add(t)
    db.flush()
    audit(db, admin, "certificate_design.upload", t.name, f"{img.width}x{img.height}")
    db.commit()
    return _row(t)


class FieldsIn(BaseModel):
    fields: dict
    name: Optional[str] = Field(None, min_length=2, max_length=120)


@router.patch("/certificate-templates/{template_id}")
def save_fields(template_id: int, body: FieldsIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    t = db.get(CertificateTemplate, template_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Design not found")
    t.fields = clean_fields(body.fields)
    if body.name:
        t.name = body.name.strip()
    audit(db, admin, "certificate_design.edit", t.name)
    db.commit()
    return _row(t)


@router.post("/certificate-templates/{template_id}/activate")
def activate(template_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    t = db.get(CertificateTemplate, template_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Design not found")
    for o in db.scalars(select(CertificateTemplate).where(CertificateTemplate.active.is_(True))).all():
        o.active = False
    t.active = True
    audit(db, admin, "certificate_design.activate", t.name)
    db.commit()
    return _row(t)


@router.post("/certificate-templates/use-builtin")
def use_builtin(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    for o in db.scalars(select(CertificateTemplate).where(CertificateTemplate.active.is_(True))).all():
        o.active = False
    audit(db, admin, "certificate_design.activate", "built-in design")
    db.commit()
    return {"builtin": True}


@router.delete("/certificate-templates/{template_id}")
def delete_template(template_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    t = db.get(CertificateTemplate, template_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Design not found")
    if t.active:
        raise HTTPException(status_code=409, detail="This design is in use. Activate another design (or the built-in one) first.")
    audit(db, admin, "certificate_design.delete", t.name)
    db.delete(t)
    db.commit()
    return {"deleted": True}


class PreviewIn(BaseModel):
    template_id: Optional[int] = None     # None = the built-in design
    fields: Optional[dict] = None         # unsaved positions from the editor
    name: str = Field("Your Name Here", max_length=60)
    course: str = Field("Introduction to Python", max_length=90)


@router.post("/certificate-templates/preview")
def preview(body: PreviewIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    if body.template_id is None:
        base, saved = default_template(), DEFAULT_FIELDS
    else:
        t = db.get(CertificateTemplate, body.template_id)
        if t is None:
            raise HTTPException(status_code=404, detail="Design not found")
        base, saved = Image.open(io.BytesIO(t.image)).convert("RGB"), t.fields
    img = render_certificate(body.name or "Your Name Here", body.course or "Course name", date.today(), "SAMPLE-0000",
                             template=(base, body.fields if body.fields is not None else saved))
    return {"image": _data_url(img, 1100)}
