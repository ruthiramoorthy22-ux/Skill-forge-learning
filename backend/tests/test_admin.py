from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app import main as app_main
from app.models import Course, Lesson, LessonProgress, User, UserPresence
from app.catalog import COURSES
from app.seed_content import seed_catalog_courses
from helpers import ADMIN_PW, PW, admin, seed_all, student

ADMIN_GETS = ["/api/admin/overview", "/api/admin/students", "/api/admin/students/export.csv", "/api/admin/live",
              "/api/admin/courses", "/api/admin/enrollments", "/api/admin/audit-logs", "/api/admin/analytics",
              "/api/admin/payments", "/api/admin/certificates", "/api/admin/notifications"]


@pytest.mark.parametrize("path", ADMIN_GETS)
def test_every_admin_endpoint_is_protected(path, client):
    assert client.get(path).status_code == 401
    s = student()
    assert s.get(path).status_code == 403


def test_student_cannot_use_admin_writes():
    s = student()
    assert s.post("/api/admin/courses", json={}).status_code == 403
    assert s.patch("/api/admin/students/x/status", json={"status": "disabled"}).status_code == 403
    assert s.patch("/api/admin/lessons/1", json={"title": "xx"}).status_code == 403


def test_overview_has_real_counts_and_payments_not_connected():
    seed_all()
    student("a@example.com", enroll="python")
    student("b@example.com")
    o = admin().get("/api/admin/overview").json()
    assert (o["total_students"], o["total_enrollments"], o["total_courses"]) == (2, 1, 3)
    assert o["verified_payments"] is None and o["payments_connected"] is False and o["certificates_issued"] == 0


def test_student_search_filter_sort_paginate_and_no_secrets():
    seed_all()
    student("asha@example.com", "Asha", enroll="python")
    student("ravi@example.com", "Ravi", enroll="html5")
    student("mei@example.com", "Mei")
    a = admin()
    assert a.get("/api/admin/students?q=ASHA").json()["total"] == 1
    assert a.get("/api/admin/students?course=html5").json()["items"][0]["display_name"] == "Ravi"
    assert a.get("/api/admin/students?level=beginner").json()["total"] == 2
    r = a.get("/api/admin/students?page_size=2&page=2&sort=activity")
    assert r.json()["total"] == 3 and len(r.json()["items"]) == 1
    assert "password" not in a.get("/api/admin/students").text


def test_student_detail_and_status_control():
    seed_all()
    s = student("asha@example.com", "Asha", enroll="python")
    sid = s.get("/api/auth/me").json()["id"]
    a = admin()
    d = a.get(f"/api/admin/students/{sid}").json()
    assert d["course_history"][0]["course"] == "Python" and d["assessment_history"] == []
    assert a.patch(f"/api/admin/students/{sid}/status", json={"status": "disabled"}).status_code == 200
    assert s.get("/api/auth/me").status_code == 401  # existing session stops working
    assert TestClient(app, base_url="https://testserver").post("/api/auth/login", json={"email": "asha@example.com", "password": PW}).status_code == 403
    with SessionLocal() as db:
        admin_id = db.query(User).filter_by(role="admin").one().id
    assert a.patch(f"/api/admin/students/{admin_id}/status", json={"status": "disabled"}).status_code == 404


def test_csv_export_blocks_formula_injection_and_is_audited():
    student("evil@example.com", "=HYPERLINK(\"http://x\")")
    a = admin()
    r = a.get("/api/admin/students/export.csv")
    assert r.headers["content-type"].startswith("text/csv") and "'=HYPERLINK" in r.text and ",=HYPERLINK" not in r.text
    assert a.get("/api/admin/audit-logs").json()["items"][0]["action"] == "student.export"


