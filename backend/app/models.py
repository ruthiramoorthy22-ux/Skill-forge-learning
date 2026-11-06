import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(10), default="student")      # student | admin
    status: Mapped[str] = mapped_column(String(10), default="active")     # active | disabled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------- Phase 3: learning content
from sqlalchemy import JSON, Boolean, ForeignKey, Integer, Text, UniqueConstraint  # noqa: E402
from sqlalchemy.orm import relationship  # noqa: E402


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(120))
    category_id: Mapped[str] = mapped_column(String(60))
    level: Mapped[str] = mapped_column(String(12))
    summary: Mapped[str] = mapped_column(Text, default="")
    objectives: Mapped[list] = mapped_column(JSON, default=list)
    est_minutes: Mapped[int] = mapped_column(Integer, default=0)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="planned", nullable=False)
    # Pricing: is_paid False = free (the certificate needs no payment). price_inr None = use the default price from Settings.
    is_paid: Mapped[bool] = mapped_column(Boolean, default=True)
    price_inr: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # The project the admin assigns to every student of this course.
    project_title: Mapped[str] = mapped_column(String(160), default="")
    project_description: Mapped[str] = mapped_column(Text, default="")
    modules = relationship("Module", back_populates="course", order_by="Module.position", cascade="all, delete-orphan")


class Module(Base):
    __tablename__ = "modules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer)
    course = relationship("Course", back_populates="modules")
    lessons = relationship("Lesson", back_populates="module", order_by="Lesson.position", cascade="all, delete-orphan")


