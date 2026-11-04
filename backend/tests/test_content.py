import subprocess
import sys

from app.db import SessionLocal
from app.models import Enrollment, LessonProgress
from app.seed_content import CONTENT, seed_content

CRED = {"email": "learner@example.com", "display_name": "Learner", "password": "correct-horse-battery"}


def signed_in(client):
    seed()
    assert client.post("/api/auth/register", json=CRED).status_code == 201
    return client


def seed():
    with SessionLocal() as db:
        seed_content(db)


def test_python_lesson_examples_produce_the_expected_output():
    checked = 0
    for course in CONTENT:
        for module in course["modules"]:
            for lesson in module["lessons"]:
                if lesson["lang"] == "python":
                    r = subprocess.run([sys.executable, "-c", lesson["code"]], capture_output=True, text=True, timeout=10)
                    assert r.returncode == 0, lesson["slug"] + ": " + r.stderr
                    assert r.stdout.strip() == lesson["out"], lesson["slug"]
                    checked += 1
    assert checked == 5


def test_seeding_is_idempotent():
    seed(); seed()
    assert len(__import__("app.routes_learning", fromlist=["x"]).lesson_counts(SessionLocal())) == 3


def test_catalog_marks_only_seeded_courses_available(client):
    seed()
    items = client.get("/api/courses?status=available").json()["items"]
    assert {c["slug"] for c in items} == {"python", "html5", "css3"}
    assert next(c for c in items if c["slug"] == "python")["lesson_count"] == 5


def test_course_detail_outline_is_public_but_lessons_are_not(client):
    seed()
    d = client.get("/api/courses/python").json()
    assert d["lesson_count"] == 5 and len(d["outline"]) == 2 and "body_md" not in str(d)
    assert client.get("/api/courses/python/lessons/loops").status_code == 401
    assert client.get("/api/courses/java").json()["outline"] is None


def test_must_enroll_before_reading_lessons(client):
    signed_in(client)
    assert client.get("/api/courses/python/lessons/first-program").status_code == 403
    assert client.post("/api/courses/python/enroll").json()["enrolled"] is True
    r = client.get("/api/courses/python/lessons/first-program")
    assert r.status_code == 200 and r.json()["prev"] is None and r.json()["next"] == "variables-types"


def test_enroll_is_idempotent_and_unknown_course_404(client):
    signed_in(client)
    client.post("/api/courses/python/enroll"); client.post("/api/courses/python/enroll")
    with SessionLocal() as db:
        assert db.query(Enrollment).count() == 1
    assert client.post("/api/courses/java/enroll").status_code == 404


def test_progress_is_calculated_from_records(client):
    signed_in(client)
    client.post("/api/courses/python/enroll")
    assert client.get("/api/courses/python/progress").json()["percent"] == 0
    client.post("/api/courses/python/lessons/first-program/complete")
    p = client.post("/api/courses/python/lessons/first-program/complete").json()  # repeat: no double count
    assert p["completed"] == ["first-program"] and p["percent"] == 20 and p["last_lesson"] == "first-program"
    with SessionLocal() as db:
        assert db.query(LessonProgress).count() == 1
    row = client.get("/api/me/enrollments").json()["items"][0]
    assert (row["course_slug"], row["completed"], row["total"], row["percent"]) == ("python", 1, 5, 20)


def test_progress_is_private_to_each_student(client):
    signed_in(client)
    client.post("/api/courses/python/enroll")
    client.post("/api/courses/python/lessons/loops/complete")
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={**CRED, "email": "other@example.com"})
    assert client.get("/api/me/enrollments").json()["items"] == []
    assert client.get("/api/courses/python/lessons/loops").status_code == 403


def test_unknown_lesson_404(client):
    signed_in(client)
    client.post("/api/courses/python/enroll")
    assert client.get("/api/courses/python/lessons/nope").status_code == 404
    assert client.post("/api/courses/python/lessons/nope/complete").status_code == 404