def test_course_lifecycle_preserves_progress_and_is_audited():
    seed_all()
    a = admin()
    assert a.post("/api/admin/courses", json={"slug": "x", "title": "T", "category_id": "nope", "level": "beginner"}).status_code == 422
    body = {"slug": "intro-sql", "title": "Intro SQL", "category_id": "database-backend", "level": "beginner", "summary": "s",
            "objectives": ["o"], "est_minutes": 30}
    cid = a.post("/api/admin/courses", json=body).json()["id"]
    assert a.post("/api/admin/courses", json=body).status_code == 409
    mid = a.post("/api/admin/modules", json={"course_id": cid, "title": "Basics"}).json()["id"]
    lesson = {"module_id": mid, "slug": "select", "title": "SELECT", "body_md": "Hello", "example_lang": "python", "published": True}
    lid = a.post("/api/admin/lessons", json=lesson).json()["id"]
    assert a.post("/api/admin/lessons", json=lesson).status_code == 409
    assert a.get("/api/courses?status=available").json()["total"] == 3          # unpublished course is hidden
    a.patch(f"/api/admin/courses/{cid}", json={"published": True})
    assert "intro-sql" in {c["slug"] for c in a.get("/api/courses?status=available").json()["items"]}
    s = student(enroll="intro-sql")
    assert s.get("/api/courses/intro-sql/lessons/select").json()["body_md"] == "Hello"
    s.post("/api/courses/intro-sql/lessons/select/complete")
    a.patch(f"/api/admin/lessons/{lid}", json={"body_md": "Updated"})
    assert s.get("/api/courses/intro-sql/lessons/select").json()["completed"] is True
    with SessionLocal() as db:
        assert db.query(LessonProgress).count() == 1
    acts = [x["action"] for x in a.get("/api/admin/audit-logs").json()["items"]]
    assert {"course.create", "course.update", "module.create", "lesson.create", "lesson.update"} <= set(acts)


def _bearer_admin():
    a = admin()
    response = a.post("/api/auth/admin/login", json={"email": settings.admin_email, "password": ADMIN_PW},
                      headers={"X-Client": "app"})
    a.headers["Authorization"] = f"Bearer {response.json()['token']}"
    return a


def _bearer_student(email="course-manager-student@example.com"):
    s = TestClient(app, base_url="https://testserver")
    response = s.post("/api/auth/register", json={"email": email, "display_name": "Learner", "password": PW},
                      headers={"X-Client": "app"})
    s.headers["Authorization"] = f"Bearer {response.json()['token']}"
    return s


def test_admin_lists_full_catalog_and_single_publish_persists_after_relogin():
    seed_all()
    with SessionLocal() as db:
        python = db.query(Course).filter_by(slug="python").one()
        python_id = python.id
        lesson_count = sum(len(module.lessons) for module in python.modules)
        seed_catalog_courses(db)
        python = db.query(Course).filter_by(slug="python").one()
        assert python.id == python_id
        assert sum(len(module.lessons) for module in python.modules) == lesson_count

    a = _bearer_admin()
    items = a.get("/api/admin/courses").json()["items"]
    assert len(items) == len(COURSES)
    target = next(item for item in items if item["slug"] == "python")
    assert target["status"] == "available"

    s = _bearer_student()
    assert s.patch(f"/api/admin/courses/{target['id']}", json={"published": False}).status_code == 403
    assert a.patch(f"/api/admin/courses/{target['id']}", json={"published": False}).json()["published"] is False
    assert next(item for item in a.get("/api/admin/courses").json()["items"] if item["id"] == target["id"])["status"] == "in_development"
    assert a.patch(f"/api/admin/courses/{target['id']}", json={"published": True}).json()["published"] is True
    assert next(item for item in a.get("/api/admin/courses").json()["items"] if item["id"] == target["id"])["status"] == "available"

    a.post("/api/auth/logout")
    a.headers.pop("Authorization", None)
    login = a.post("/api/auth/admin/login", json={"email": settings.admin_email, "password": ADMIN_PW},
                   headers={"X-Client": "app"})
    a.headers["Authorization"] = f"Bearer {login.json()['token']}"
    assert next(item for item in a.get("/api/admin/courses").json()["items"] if item["id"] == target["id"])["status"] == "available"
    assert next(item for item in a.get("/api/courses?status=available&page_size=100").json()["items"]
                if item["slug"] == "python")["status"] == "available"