class Lesson(Base):
    __tablename__ = "lessons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id"), index=True)
    slug: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(160))
    position: Mapped[int] = mapped_column(Integer)
    body_md: Mapped[str] = mapped_column(Text, default="")
    example_code: Mapped[str] = mapped_column(Text, default="")
    example_lang: Mapped[str] = mapped_column(String(10), default="python")
    expected_output: Mapped[str] = mapped_column(Text, default="")
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    module = relationship("Module", back_populates="lessons")


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("user_id", "course_id", name="uq_enrollment"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_lesson_id: Mapped[Optional[int]] = mapped_column(ForeignKey("lessons.id"), nullable=True)
    course = relationship("Course")


class LessonProgress(Base):
    __tablename__ = "lesson_progress"
    __table_args__ = (UniqueConstraint("user_id", "lesson_id", name="uq_lesson_progress"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ---------------------------------------------------------------- Phases 4-10
class Quiz(Base):
    __tablename__ = "quizzes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(10), default="chapter")  # chapter | final
    pass_mark: Mapped[int] = mapped_column(Integer, default=70)
    time_limit_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    course = relationship("Course")
    questions = relationship("Question", back_populates="quiz", order_by="Question.position", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    qtype: Mapped[str] = mapped_column(String(10))  # single | multiple | short
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON, default=list)   # [{"id","text"}]
    answer: Mapped[list] = mapped_column(JSON, default=list)    # option ids, or accepted short answers (never sent before submit)
    explanation: Mapped[str] = mapped_column(Text, default="")
    quiz = relationship("Quiz", back_populates="questions")


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    score_pct: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    answers: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Final exam: the student does not see the result until the admin releases it.
    result_released: Mapped[bool] = mapped_column(Boolean, default=False)
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    quiz = relationship("Quiz")


class Challenge(Base):
    __tablename__ = "challenges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(160))
    language: Mapped[str] = mapped_column(String(10), default="python")
    difficulty: Mapped[str] = mapped_column(String(12), default="easy")
    topic: Mapped[str] = mapped_column(String(60), default="")
    statement_md: Mapped[str] = mapped_column(Text, default="")
    input_format: Mapped[str] = mapped_column(Text, default="")
    output_format: Mapped[str] = mapped_column(Text, default="")
    constraints: Mapped[str] = mapped_column(Text, default="")
    starter_code: Mapped[str] = mapped_column(Text, default="")
    hints: Mapped[list] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text, default="")
    tests: Mapped[list] = mapped_column(JSON, default=list)  # [{"stdin","expected","hidden"}]
    published: Mapped[bool] = mapped_column(Boolean, default=True)


class CodeSubmission(Base):
    __tablename__ = "code_submissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    challenge_id: Mapped[Optional[int]] = mapped_column(ForeignKey("challenges.id"), nullable=True, index=True)
    language: Mapped[str] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(Text)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(10))  # accepted | wrong | error
    results: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class XPEvent(Base):
    __tablename__ = "xp_events"
    __table_args__ = (UniqueConstraint("user_id", "kind", "ref", name="uq_xp_once"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    ref: Mapped[str] = mapped_column(String(60))
    points: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UserAchievement(Base):
    __tablename__ = "user_achievements"
    __table_args__ = (UniqueConstraint("user_id", "code", name="uq_user_achievement"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    ref: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class UserPresence(Base):
    __tablename__ = "user_presence"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_logout_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class UserSettings(Base):
    __tablename__ = "user_settings"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    show_on_leaderboard: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(40))
    target: Mapped[str] = mapped_column(String(120), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class Payment(Base):
    """One row per payment attempt (Razorpay order or direct UPI payment). Only status == verified unlocks anything."""
    __tablename__ = "payments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    course_id: Mapped[Optional[int]] = mapped_column(ForeignKey("courses.id"), nullable=True)
    purpose: Mapped[str] = mapped_column(String(20), default="certificate")
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    gateway: Mapped[str] = mapped_column(String(30))
    transaction_ref: Mapped[Optional[str]] = mapped_column(String(80), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending | verified | failed | refunded
    refund_status: Mapped[str] = mapped_column(String(12), default="none")
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Added with the Razorpay / UPI upgrade. status also uses "in_review" (a direct UPI payment waiting for the admin).
    method: Mapped[str] = mapped_column(String(20), default="")           # upi | card | netbanking | wallet (as reported by Razorpay)
    failure_reason: Mapped[str] = mapped_column(String(200), default="")
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=_now, nullable=True)


class Certificate(Base):
    """Prepared for the future. Issuance is disabled in code (see certificates.py)."""
    __tablename__ = "certificates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    status: Mapped[str] = mapped_column(String(10), default="valid")


# ---------------------------------------------------------------- certificates, payments, notifications (new tables only)
class AdminNotification(Base):
    __tablename__ = "admin_notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(Text)
    ref: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    emailed: Mapped[bool] = mapped_column(Boolean, default=False)


class CertificateDelivery(Base):
    __tablename__ = "certificate_deliveries"
    certificate_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    method: Mapped[str] = mapped_column(String(10))  # email | manual
    by_admin_id: Mapped[str] = mapped_column(String(36))


# ---------------------------------------------------------------- admin settings, certificate unlocks, projects
class AppSetting(Base):
    """Key/value settings the admin can change at runtime (certificate price, release mode)."""
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))


class CertificateGrant(Base):
    """An admin released ('unlocked') the certificate of a student for a course."""
    __tablename__ = "certificate_grants"
    __table_args__ = (UniqueConstraint("user_id", "course_id", name="uq_cert_grant"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    admin_id: Mapped[str] = mapped_column(String(36))
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(160))
    level: Mapped[str] = mapped_column(String(12), default="beginner")
    summary: Mapped[str] = mapped_column(Text, default="")
    body_md: Mapped[str] = mapped_column(Text, default="")
    published: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------- student profile and project submissions
class StudentProfile(Base):
    __tablename__ = "student_profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), default="")
    college_name: Mapped[str] = mapped_column(String(160), default="")
    school_name: Mapped[str] = mapped_column(String(160), default="")
    tenth_mark: Mapped[str] = mapped_column(String(12), default="")       # 10th mark / percentage
    twelfth_mark: Mapped[str] = mapped_column(String(12), default="")     # 12th mark / percentage
    degree: Mapped[str] = mapped_column(String(120), default="")          # degree / department / class
    year_of_study: Mapped[str] = mapped_column(String(30), default="")
    city: Mapped[str] = mapped_column(String(80), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    avatar: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)  # 256x256 JPEG, re-encoded by the server


class ProjectSubmission(Base):
    """Optional student project submission for practice and admin feedback."""
    __tablename__ = "project_submissions"
    __table_args__ = (UniqueConstraint("user_id", "course_id", name="uq_project_submission"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    repo_url: Mapped[str] = mapped_column(String(300), default="")
    demo_url: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(20), default="submitted")  # submitted | approved | changes_requested
    admin_feedback: Mapped[str] = mapped_column(Text, default="")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)


# ---------------------------------------------------------------- payments upgrade, student notifications, certificate designs
class PaymentWebhookEvent(Base):
    """Razorpay event ids already handled. A repeated delivery of the same event is ignored."""
    __tablename__ = "payment_webhook_events"
    event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    event: Mapped[str] = mapped_column(String(40), default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UserNotification(Base):
    """A message for one student (new course, new challenge, project approved, payment received, announcements)."""
    __tablename__ = "user_notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(140))
    message: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)


class CertificateTemplate(Base):
    """A certificate design uploaded by the admin. The active one is used for every certificate; none = built-in design."""
    __tablename__ = "certificate_templates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    image: Mapped[bytes] = mapped_column(LargeBinary)
    mime: Mapped[str] = mapped_column(String(20), default="image/png")
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    fields: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_by: Mapped[str] = mapped_column(String(36), default="")
