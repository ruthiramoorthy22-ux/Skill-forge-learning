"""Certificates: locked until the course is completed (all lessons + final exam passed) AND the payment is verified."""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

import io

from PIL import Image

from . import app_settings, mailer
from .certificate_image import render_certificate
from .config import settings
from .models import (AdminNotification, Certificate, CertificateGrant, CertificateTemplate, Course, Payment, ProjectSubmission,
                     User)
from .notify import notify_user
from .progress import completed_on, completion

log = logging.getLogger("skillforge")


class DuplicateTransaction(Exception):
    pass


def get_certificate(db: Session, user_id: str, course_id: int) -> Optional[Certificate]:
    return db.scalar(select(Certificate).where(Certificate.user_id == user_id, Certificate.course_id == course_id))


def has_verified_payment(db: Session, user_id: str, course_id: int) -> bool:
    return db.scalar(select(Payment.id).where(Payment.user_id == user_id, Payment.course_id == course_id,
                                              Payment.purpose == "certificate", Payment.status == "verified").limit(1)) is not None


def price_for(db: Session, course: Course) -> int:
    """Rupees the student pays for this course's certificate. 0 means the course is free."""
    if not course.is_paid:
        return 0
    return course.price_inr or app_settings.get_price(db)


def payment_ok(db: Session, user_id: str, course: Course) -> bool:
    """True when the certificate needs no payment (free course) or the payment was verified."""
    return price_for(db, course) == 0 or has_verified_payment(db, user_id, course.id)


def active_template(db: Session):
    """(image, fields) of the design the admin activated, or None for the built-in design."""
    t = db.scalar(select(CertificateTemplate).where(CertificateTemplate.active.is_(True)).order_by(CertificateTemplate.id.desc()).limit(1))
    if t is None:
        return None
    return Image.open(io.BytesIO(t.image)).convert("RGB"), t.fields


def get_submission(db: Session, user_id: str, course_id: int) -> Optional[ProjectSubmission]:
    return db.scalar(select(ProjectSubmission).where(ProjectSubmission.user_id == user_id, ProjectSubmission.course_id == course_id))


def project_ok(db: Session, user_id: str, course_id: int) -> bool:
    """True when no project is required, or the admin approved the student's project."""
    if not app_settings.get_project_required(db):
        return True
    sub = get_submission(db, user_id, course_id)
    return sub is not None and sub.status == "approved"


def has_grant(db: Session, user_id: str, course_id: int) -> bool:
    return db.scalar(select(CertificateGrant.id).where(CertificateGrant.user_id == user_id,
                                                       CertificateGrant.course_id == course_id).limit(1)) is not None


def issue_if_eligible(db: Session, user_id: str, course: Course) -> Optional[Certificate]:
    """Needs a completed course AND (an admin unlock OR a verified payment while the release mode is 'auto')."""
    cert = get_certificate(db, user_id, course.id)
    if cert:
        return cert
    released = has_grant(db, user_id, course.id) or (
        app_settings.get_release_mode(db) == "auto" and payment_ok(db, user_id, course))
    if not released or not completion(db, user_id, course)["completed"] or not project_ok(db, user_id, course.id):
        return None
    cert = Certificate(user_id=user_id, course_id=course.id)
    db.add(cert)
    db.flush()
    notify_user(db, user_id, "certificate", "Your certificate is ready", f"Your {course.title} certificate can be downloaded now.", "/certificates")
    return cert


def finalize_payment(db: Session, payment: Payment, payment_id: str, method: str = "") -> Optional[Certificate]:
    """Idempotent. Marks the payment verified once, notifies the admin once, and issues the certificate when eligible."""
    note = None
    if payment.status != "verified":
        if db.scalar(select(Payment.id).where(Payment.transaction_ref == payment_id, Payment.id != payment.id)):
            raise DuplicateTransaction()
        payment.status, payment.transaction_ref, payment.paid_at = "verified", payment_id, datetime.now(timezone.utc)
        payment.failure_reason = ""
        if method:
            payment.method = method[:20]
        user, course = db.get(User, payment.user_id), db.get(Course, payment.course_id)
        notify_user(db, user.id, "payment", "Payment received", f"Rs {payment.amount_minor / 100:.2f} paid for the {course.title} certificate. Thank you!", "/payments")
        note = AdminNotification(kind="certificate_paid", ref=payment.id, message=(
            f"{user.display_name} ({user.email}) paid Rs {payment.amount_minor / 100:.2f} for the {course.title} certificate. "
            f"Open Admin > Certificates to unlock it or send it by email."))
        db.add(note)
        db.flush()  # the eligibility check below must see the verified payment
    cert = issue_if_eligible(db, payment.user_id, db.get(Course, payment.course_id))
    db.commit()
    if note is not None:
        try:
            mailer.send_mail(settings.admin_email, "SkillForge Learning: certificate payment received", note.message)
            note.emailed = True
            db.commit()
        except mailer.MailUnavailable:
            log.info("Admin email not sent (email not configured or failed); dashboard notification was created.")
    return cert


def render_for(db: Session, cert: Certificate):
    user, course = db.get(User, cert.user_id), db.get(Course, cert.course_id)
    img = render_certificate(user.display_name, course.title, completed_on(db, user.id, course).date(), cert.id,
                             template=active_template(db))
    return img, f"SkillForge-{course.slug}-certificate"
