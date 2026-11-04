import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import executor
from .db import get_db
from .deps import get_current_user
from .gamification import after_learning_event, grant_xp, record_activity
from .config import settings
from .progress import final_exam_status, final_result
from .models import AdminNotification, Challenge, CodeSubmission, Course, Enrollment, Question, Quiz, QuizAttempt, User
from .ratelimit import Limiter

router = APIRouter(prefix="/api")
run_limiter = Limiter(20, 60)
submit_limiter = Limiter(15, 60)
GRACE_SECONDS = 30


def _now():
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


# ------------------------------------------------------------------ quizzes
def _quiz(db: Session, user: User, quiz_id: int) -> Quiz:
    quiz = db.get(Quiz, quiz_id)
    if quiz is None or not quiz.published or not quiz.course.published or not quiz.questions:
        raise HTTPException(status_code=404, detail="Quiz not found")
    if db.scalar(select(Enrollment.id).where(Enrollment.user_id == user.id, Enrollment.course_id == quiz.course_id)) is None:
        raise HTTPException(status_code=403, detail="Enroll in this course to take its quizzes.")
    if quiz.kind == "final":
        st = final_exam_status(db, user.id, quiz.course, settings.final_unlock_rule)
        if not st["unlocked"]:
            raise HTTPException(status_code=403, detail=st["message"])
    return quiz


def _expired(quiz: Quiz, attempt: QuizAttempt) -> bool:
    if not quiz.time_limit_minutes:
        return False
    return _now() > _aware(attempt.started_at) + timedelta(minutes=quiz.time_limit_minutes, seconds=GRACE_SECONDS)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def grade_question(q: Question, given: List[str]) -> bool:
    if q.qtype == "short":
        return bool(given) and _norm(given[0]) in {_norm(a) for a in q.answer}
    return set(given) == set(q.answer) and len(given) == len(set(given))


@router.get("/courses/{slug}/quizzes")
def course_quizzes(slug: str, db: Session = Depends(get_db)):
    course = db.scalar(select(Course).where(Course.slug == slug, Course.published.is_(True)))
    items = []
    for q in (db.scalars(select(Quiz).where(Quiz.course_id == course.id, Quiz.published.is_(True))).all() if course else []):
        items.append({"id": q.id, "title": q.title, "kind": q.kind, "pass_mark": q.pass_mark,
                      "time_limit_minutes": q.time_limit_minutes, "question_count": len(q.questions)})
    return {"items": items}


