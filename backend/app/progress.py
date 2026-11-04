from sqlalchemy import func, select

from datetime import datetime, timezone

from .models import Course, Lesson, LessonProgress, Module, Quiz, QuizAttempt


def completion(db, user_id: str, course: Course) -> dict:
    """Completion rule: every published lesson done, and the final exam passed AND its result released by the admin."""
    lessons = [l for m in course.modules for l in m.lessons if l.published]
    ids = [l.id for l in lessons]
    done = db.scalar(select(func.count()).select_from(LessonProgress).where(
        LessonProgress.user_id == user_id, LessonProgress.lesson_id.in_(ids))) if ids else 0
    final_ids = db.scalars(select(Quiz.id).where(
        Quiz.course_id == course.id, Quiz.kind == "final", Quiz.published.is_(True))).all()
    final_passed = None
    if final_ids:
        final_passed = db.scalar(select(QuizAttempt.id).where(
            QuizAttempt.user_id == user_id, QuizAttempt.quiz_id.in_(final_ids), QuizAttempt.passed.is_(True),
            QuizAttempt.result_released.is_(True)).limit(1)) is not None
    total = len(lessons)
    return {"lessons_done": done, "lessons_total": total, "percent": round(100 * done / total) if total else 0,
            "final_passed": final_passed, "completed": total > 0 and done == total and final_passed in (None, True)}


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def final_exam_status(db, user_id: str, course: Course, rule: str = "attempted") -> dict:
    """The final exam stays locked until every published lesson is done and every published topic test has been
    attended (rule 'attempted') or passed (rule 'passed')."""
    lessons = [l for m in course.modules for l in m.lessons if l.published]
    done = set(db.scalars(select(LessonProgress.lesson_id).where(
        LessonProgress.user_id == user_id, LessonProgress.lesson_id.in_([l.id for l in lessons] or [0]))).all())
    missing_lessons = [l.title for l in lessons if l.id not in done]
    missing_tests = []
    for q in db.scalars(select(Quiz).where(Quiz.course_id == course.id, Quiz.kind == "chapter", Quiz.published.is_(True))).all():
        stmt = select(QuizAttempt.id).where(QuizAttempt.user_id == user_id, QuizAttempt.quiz_id == q.id,
                                            QuizAttempt.submitted_at.is_not(None))
        if rule == "passed":
            stmt = stmt.where(QuizAttempt.passed.is_(True))
        if db.scalar(stmt.limit(1)) is None:
            missing_tests.append(q.title)
    todo = [f"lesson: {t}" for t in missing_lessons[:3]] + [f"test: {t}" for t in missing_tests[:3]]
    more = len(missing_lessons) + len(missing_tests) - len(todo)
    msg = ("The final exam is locked. Still to do: " + "; ".join(todo) + (f" and {more} more" if more > 0 else "") + ".") if todo else ""
    return {"unlocked": not todo, "missing_lessons": missing_lessons, "missing_tests": missing_tests, "message": msg, "rule": rule}


def completed_on(db, user_id: str, course: Course) -> datetime:
    ids = [l.id for m in course.modules for l in m.lessons if l.published]
    stamps = []
    if ids:
        stamps.append(db.scalar(select(func.max(LessonProgress.completed_at)).where(
            LessonProgress.user_id == user_id, LessonProgress.lesson_id.in_(ids))))
    stamps.append(db.scalar(select(func.max(QuizAttempt.submitted_at)).join(Quiz, Quiz.id == QuizAttempt.quiz_id).where(
        QuizAttempt.user_id == user_id, QuizAttempt.passed.is_(True), Quiz.course_id == course.id, Quiz.kind == "final")))
    stamps = [_aware(s) for s in stamps if s]
    return max(stamps) if stamps else datetime.now(timezone.utc)


def final_result(db, user_id: str, course: Course) -> dict:
    """What the student may know about the final exam: nothing until the admin releases the result."""
    final_ids = db.scalars(select(Quiz.id).where(Quiz.course_id == course.id, Quiz.kind == "final", Quiz.published.is_(True))).all()
    if not final_ids:
        return {"state": "none"}
    att = db.scalar(select(QuizAttempt).where(QuizAttempt.user_id == user_id, QuizAttempt.quiz_id.in_(final_ids),
                                              QuizAttempt.submitted_at.is_not(None), QuizAttempt.score_pct.is_not(None))
                    .order_by(QuizAttempt.id.desc()).limit(1))
    if att is None:
        return {"state": "none"}
    if not att.result_released:
        return {"state": "pending", "attempt_id": att.id}
    return {"state": "released", "attempt_id": att.id, "score_pct": att.score_pct, "passed": bool(att.passed),
            "pass_mark": att.quiz.pass_mark}