def test_publish_all_is_admin_only_and_student_enrollments_hide_unavailable_courses():
    seed_all()
    with SessionLocal() as db:
        seed_catalog_courses(db)
    a = _bearer_admin()
    s = _bearer_student("bulk-publish-student@example.com")
    assert s.post("/api/admin/courses/publish-all").status_code == 403
    assert s.patch("/api/admin/courses/1", json={"published": True}).status_code == 403

    result = a.post("/api/admin/courses/publish-all")
    assert result.status_code == 200 and result.json()["updated"] == len(COURSES)
    assert a.get("/api/courses?status=available&page_size=100").json()["total"] == len(COURSES)
    without_lessons = next(item for item in a.get("/api/admin/courses").json()["items"] if item["lessons"] == 0)
    assert a.get(f"/api/courses/{without_lessons['slug']}").json()["status"] == "available"

    python_id = next(item["id"] for item in a.get("/api/admin/courses").json()["items"] if item["slug"] == "python")
    assert s.post("/api/courses/python/enroll").status_code == 200
    assert len(s.get("/api/me/enrollments").json()["items"]) == 1
    a.patch(f"/api/admin/courses/{python_id}", json={"published": False})
    assert s.get("/api/me/enrollments").json()["items"] == []
    assert all(item["course_slug"] != "python" for item in s.get("/api/me/recommendations").json()["items"])
    assert all(item["slug"] != "python" for item in s.get("/api/courses?q=Python&page_size=100").json()["items"])
    assert s.get("/api/courses/python").status_code == 404
    assert s.get("/api/courses/python/lessons/first-program").status_code == 404


def test_legacy_course_schema_migration_preserves_ids_and_backfills_status(monkeypatch):
    legacy_engine = create_engine("sqlite:///:memory:")
    with legacy_engine.begin() as conn:
        conn.execute(text("""CREATE TABLE courses (
            id INTEGER PRIMARY KEY, slug VARCHAR(80), title VARCHAR(120), category_id VARCHAR(60),
            level VARCHAR(12), summary TEXT, objectives JSON, est_minutes INTEGER, published BOOLEAN
        )"""))
        conn.execute(text("""INSERT INTO courses
            (id, slug, title, category_id, level, summary, objectives, est_minutes, published)
            VALUES (73, 'python', 'Python', 'programming-languages', 'beginner', '', '[]', 0, TRUE)"""))
        conn.execute(text("""INSERT INTO courses
            (id, slug, title, category_id, level, summary, objectives, est_minutes, published)
            VALUES (91, 'html5', 'HTML5', 'web-development', 'beginner', '', '[]', 0, FALSE)"""))

    monkeypatch.setattr(app_main, "engine", legacy_engine)
    monkeypatch.setattr(app_main, "SessionLocal", sessionmaker(bind=legacy_engine))
    app_main.add_missing_columns()
    app_main.backfill_course_statuses()

    with legacy_engine.connect() as conn:
        rows = conn.execute(text("SELECT id, slug, status FROM courses ORDER BY id")).all()
    assert rows == [(73, "python", "available"), (91, "html5", "in_development")]


def test_admin_quiz_validation_and_publish_toggle():
    seed_all()
    a = admin()
    q = lambda **k: {"qtype": "single", "prompt": "Pick one", "options": [{"id": "a", "text": "x"}, {"id": "b", "text": "y"}],
                     "answer": ["a"], **k}
    base = {"course_slug": "python", "title": "Extra", "kind": "chapter", "pass_mark": 50}
    assert a.post("/api/admin/quizzes", json={**base, "questions": [q(answer=["a", "b"])]}).status_code == 422
    assert a.post("/api/admin/quizzes", json={**base, "questions": [q(answer=["z"])]}).status_code == 422
    qid = a.post("/api/admin/quizzes", json={**base, "questions": [q()]}).json()["id"]
    s = student(enroll="python")
    assert s.post(f"/api/quizzes/{qid}/start").status_code == 404            # still unpublished
    a.patch(f"/api/admin/quizzes/{qid}", json={"published": True})
    assert s.post(f"/api/quizzes/{qid}/start").status_code == 200


