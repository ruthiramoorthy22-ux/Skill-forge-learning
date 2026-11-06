import io
import json
import time
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import app_settings, certificates, payments
from .certificate_image import render_certificate, to_pdf, to_png
from .config import settings
from .db import get_db
from .deps import get_current_user
from .security import check_link_token, create_link_token
from .models import Certificate, Course, Enrollment, Payment, PaymentWebhookEvent, User
from .notify import notify_user
from .progress import completion, final_result
from .routes_learning import _require_course

router = APIRouter(prefix="/api")


def _enrolled_course(db: Session, user: User, slug: str) -> Course:
    course = _require_course(db, slug)
    if db.scalar(select(Enrollment.id).where(Enrollment.user_id == user.id, Enrollment.course_id == course.id)) is None:
        raise HTTPException(status_code=403, detail="Enroll in this course first.")
    return course


@router.get("/courses/{slug}/certificate")
def certificate_status(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    course = _enrolled_course(db, user, slug)
    completed = completion(db, user.id, course)["completed"]
    cert = certificates.issue_if_eligible(db, user.id, course)  # covers "paid first, finished later"
    db.commit()
    paid = certificates.has_verified_payment(db, user.id, course.id)
    price = certificates.price_for(db, course)
    sub = certificates.get_submission(db, user.id, course.id)
    project_approved = sub is not None and sub.status == "approved"
    awaiting_admin = bool(cert is None and completed and certificates.payment_ok(db, user.id, course) and app_settings.get_release_mode(db) == "admin")
    reason = None
    if cert is None:
        if not completed:
            reason = "Locked. Finish every lesson and the final exam, then wait for the admin to release your result."
        elif awaiting_admin:
            reason = "Payment received. The admin will unlock your certificate shortly."
        else:
            reason = "Locked. Pay the certificate fee to receive it." if price else "Your certificate is being prepared."
    from .routes_pay import methods_out
    m = methods_out(db)
    return {"price_inr": price, "is_free": price == 0, "can_pay": m["razorpay"]["enabled"] or m["upi"]["enabled"],
            "payments_configured": payments.configured(),
            "course_completed": completed, "paid": paid, "awaiting_admin": awaiting_admin,
            "project_required": False, "project_approved": project_approved,
            "project_status": sub.status if sub else None, "issued": cert is not None,
            "certificate_id": cert.id if cert else None, "locked_reason": reason,
            "final_result": final_result(db, user.id, course)}


@router.get("/pricing")
def pricing(db: Session = Depends(get_db)):
    """One certificate price for every course."""
    return {"certificate_price_inr": app_settings.get_price(db)}


@router.get("/courses/{slug}/certificate/preview")
def certificate_preview(slug: str, db: Session = Depends(get_db)):
    """A sample certificate (placeholder name) shown locked on the course page. Contains no student data."""
    course = _require_course(db, slug)
    img = render_certificate("Your Name Here", course.title, date.today(), "SAMPLE", template=certificates.active_template(db))
    img.thumbnail((900, 900))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=80)
    return Response(buf.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "public, max-age=300"})