@router.get("/courses/{slug}/exam-status")
def exam_status(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    course = db.scalar(select(Course).where(Course.slug == slug, Course.published.is_(True)))
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if db.scalar(select(Enrollment.id).where(Enrollment.user_id == user.id, Enrollment.course_id == course.id)) is None:
        raise HTTPException(status_code=403, detail="Enroll in this course first.")
    return final_exam_status(db, user.id, course, settings.final_unlock_rule)


@router.get("/courses/{slug}/final-result")
def course_final_result(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    course = db.scalar(select(Course).where(Course.slug == slug, Course.published.is_(True)))
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if db.scalar(select(Enrollment.id).where(Enrollment.user_id == user.id, Enrollment.course_id == course.id)) is None:
        raise HTTPException(status_code=403, detail="Enroll in this course first.")
    return final_result(db, user.id, course)


@router.post("/quizzes/{quiz_id}/start")
def start_quiz(quiz_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    quiz = _quiz(db, user, quiz_id)
    if quiz.kind == "final" and final_result(db, user.id, quiz.course).get("state") == "pending":
        raise HTTPException(status_code=409, detail="Your final exam is with the admin. You will see the result once it is released.")
    attempt = db.scalar(select(QuizAttempt).where(QuizAttempt.user_id == user.id, QuizAttempt.quiz_id == quiz.id,
                                                  QuizAttempt.submitted_at.is_(None)).order_by(QuizAttempt.id.desc()))
    if attempt is None or _expired(quiz, attempt):
        attempt = QuizAttempt(user_id=user.id, quiz_id=quiz.id)
        db.add(attempt)
        db.commit()
    # Answer keys are never included here.
    return {"attempt_id": attempt.id, "started_at": _aware(attempt.started_at).isoformat(), "title": quiz.title, "kind": quiz.kind,
            "pass_mark": quiz.pass_mark, "time_limit_minutes": quiz.time_limit_minutes,
            "questions": [{"id": q.id, "qtype": q.qtype, "prompt": q.prompt, "options": q.options} for q in quiz.questions]}


class SubmitIn(BaseModel):
    attempt_id: int
    answers: Dict[str, List[str]] = Field(default_factory=dict)


@router.post("/quizzes/{quiz_id}/submit")
def submit_quiz(quiz_id: int, body: SubmitIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    quiz = _quiz(db, user, quiz_id)
    attempt = db.get(QuizAttempt, body.attempt_id)
    if attempt is None or attempt.user_id != user.id or attempt.quiz_id != quiz.id:
        raise HTTPException(status_code=404, detail="Attempt not found")
    if attempt.submitted_at is not None:
        raise HTTPException(status_code=409, detail="This attempt was already submitted.")
    attempt.submitted_at = _now()
    if _expired(quiz, attempt):
        attempt.score_pct, attempt.passed, attempt.answers = 0, False, {}
        db.commit()
        raise HTTPException(status_code=409, detail="The time limit for this attempt has passed. Start a new attempt.")
    results, correct = [], 0
    for q in quiz.questions:
        given = [str(a)[:200] for a in body.answers.get(str(q.id), [])][:8]
        ok = grade_question(q, given)
        correct += ok
        results.append({"question_id": q.id, "correct": ok, "your_answer": given, "correct_answer": q.answer,
                        "explanation": q.explanation})
    pct = round(100 * correct / len(quiz.questions))
    attempt.score_pct, attempt.passed, attempt.answers = pct, pct >= quiz.pass_mark, body.answers
    record_activity(db, user.id, "practice_submit" if quiz.kind == "practice" else "quiz_submit", quiz.id)
    if quiz.kind == "final":
        # The student never sees marks or answers for the final exam. The admin is told and releases the result.
        attempt.result_released = False
        db.add(AdminNotification(kind="final_exam_submitted", ref=str(attempt.id), message=(
            f"{user.display_name} ({user.email}) finished the final exam for {quiz.course.title}: {pct}% "
            f"({'passed' if attempt.passed else 'not passed'}). Open Admin > Final results to release the result to the student.")))
        db.commit()
        return {"pending_review": True, "kind": "final", "course_slug": quiz.course.slug,
                "message": "Your final exam was submitted. The admin will review it and release your result."}
    if attempt.passed and quiz.kind != "practice":  # practice never earns XP and never affects completion
        grant_xp(db, user.id, "quiz_pass", quiz.id)
    new = after_learning_event(db, user)
    db.commit()
    return {"score_pct": pct, "passed": attempt.passed, "pass_mark": quiz.pass_mark, "correct_count": correct,
            "total": len(quiz.questions), "results": results, "new_achievements": new}


@router.get("/quizzes/{quiz_id}/attempts")
def quiz_attempts(quiz_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    quiz = _quiz(db, user, quiz_id)
    rows = db.scalars(select(QuizAttempt).where(QuizAttempt.user_id == user.id, QuizAttempt.quiz_id == quiz.id,
                                                QuizAttempt.submitted_at.is_not(None)).order_by(QuizAttempt.id.desc())).all()
    show = lambda a: quiz.kind != "final" or a.result_released  # noqa: E731
    return {"items": [{"id": a.id, "submitted_at": _aware(a.submitted_at).isoformat(),
                       "score_pct": a.score_pct if show(a) else None, "passed": a.passed if show(a) else None,
                       "result_released": show(a)} for a in rows]}


# ------------------------------------------------------------------ code runner and challenges
Language = Literal["python", "java", "c", "cpp"]


class RunIn(BaseModel):
    language: Language
    source: str = Field(max_length=executor.MAX_SOURCE)
    stdin: str = Field("", max_length=executor.MAX_STDIN)


def _run(language: str, source: str, stdin: str) -> dict:
    try:
        return executor.execute(language, source, stdin)
    except executor.ExecutionUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/code/run")
def run_code(body: RunIn, user: User = Depends(get_current_user)):
    run_limiter.check(user.id)
    return _run(body.language, body.source, body.stdin)


def _public_challenge(c: Challenge) -> dict:
    return {"slug": c.slug, "title": c.title, "language": c.language, "difficulty": c.difficulty, "topic": c.topic}


@router.get("/challenges")
def list_challenges(topic: Optional[str] = None, difficulty: Optional[str] = None, db: Session = Depends(get_db)):
    q = select(Challenge).where(Challenge.published.is_(True)).order_by(Challenge.id)
    if topic:
        q = q.where(Challenge.topic == topic)
    if difficulty:
        q = q.where(Challenge.difficulty == difficulty)
    return {"items": [_public_challenge(c) for c in db.scalars(q).all()]}


@router.get("/challenges/{slug}")
def get_challenge(slug: str, db: Session = Depends(get_db)):
    c = db.scalar(select(Challenge).where(Challenge.slug == slug, Challenge.published.is_(True)))
    if c is None:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return {**_public_challenge(c), "statement_md": c.statement_md, "input_format": c.input_format,
            "output_format": c.output_format, "constraints": c.constraints, "starter_code": c.starter_code, "hints": c.hints,
            "examples": [{"input": t["stdin"], "output": t["expected"]} for t in c.tests if not t.get("hidden")],
            "hidden_test_count": sum(1 for t in c.tests if t.get("hidden"))}


def _same(actual: str, expected: str) -> bool:
    clean = lambda s: "\n".join(line.rstrip() for line in s.replace("\r\n", "\n").strip().split("\n"))
    return clean(actual) == clean(expected)


@router.post("/challenges/{slug}/submit")
def submit_challenge(slug: str, body: RunIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.scalar(select(Challenge).where(Challenge.slug == slug, Challenge.published.is_(True)))
    if c is None:
        raise HTTPException(status_code=404, detail="Challenge not found")
    if body.language != c.language:
        raise HTTPException(status_code=422, detail=f"This challenge uses {c.language}.")
    submit_limiter.check(user.id)
    results, passed, errored = [], 0, False
    for i, t in enumerate(c.tests, 1):
        out = _run(body.language, body.source, t["stdin"])
        ran_ok = out["status_id"] == 3
        ok = ran_ok and _same(out["stdout"], t["expected"])
        passed += ok
        errored = errored or not ran_ok
        row = {"test": i, "hidden": bool(t.get("hidden")), "passed": ok, "status": out["status"]}
        if not t.get("hidden"):  # hidden test data and output are never returned
            row.update(input=t["stdin"], expected=t["expected"], actual=out["stdout"],
                       error=(out["compile_output"] or out["stderr"])[:2000])
        results.append(row)
    status = "accepted" if passed == len(c.tests) else "error" if errored and passed == 0 else "wrong"
    db.add(CodeSubmission(user_id=user.id, challenge_id=c.id, language=body.language, source=body.source,
                          passed=passed, total=len(c.tests), status=status, results=results))
    record_activity(db, user.id, "challenge_submit", c.slug)
    if status == "accepted":
        grant_xp(db, user.id, "challenge", c.id)
    new = after_learning_event(db, user)
    db.commit()
    return {"status": status, "passed": passed, "total": len(c.tests), "results": results, "new_achievements": new}


@router.get("/challenges/{slug}/submissions")
def challenge_submissions(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.scalar(select(Challenge).where(Challenge.slug == slug))
    if c is None:
        raise HTTPException(status_code=404, detail="Challenge not found")
    rows = db.scalars(select(CodeSubmission).where(CodeSubmission.user_id == user.id, CodeSubmission.challenge_id == c.id)
                      .order_by(CodeSubmission.id.desc()).limit(50)).all()
    return {"items": [{"id": s.id, "status": s.status, "passed": s.passed, "total": s.total,
                       "created_at": _aware(s.created_at).isoformat()} for s in rows]}
