"""Payments: which methods are open, Razorpay failure reports, payment status and history, direct UPI payments, and the
admin's payment settings and UPI confirmation. Order creation, signature verification and the webhook are in routes_certs.py.
Nothing here unlocks a certificate except a payment that the server (or the admin) marked verified."""
import time
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import app_settings, certificates, payments
from .config import settings
from .db import get_db
from .deps import get_current_user, require_admin
from .models import AdminNotification, Course, Payment, User
from .notify import notify_user
from .progress import completion
from .routes_admin import _iso, audit
from .routes_certs import _enrolled_course

router = APIRouter(prefix="/api")


def methods_out(db: Session) -> dict:
    """What the pay screen may offer. A method appears only when the admin enabled it and it is usable."""
    rzp_on = app_settings.razorpay_enabled(db) and payments.configured()
    allowed = app_settings.razorpay_methods(db)
    return {
        "brand": settings.brand_name,
        "razorpay": {"enabled": rzp_on, "mode": settings.razorpay_mode, "key_id": settings.razorpay_key_id if rzp_on else "",
                     "methods": allowed, "hide": [m for m in app_settings.RZP_ALL_METHODS if m not in allowed]},
        "upi": {"enabled": app_settings.upi_enabled(db), "upi_id": app_settings.get_upi_id(db) if app_settings.upi_enabled(db) else "",
                "payee_name": app_settings.get_upi_name(db)},
    }


@router.get("/payments/methods")
def payment_methods(db: Session = Depends(get_db)):
    return methods_out(db)


def payment_out(db: Session, p: Payment) -> dict:
    course = db.get(Course, p.course_id) if p.course_id else None
    return {"id": p.id, "course": course.title if course else "", "course_slug": course.slug if course else "",
            "amount_inr": p.amount_minor / 100, "currency": p.currency, "status": p.status, "gateway": p.gateway,
            "method": p.method, "reference": p.transaction_ref, "failure_reason": p.failure_reason,
            "created_at": _iso(p.created_at) if p.created_at else None, "paid_at": _iso(p.paid_at) if p.paid_at else None}