@router.post("/courses/{slug}/certificate/order")
def certificate_order(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    course = _enrolled_course(db, user, slug)
    price = certificates.price_for(db, course)
    if price == 0:
        raise HTTPException(status_code=409, detail="This course is free. No payment is needed.")
    if not completion(db, user.id, course)["completed"]:
        raise HTTPException(status_code=403, detail="Finish every lesson and pass the final exam before paying for the certificate.")
    if certificates.has_verified_payment(db, user.id, course.id):
        raise HTTPException(status_code=409, detail="You have already paid for this certificate.")
    if not app_settings.razorpay_enabled(db):
        raise HTTPException(status_code=503, detail="Online payment by Razorpay is turned off. Use another payment method.")
    amount = price * 100  # the amount comes from the server, never from the browser
    try:
        order = payments.create_order(amount, f"cert-{user.id[:8]}-{course.id}-{int(time.time())}",
                                      {"user_id": user.id, "course": course.slug})
    except payments.PaymentsUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    db.add(Payment(id=order["id"], user_id=user.id, course_id=course.id, purpose="certificate", amount_minor=amount,
                   currency="INR", gateway="razorpay", status="pending"))
    db.commit()
    return {"order_id": order["id"], "amount": amount, "currency": "INR", "key_id": settings.razorpay_key_id,
            "course_title": course.title, "student_name": user.display_name, "student_email": user.email,
            "brand": settings.brand_name}


class VerifyIn(BaseModel):
    razorpay_order_id: str = Field(max_length=60)
    razorpay_payment_id: str = Field(max_length=60)
    razorpay_signature: str = Field(max_length=200)


@router.post("/payments/razorpay/verify")
def verify_payment(body: VerifyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payment = db.get(Payment, body.razorpay_order_id)
    if payment is None or payment.user_id != user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    if not payments.verify_signature(body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature):
        raise HTTPException(status_code=400, detail="Payment verification failed. No certificate was issued.")
    method = ""
    if payment.status != "verified":
        try:  # the signature proves Razorpay issued this payment id; this proves the money was really captured
            method = payments.ensure_captured(payment.id, body.razorpay_payment_id, payment.amount_minor).get("method", "")
        except payments.PaymentsUnavailable as e:
            raise HTTPException(status_code=502, detail=f"{e} If money was deducted, it will be confirmed automatically. Check Payment history in a minute.")
    try:
        cert = certificates.finalize_payment(db, payment, body.razorpay_payment_id, method)
    except certificates.DuplicateTransaction:
        raise HTTPException(status_code=409, detail="This payment was already used.")
    return {"paid": True, "payment_id": payment.id, "issued": cert is not None, "certificate_id": cert.id if cert else None}


@router.post("/payments/razorpay/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    if not settings.razorpay_webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook secret is not configured.")
    if not payments.verify_webhook(body, request.headers.get("x-razorpay-signature", "")):
        raise HTTPException(status_code=400, detail="Invalid signature.")
    try:
        event = json.loads(body)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid body.")
    name = event.get("event") or ""
    event_id = request.headers.get("x-razorpay-event-id", "").strip()
    if event_id and db.get(PaymentWebhookEvent, event_id) is not None:
        return {"ok": True, "duplicate": True}  # Razorpay retries deliveries; the same event is handled once
    entity = ((event.get("payload") or {}).get("payment") or {}).get("entity") or {}
    order_id, payment_id = entity.get("order_id"), entity.get("id")
    payment = db.get(Payment, order_id) if order_id else None
    if payment is not None and payment_id:
        if name in ("payment.captured", "order.paid"):
            if entity.get("amount") == payment.amount_minor and entity.get("status", "captured") == "captured":
                try:
                    certificates.finalize_payment(db, payment, payment_id, entity.get("method") or "")
                except certificates.DuplicateTransaction:
                    pass
        elif name == "payment.failed" and payment.status in ("pending", "failed"):
            payment.status = "failed"
            payment.failure_reason = (entity.get("error_description") or "The payment failed.")[:200]
            db.commit()
    if event_id:
        db.add(PaymentWebhookEvent(event_id=event_id, event=name[:40]))
        try:
            db.commit()
        except IntegrityError:  # two deliveries at the same moment: the work above is idempotent, so just carry on
            db.rollback()
    return {"ok": True}


@router.get("/me/certificates")
def my_certificates(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Certificate).where(Certificate.user_id == user.id).order_by(Certificate.issued_at.desc())).all()
    out = []
    for c in rows:
        course = db.get(Course, c.course_id)
        out.append({"id": c.id, "course": course.title, "course_slug": course.slug})
    return {"items": out}


def _own_or_admin(db: Session, user: User, certificate_id: str) -> Certificate:
    cert = db.get(Certificate, certificate_id)
    if cert is None or (cert.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=404, detail="Certificate not found")  # the same answer for "not yours" and "does not exist"
    return cert


@router.post("/certificates/{certificate_id}/link")
def certificate_link(certificate_id: str, format: Literal["png", "pdf"] = Query("pdf"),
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _own_or_admin(db, user, certificate_id)
    return {"url": f"/api/certificates/{certificate_id}/download?format={format}&t={create_link_token(certificate_id)}"}


@router.get("/certificates/{certificate_id}/download")
def download_certificate(certificate_id: str, request: Request, format: Literal["png", "pdf"] = Query("pdf"),
                         t: Optional[str] = Query(None, max_length=600), db: Session = Depends(get_db)):
    if t is not None:
        cert = db.get(Certificate, certificate_id)
        if cert is None or not check_link_token(t, certificate_id):
            raise HTTPException(status_code=403, detail="This download link is invalid or has expired.")
    else:
        cert = _own_or_admin(db, get_current_user(request, db), certificate_id)
    img, base = certificates.render_for(db, cert)
    if format == "png":
        return Response(to_png(img), media_type="image/png", headers={"Content-Disposition": f'attachment; filename="{base}.png"'})
    return Response(to_pdf(img), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{base}.pdf"'})
