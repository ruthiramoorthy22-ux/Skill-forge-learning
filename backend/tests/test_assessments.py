import pytest

from app import executor
from app.config import settings
from app.db import SessionLocal
from app.models import QuizAttempt, XPEvent
from app.seed_assessments import CHALLENGES
from helpers import admin, fake_execute, finish_lessons, quiz_id, seed_all, student, take, unlock_final

HTML_RIGHT = {"1": ["b"], "2": ["c"], "3": ["a", "b", "c"]}


def html_answers(c, right=True):
    finish_lessons(c, "html5")
    qid = quiz_id(c, "html5", "final")
    qs = c.post(f"/api/quizzes/{qid}/start").json()["questions"]
    keys = [q["id"] for q in qs]
    good = {str(keys[0]): ["b"], str(keys[1]): ["c"], str(keys[2]): ["a", "b", "c"]}
    return qid, (good if right else {str(k): ["d"] for k in keys})


def test_quiz_list_public_start_needs_enrollment_and_hides_answers():
    seed_all()
    c = student()
    assert c.get("/api/courses/html5/quizzes").json()["items"][0]["question_count"] == 3
    qid = quiz_id(c, "html5", "final")
    assert c.post(f"/api/quizzes/{qid}/start").status_code == 403
    c.post("/api/courses/html5/enroll")
    assert c.post(f"/api/quizzes/{qid}/start").status_code == 403   # enrolled, but the final exam is still locked
    finish_lessons(c, "html5")
    start = c.post(f"/api/quizzes/{qid}/start").json()
    assert "answer" not in str(start) and "explanation" not in str(start)


def _release(attempt_id):
    a = admin()
    assert a.post(f"/api/admin/final-results/{attempt_id}/release").status_code == 200
    return a


def test_final_exam_result_is_hidden_until_the_admin_releases_it():
    seed_all()
    c = student(enroll="html5")
    qid, good = html_answers(c)
    r, start = take(c, qid, good)
    body = r.json()
    assert body["pending_review"] is True and "score_pct" not in body and "results" not in body and "passed" not in body
    assert c.get("/api/courses/html5/final-result").json()["state"] == "pending"
    att = c.get(f"/api/quizzes/{qid}/attempts").json()["items"][0]
    assert att["score_pct"] is None and att["passed"] is None and att["result_released"] is False
    assert c.post(f"/api/quizzes/{qid}/start").status_code == 409            # no second attempt while the admin reviews
    assert c.get("/api/courses/html5/progress").json()["course_completed"] is False
    a = admin()
    row = next(i for i in a.get("/api/admin/final-results?released=false").json()["items"] if i["attempt_id"] == start["attempt_id"])
    assert row["score_pct"] == 100 and row["passed"] is True and row["released"] is False
    assert any(n["kind"] == "final_exam_submitted" for n in a.get("/api/admin/notifications").json()["items"])
    assert a.post(f"/api/admin/final-results/{start['attempt_id']}/release").status_code == 200
    assert a.post(f"/api/admin/final-results/{start['attempt_id']}/release").status_code == 200   # idempotent
    res = c.get("/api/courses/html5/final-result").json()
    assert res["state"] == "released" and res["score_pct"] == 100 and res["passed"] is True
    assert c.get("/api/courses/html5/progress").json()["course_completed"] is True
    with SessionLocal() as db:
        assert db.query(XPEvent).filter_by(kind="quiz_pass").count() == 1


def test_wrong_answers_fail_and_partial_multiple_is_wrong():
    seed_all()
    c = student(enroll="html5")
    qid, bad = html_answers(c, right=False)
    r, start = take(c, qid, bad)
    assert r.json()["pending_review"] is True
    _release(start["attempt_id"])
    assert c.get("/api/courses/html5/final-result").json()["passed"] is False
    start = c.post(f"/api/quizzes/{qid}/start").json()               # a failed result can be retaken
    ids = [q["id"] for q in start["questions"]]
    partial = {str(ids[0]): ["b"], str(ids[1]): ["c"], str(ids[2]): ["a", "b"]}
    assert c.post(f"/api/quizzes/{qid}/submit", json={"attempt_id": start["attempt_id"], "answers": partial}).json()["pending_review"]
    a = admin()
    row = next(i for i in a.get("/api/admin/final-results?released=false").json()["items"] if i["attempt_id"] == start["attempt_id"])
    assert row["score_pct"] == 67 and row["passed"] is True  # 2 of 3, pass mark 60