@router.get("/me/payments")
def my_payments(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Payment history of the signed-in student. Orders that were opened and abandoned are hidden unless they failed."""
    rows = db.scalars(select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc().nullslast(), Payment.paid_at.desc().nullslast())).all()
    return {"items": [payment_out(db, p) for p in rows if p.status != "pending"]}


@router.get("/payments/{payment_id}")
def payment_status(payment_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.get(Payment, payment_id)
    if p is None or p.user_id != user.id:
        raise HTTPException(status_code=404, detail="Payment not found")
    out = payment_out(db, p)
    out["certificate_issued"] = bool(p.course_id and certificates.get_certificate(db, user.id, p.course_id))
    return out


class FailedIn(BaseModel):
    razorpay_order_id: str = Field(max_length=60)
    reason: str = Field("", max_length=200)


@router.post("/payments/razorpay/failed")
def razorpay_failed(body: FailedIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The checkout window reports a failed attempt. This only records the reason; it can never unlock anything, and a
    later verified payment for the same order still goes through."""
    p = db.get(Payment, body.razorpay_order_id)
    if p is None or p.user_id != user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    if p.status in ("pending", "failed"):
        p.status, p.failure_reason = "failed", (body.reason.strip() or "The payment failed.")[:200]
        db.commit()
    return payment_out(db, p)


# --------------------------------------------------------------------------- direct UPI (admin confirms)
@router.post("/courses/{slug}/certificate/upi-order")
def upi_order(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    course = _enrolled_course(db, user, slug)
    if not app_settings.upi_enabled(db):
        raise HTTPException(status_code=503, detail="Direct UPI payment is not available.")
    price = certificates.price_for(db, course)
    if price == 0:
        raise HTTPException(status_code=409, detail="This course is free. No payment is needed.")
    if not completion(db, user.id, course)["completed"]:
        raise HTTPException(status_code=403, detail="Finish every lesson and pass the final exam before paying for the certificate.")
    if certificates.has_verified_payment(db, user.id, course.id):
        raise HTTPException(status_code=409, detail="You have already paid for this certificate.")
    pay = db.scalar(select(Payment).where(Payment.user_id == user.id, Payment.course_id == course.id, Payment.gateway == "upi_manual",
                                          Payment.status == "pending", Payment.amount_minor == price * 100))
    if pay is None:  # reuse the open request so repeated taps do not pile up rows
        pay = Payment(id=str(uuid.uuid4()), user_id=user.id, course_id=course.id, purpose="certificate", amount_minor=price * 100,
                      currency="INR", gateway="upi_manual", method="upi", status="pending")
        db.add(pay)
        db.commit()
    vpa, payee = app_settings.get_upi_id(db), app_settings.get_upi_name(db)
    return {"payment_id": pay.id, "amount": price, "upi_id": vpa, "payee_name": payee,
            "uri": payments.upi_uri(vpa, payee, price, f"{settings.brand_name} certificate", pay.id.replace("-", "")),
            "course_title": course.title}


class UtrIn(BaseModel):
    utr: str = Field(pattern=r"^\d{12}$")  # the 12-digit UPI reference number shown in the payment app


@router.post("/payments/upi/{payment_id}/submit")
def upi_submit(payment_id: str, body: UtrIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.get(Payment, payment_id)
    if p is None or p.user_id != user.id or p.gateway != "upi_manual":
        raise HTTPException(status_code=404, detail="Payment not found")
    if p.status not in ("pending", "failed"):
        raise HTTPException(status_code=409, detail="This payment was already submitted.")
    ref = f"UTR:{body.utr}"
    if db.scalar(select(Payment.id).where(Payment.transaction_ref == ref, Payment.id != p.id)):
        raise HTTPException(status_code=409, detail="This UPI reference number was already used.")
    p.status, p.transaction_ref, p.failure_reason = "in_review", ref, ""
    course = db.get(Course, p.course_id)
    db.add(AdminNotification(kind="upi_review", ref=p.id, message=(
        f"{user.display_name} ({user.email}) says they paid Rs {p.amount_minor / 100:.2f} by UPI for the {course.title} certificate "
        f"(UTR {body.utr}). Check your bank or UPI app, then open Admin > Payments to confirm or reject it.")))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This UPI reference number was already used.")
    return payment_out(db, p)


class ReviewIn(BaseModel):
    reason: str = Field("", max_length=200)


@router.post("/admin/payments/{payment_id}/confirm")
def admin_confirm(payment_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = db.get(Payment, payment_id)
    if p is None or p.gateway != "upi_manual":
        raise HTTPException(status_code=404, detail="UPI payment not found")
    if p.status != "in_review":
        raise HTTPException(status_code=409, detail="Only a payment waiting for review can be confirmed.")
    certificates.finalize_payment(db, p, p.transaction_ref, "upi")
    audit(db, admin, "payment.confirm", p.id, p.transaction_ref or "")
    db.commit()
    return payment_out(db, p)


@router.post("/admin/payments/{payment_id}/reject")
def admin_reject(payment_id: str, body: ReviewIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = db.get(Payment, payment_id)
    if p is None or p.gateway != "upi_manual":
        raise HTTPException(status_code=404, detail="UPI payment not found")
    if p.status != "in_review":
        raise HTTPException(status_code=409, detail="Only a payment waiting for review can be rejected.")
    p.status, p.failure_reason = "failed", (body.reason.strip() or "The admin could not find this payment.")[:200]
    p.transaction_ref = None  # the UTR is free again, the student may submit the right one
    notify_user(db, p.user_id, "payment", "UPI payment not confirmed", p.failure_reason + " Open the pay screen and try again.",
                f"/courses/{db.get(Course, p.course_id).slug}/pay")
    audit(db, admin, "payment.reject", p.id, p.failure_reason)
    db.commit()
    return payment_out(db, p)


# --------------------------------------------------------------------------- admin: payment settings
class PaymentSettingsIn(BaseModel):
    razorpay_enabled: Optional[bool] = None
    upi_enabled: Optional[bool] = None
    upi_id: Optional[str] = Field(None, max_length=80)
    upi_payee_name: Optional[str] = Field(None, max_length=80)
    razorpay_methods: Optional[List[str]] = None


def _settings_out(db: Session) -> dict:
    return {"razorpay_enabled": app_settings.razorpay_enabled(db), "razorpay_configured": payments.configured(),
            "razorpay_mode": settings.razorpay_mode, "razorpay_methods": app_settings.razorpay_methods(db),
            "webhook_configured": bool(settings.razorpay_webhook_secret),
            "upi_enabled": app_settings.upi_enabled(db), "upi_id": app_settings.get_upi_id(db),
            "upi_payee_name": app_settings.get_upi_name(db), "brand": settings.brand_name}


@router.get("/admin/payment-settings")
def get_payment_settings(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _settings_out(db)


@router.patch("/admin/payment-settings")
def patch_payment_settings(body: PaymentSettingsIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if body.upi_id is not None and body.upi_id.strip() and not app_settings.UPI_RE.match(body.upi_id.strip()):
        raise HTTPException(status_code=422, detail="Enter a valid UPI id, for example name@okhdfcbank.")
    if body.razorpay_methods is not None:
        if any(m not in app_settings.RZP_ALL_METHODS for m in body.razorpay_methods) or not body.razorpay_methods:
            raise HTTPException(status_code=422, detail="Choose at least one of: upi, card, netbanking, wallet.")
    new_upi_id = body.upi_id.strip() if body.upi_id is not None else app_settings.get_upi_id(db)
    rzp = body.razorpay_enabled if body.razorpay_enabled is not None else app_settings.razorpay_enabled(db)
    upi_on = body.upi_enabled if body.upi_enabled is not None else app_settings._get(db, app_settings.UPI_ENABLED_KEY) == "1"
    if upi_on and not new_upi_id:
        raise HTTPException(status_code=422, detail="Enter your UPI id before turning on direct UPI payment.")
    if not rzp and not upi_on:
        raise HTTPException(status_code=422, detail="Keep at least one payment method on.")
    app_settings.set_payment_settings(db, razorpay_enabled=body.razorpay_enabled, upi_enabled=body.upi_enabled, upi_id=body.upi_id,
                                      upi_payee_name=body.upi_payee_name, razorpay_methods=body.razorpay_methods)
    audit(db, admin, "settings.payment_methods", "payments", f"razorpay={rzp} upi={upi_on}")
    db.commit()
    return _settings_out(db)
