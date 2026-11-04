import subprocess
import sys

from fastapi.testclient import TestClient

from app.config import settings
from app.create_admin import create_admin
from app.db import SessionLocal
from app.main import app
from app.seed_assessments import seed_assessments
from app.seed_content import seed_content

PW = "correct-horse-battery"
ADMIN_PW = "a-very-long-admin-pass"


def seed_all():
    with SessionLocal() as db:
        seed_content(db)
        seed_assessments(db)


def student(email="learner@example.com", name="Learner", enroll=None) -> TestClient:
    c = TestClient(app)
    assert c.post("/api/auth/register", json={"email": email, "display_name": name, "password": PW}).status_code == 201
    if enroll:
        assert c.post(f"/api/courses/{enroll}/enroll").status_code == 200
    return c


def admin() -> TestClient:
    with SessionLocal() as db:
        create_admin(db, settings.admin_email, ADMIN_PW)
    c = TestClient(app)
    assert c.post("/api/auth/admin/login", json={"email": settings.admin_email, "password": ADMIN_PW}).status_code == 200
    return c


def fake_execute(language, source, stdin=""):
    """Test double for Judge0: runs trusted test code locally so the grading logic can be exercised."""
    r = subprocess.run([sys.executable, "-c", source], input=stdin, capture_output=True, text=True, timeout=10)
    ok = r.returncode == 0
    return {"stdout": r.stdout, "stderr": r.stderr, "compile_output": "", "status": "Accepted" if ok else "Runtime Error",
            "status_id": 3 if ok else 11, "time": None, "memory": None}


def quiz_id(c, slug, kind):
    return next(q["id"] for q in c.get(f"/api/courses/{slug}/quizzes").json()["items"] if q["kind"] == kind)


def take(c, qid, answers):
    start = c.post(f"/api/quizzes/{qid}/start").json()
    return c.post(f"/api/quizzes/{qid}/submit", json={"attempt_id": start["attempt_id"], "answers": answers}), start


def finish_lessons(c, slug):
    for m in c.get(f"/api/courses/{slug}").json()["outline"]:
        for l in m["lessons"]:
            assert c.post(f"/api/courses/{slug}/lessons/{l['slug']}/complete").status_code == 200


def unlock_final(c, slug):
    """Completes every lesson and attends every topic test (with empty answers), which unlocks the final exam."""
    finish_lessons(c, slug)
    for q in c.get(f"/api/courses/{slug}/quizzes").json()["items"]:
        if q["kind"] == "chapter":
            take(c, q["id"], {})


def pass_quiz(c, qid):
    from app.db import SessionLocal
    from app.models import Question
    start = c.post(f"/api/quizzes/{qid}/start")
    assert start.status_code == 200, start.text
    with SessionLocal() as db:
        ans = {str(q.id): list(q.answer) for q in db.query(Question).filter_by(quiz_id=qid)}
    r = c.post(f"/api/quizzes/{qid}/submit", json={"attempt_id": start.json()["attempt_id"], "answers": ans})
    assert r.status_code == 200, r.text
    if r.json().get("pending_review"):  # final exam: the student sees nothing until the admin releases the result
        a = admin()
        item = next(i for i in a.get("/api/admin/final-results?released=false").json()["items"] if i["attempt_id"] == start.json()["attempt_id"])
        assert item["passed"], item
        assert a.post(f"/api/admin/final-results/{item['attempt_id']}/release").status_code == 200
        return {"passed": True, "released": True}
    assert r.json()["passed"], r.text
    return r.json()


def complete_course(c, slug):
    unlock_final(c, slug)
    pass_quiz(c, quiz_id(c, slug, "final"))


PROJECT = {"title": "Pocket Calculator", "description": "A small calculator that adds, subtracts, multiplies and divides numbers.",
           "repo_url": "https://github.com/example/calculator", "demo_url": ""}


def approve_project(c, slug, a=None, release=False):
    """The student submits a project and the admin approves it (needed before a certificate)."""
    assert c.put(f"/api/courses/{slug}/project", json=PROJECT).status_code == 200
    a = a or admin()
    sid = next(s["id"] for s in a.get("/api/admin/project-submissions?status=submitted").json()["items"]
               if s["email"] == c.get("/api/auth/me").json()["email"])
    r = a.patch(f"/api/admin/project-submissions/{sid}/review", json={"decision": "approved", "release": release})
    assert r.status_code == 200, r.text
    return r.json()