def test_short_answer_is_case_and_space_insensitive():
    seed_all()
    c = student(enroll="python")
    qid = quiz_id(c, "python", "chapter")
    start = c.post(f"/api/quizzes/{qid}/start").json()
    short = next(q["id"] for q in start["questions"] if q["qtype"] == "short")
    r = c.post(f"/api/quizzes/{qid}/submit", json={"attempt_id": start["attempt_id"], "answers": {str(short): ["  DEF "]}}).json()
    assert next(x for x in r["results"] if x["question_id"] == short)["correct"] is True


def test_attempt_cannot_be_reused_or_borrowed():
    seed_all()
    c = student(enroll="html5")
    qid, good = html_answers(c)
    start = c.post(f"/api/quizzes/{qid}/start").json()
    body = {"attempt_id": start["attempt_id"], "answers": good}
    assert c.post(f"/api/quizzes/{qid}/submit", json=body).status_code == 200
    assert c.post(f"/api/quizzes/{qid}/submit", json=body).status_code == 409
    other = student("other@example.com", enroll="html5")
    assert other.post(f"/api/quizzes/{qid}/submit", json=body).status_code == 403   # their own final exam is still locked
    finish_lessons(other, "html5")
    assert other.post(f"/api/quizzes/{qid}/submit", json=body).status_code == 404


def test_timed_quiz_rejects_late_submission():
    seed_all()
    c = student(enroll="python")
    unlock_final(c, "python")
    qid = quiz_id(c, "python", "final")
    start = c.post(f"/api/quizzes/{qid}/start").json()
    from datetime import datetime, timedelta, timezone
    with SessionLocal() as db:
        a = db.get(QuizAttempt, start["attempt_id"])
        a.started_at = datetime.now(timezone.utc) - timedelta(minutes=60)
        db.commit()
    r = c.post(f"/api/quizzes/{qid}/submit", json={"attempt_id": start["attempt_id"], "answers": {}})
    assert r.status_code == 409
    with SessionLocal() as db:
        assert db.get(QuizAttempt, start["attempt_id"]).score_pct == 0


def test_course_completion_needs_all_lessons_and_final_exam():
    seed_all()
    c = student(enroll="html5")
    for l in ("page-structure", "text-and-links", "lists-and-images"):
        p = c.post(f"/api/courses/html5/lessons/{l}/complete").json()
    assert p["percent"] == 100 and p["course_completed"] is False  # final exam still required
    qid, good = html_answers(c)
    _, start = take(c, qid, good)
    assert c.get("/api/courses/html5/progress").json()["course_completed"] is False   # result not released yet
    _release(start["attempt_id"])
    assert c.get("/api/courses/html5/progress").json()["course_completed"] is True


@pytest.fixture
def judge(monkeypatch):
    monkeypatch.setattr(executor, "execute", fake_execute)


def test_reference_solutions_pass_every_seeded_challenge(judge):
    seed_all()
    c = student()
    for ch in CHALLENGES:
        r = c.post(f"/api/challenges/{ch['slug']}/submit", json={"language": "python", "source": ch["ref"]}).json()
        assert r["status"] == "accepted" and r["passed"] == r["total"] == 4, ch["slug"]


def test_wrong_and_crashing_code_and_hidden_tests_stay_hidden(judge):
    seed_all()
    c = student()
    wrong = c.post("/api/challenges/sum-of-two/submit", json={"language": "python", "source": "print(0)"}).json()
    assert wrong["status"] == "wrong"
    crash = c.post("/api/challenges/sum-of-two/submit", json={"language": "python", "source": "raise SystemExit(3)"}).json()
    assert crash["status"] == "error"
    hidden = [t for t in wrong["results"] if t["hidden"]]
    assert hidden and all("expected" not in t and "input" not in t and "actual" not in t for t in hidden)
    detail = c.get("/api/challenges/sum-of-two").json()
    assert detail["hidden_test_count"] == 2 and "3000000" not in str(detail)
    assert len(c.get("/api/challenges/sum-of-two/submissions").json()["items"]) == 2


def test_execution_unavailable_is_reported_not_faked():
    seed_all()
    c = student()
    assert c.post("/api/code/run", json={"language": "python", "source": "print(1)"}).status_code == 503
    assert c.post("/api/challenges/sum-of-two/submit", json={"language": "python", "source": "print(1)"}).status_code == 503


def test_run_code_validation_and_auth(judge, client):
    assert client.post("/api/code/run", json={"language": "python", "source": "print(1)"}).status_code == 401
    c = student()
    assert c.post("/api/code/run", json={"language": "ruby", "source": "x"}).status_code == 422
    assert c.post("/api/code/run", json={"language": "python", "source": "x" * 30000}).status_code == 422
    assert c.post("/api/code/run", json={"language": "python", "source": "print(7)"}).json()["stdout"].strip() == "7"