def test_admin_challenge_create_and_publish():
    a = admin()
    body = {"slug": "double", "title": "Double it", "tests": [{"stdin": "2", "expected": "4"}]}
    assert a.post("/api/admin/challenges", json=body).status_code == 201
    assert a.post("/api/admin/challenges", json=body).status_code == 409
    assert student().get("/api/challenges/double").status_code == 404
    a.patch("/api/admin/challenges/double", json={"published": True})
    assert student("z@example.com").get("/api/challenges/double").status_code == 200


def test_analytics_uses_real_records_and_explains_metrics():
    seed_all()
    student("a@example.com", enroll="python").post("/api/courses/python/lessons/loops/complete")
    student("b@example.com")
    a = admin()
    r = a.get("/api/admin/analytics").json()
    assert sum(x["count"] for x in r["registrations"]) == 2 and r["monthly_active"] == 2
    assert sum(x["count"] for x in r["daily_active"]) == 2 and sum(x["count"] for x in r["enrollments"]) == 1
    assert next(c for c in r["completion"] if c["course"] == "Python")["enrolled"] == 1
    assert r["revenue"]["connected"] is False and "retention_7d" in r["definitions"]
    assert a.get("/api/admin/analytics?from=2026-10-30&to=2026-01-01").status_code == 422
    assert a.get("/api/admin/analytics?from=2020-01-01&to=2026-10-30").status_code == 422


def test_live_view_stops_showing_stale_presence():
    c = student(name="Stale")
    c.post("/api/activity/heartbeat")
    with SessionLocal() as db:
        db.get(UserPresence, db.query(User).one().id).last_seen_at = datetime.now(timezone.utc) - timedelta(seconds=settings.online_timeout_seconds + 60)
        db.commit()
    assert admin().get("/api/admin/live").json()["online"] == []


def test_logout_records_last_logout():
    c = student("lo@example.com", "Lo")
    sid = c.get("/api/auth/me").json()["id"]
    c.post("/api/auth/logout")
    assert admin().get(f"/api/admin/students/{sid}").json()["last_logout_at"] is not None


def test_payments_report_not_configured_and_no_fake_revenue(client):
    a = admin()
    p = a.get("/api/admin/payments").json()
    assert p["connected"] is False and p["items"] == [] and p["verified_revenue_inr"] == 0 and "not configured" in p["message"]
    assert a.get("/api/admin/certificates").json()["items"] == []
    assert client.get("/api/certificates/verify/anything").status_code == 404


def test_admin_can_browse_edit_and_extend_content():
    seed_all()
    a = admin()
    courses = a.get("/api/admin/courses").json()["items"]
    py = next(c for c in courses if c["slug"] == "python")
    detail = a.get(f"/api/admin/courses/{py['id']}").json()
    lesson = detail["modules"][0]["lessons"][0]
    full = a.get(f"/api/admin/lessons/{lesson['id']}").json()
    assert full["body_md"] and a.get("/api/admin/lessons/99999").status_code == 404
    quizzes = a.get("/api/admin/quizzes").json()["items"]
    qz = next(q for q in quizzes if q["kind"] == "chapter")
    before = a.get(f"/api/admin/quizzes/{qz['id']}").json()
    assert "answer" in before["questions"][0]
    new_q = {"qtype": "multiple", "prompt": "Pick the even numbers", "options": [{"id": "a", "text": "2"}, {"id": "b", "text": "3"}, {"id": "c", "text": "4"}], "answer": ["a", "c"]}
    assert a.post(f"/api/admin/quizzes/{qz['id']}/questions", json=new_q).status_code == 201
    assert len(a.get(f"/api/admin/quizzes/{qz['id']}").json()["questions"]) == len(before["questions"]) + 1
    assert a.post(f"/api/admin/quizzes/{qz['id']}/questions", json={**new_q, "answer": ["z"]}).status_code == 422
    s = student(enroll="python")
    assert student("x@example.com").get(f"/api/admin/quizzes/{qz['id']}").status_code == 403
    assert s.get(f"/api/admin/lessons/{lesson['id']}").status_code == 403
