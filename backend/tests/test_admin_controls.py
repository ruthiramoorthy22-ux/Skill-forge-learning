"""Admin controls: one editable price, admin unlock of certificates, delete/edit of content, projects, sample certificate."""
from app import payments
from app.db import SessionLocal
from app.models import AppSetting, CertificateGrant, Enrollment, LessonProgress
from helpers import admin, approve_project, complete_course, seed_all, student
from test_certificates import SECRET, outbox, pay_for, razorpay, sign  # noqa: F401  (fixtures)


def test_default_price_is_55_for_every_course_and_admin_can_change_it(razorpay):
    seed_all()
    a = admin()
    assert a.get("/api/admin/settings").json() == {"certificate_price_inr": 55, "certificate_release": "auto", "project_required": True}
    assert student("p@example.com").get("/api/pricing").json() == {"certificate_price_inr": 55}
    assert a.patch("/api/admin/settings", json={"certificate_price_inr": 0}).status_code == 422
    assert a.patch("/api/admin/settings", json={"certificate_price_inr": 149}).json()["certificate_price_inr"] == 149
    c = student(enroll="html5")
    complete_course(c, "html5")
    approve_project(c, "html5", a)
    st = c.get("/api/courses/html5/certificate").json()
    assert st["price_inr"] == 149
    assert c.post("/api/courses/html5/certificate/order").json()["amount"] == 14900
    c2 = student("two@example.com", enroll="css3")
    complete_course(c2, "css3")
    assert c2.get("/api/courses/css3/certificate").json()["price_inr"] == 149      # same price on every course
    assert any(x["action"] == "settings.price" for x in a.get("/api/admin/audit-logs").json()["items"])


def test_students_cannot_use_admin_endpoints():
    seed_all()
    c = student()
    assert c.get("/api/admin/settings").status_code == 403
    assert c.patch("/api/admin/settings", json={"certificate_price_inr": 1}).status_code == 403
    assert c.post("/api/admin/certificate-unlock", json={"user_id": "x", "course_id": 1}).status_code == 403
    assert c.delete("/api/admin/courses/1").status_code == 403


def test_admin_release_mode_paid_student_waits_for_admin_unlock(razorpay, outbox):
    seed_all()
    a = admin()
    a.patch("/api/admin/settings", json={"certificate_release": "admin"})
    c = student("pay@example.com", "Payer", enroll="html5")
    complete_course(c, "html5")
    approve_project(c, "html5", a)
    _, r = pay_for(c)
    assert r.json()["paid"] is True and r.json()["issued"] is False
    st = c.get("/api/courses/html5/certificate").json()
    assert st["awaiting_admin"] is True and "admin will unlock" in st["locked_reason"]
    assert any(n["kind"] == "certificate_paid" for n in a.get("/api/admin/notifications").json()["items"])
    req = a.get("/api/admin/certificate-requests").json()
    assert req["release_mode"] == "admin" and [(i["email"], i["paid"]) for i in req["items"]] == [("pay@example.com", True)]
    row = req["items"][0]
    out = a.post("/api/admin/certificate-unlock", json={"user_id": row["user_id"], "course_id": row["course_id"], "send_email": True}).json()
    assert out["unlocked"] and out["certificate_id"] and out["emailed"] is True
    assert outbox[-1][0] == "pay@example.com" and outbox[-1][3][0][0].endswith(".pdf")
    assert c.get("/api/courses/html5/certificate").json()["issued"] is True
    assert a.get("/api/admin/certificate-requests").json()["items"] == []


def test_admin_can_unlock_without_payment_but_not_before_completion(razorpay):
    seed_all()
    a = admin()
    c = student("free@example.com", enroll="html5")
    uid = c.get("/api/auth/me").json()["id"]
    cid = a.get("/api/admin/courses").json()["items"]
    html = next(x["id"] for x in cid if x["slug"] == "html5")
    assert a.post("/api/admin/certificate-unlock", json={"user_id": uid, "course_id": html}).status_code == 409
    complete_course(c, "html5")
    assert c.get("/api/courses/html5/certificate").json()["issued"] is False
    approve_project(c, "html5", a)
    r = a.post("/api/admin/certificate-unlock", json={"user_id": uid, "course_id": html}).json()
    assert r["certificate_id"] and r["emailed"] is False
    assert c.get("/api/courses/html5/certificate").json()["issued"] is True
    a.post("/api/admin/certificate-unlock", json={"user_id": uid, "course_id": html})   # repeating is harmless
    with SessionLocal() as db:
        assert db.query(CertificateGrant).count() == 1


def test_sample_certificate_preview_is_public_and_a_jpeg():
    seed_all()
    r = student("v@example.com").get("/api/courses/html5/certificate/preview")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content[:2] == b"\xff\xd8"
    assert student("w@example.com").get("/api/courses/nope/certificate/preview").status_code == 404


def test_delete_lesson_module_quiz_and_course_with_progress():
    seed_all()
    a = admin()
    c = student(enroll="css3")
    uid = c.get("/api/auth/me").json()["id"]
    course = next(x for x in a.get("/api/admin/courses").json()["items"] if x["slug"] == "css3")
    detail = a.get(f"/api/admin/courses/{course['id']}").json()
    lesson = detail["modules"][0]["lessons"][0]
    c.post(f"/api/courses/css3/lessons/{lesson['slug']}/complete")
    assert a.delete(f"/api/admin/lessons/{lesson['id']}").json() == {"deleted": True}
    assert a.get(f"/api/admin/lessons/{lesson['id']}").status_code == 404
    with SessionLocal() as db:
        assert db.query(LessonProgress).filter_by(user_id=uid).count() == 0
    mid = detail["modules"][0]["id"]
    assert a.patch(f"/api/admin/modules/{mid}", json={"title": "Renamed"}).status_code == 200
    quiz = next(q for q in a.get("/api/admin/quizzes").json()["items"] if q["course_slug"] == "css3")
    assert a.delete(f"/api/admin/quizzes/{quiz['id']}").json()["deleted"]
    assert a.delete(f"/api/admin/modules/{mid}").json()["deleted"]
    assert a.patch(f"/api/admin/courses/{course['id']}", json={"title": "CSS Edited", "category_id": "web-development"}).status_code == 200
    assert a.patch(f"/api/admin/courses/{course['id']}", json={"category_id": "nope"}).status_code == 422
    assert a.delete(f"/api/admin/courses/{course['id']}").json()["deleted"]
    with SessionLocal() as db:
        assert db.query(Enrollment).filter_by(user_id=uid).count() == 0
    assert a.delete("/api/admin/courses/9999").status_code == 404


def test_course_with_a_paid_certificate_cannot_be_deleted(razorpay, outbox):
    seed_all()
    a = admin()
    c = student(enroll="html5")
    complete_course(c, "html5")
    approve_project(c, "html5", a)
    pay_for(c)
    html = next(x["id"] for x in a.get("/api/admin/courses").json()["items"] if x["slug"] == "html5")
    r = a.delete(f"/api/admin/courses/{html}")
    assert r.status_code == 409 and "Unpublish" in r.json()["detail"]


def test_challenge_edit_and_delete():
    seed_all()
    a = admin()
    body = {"slug": "double-it", "title": "Double it", "language": "python", "difficulty": "easy", "topic": "math",
            "statement_md": "Print twice the number.", "tests": [{"stdin": "2\n", "expected": "4", "hidden": False}], "published": True}
    assert a.post("/api/admin/challenges", json=body).status_code == 201
    assert any(x["slug"] == "double-it" for x in a.get("/api/admin/challenges").json()["items"])
    assert a.put("/api/admin/challenges/double-it", json={**body, "title": "Double it!", "difficulty": "medium"}).status_code == 200
    got = a.get("/api/admin/challenges/double-it").json()
    assert got["title"] == "Double it!" and got["difficulty"] == "medium" and got["tests"][0]["expected"] == "4"
    assert a.put("/api/admin/challenges/double-it", json={**body, "slug": "other"}).status_code == 422
    assert a.delete("/api/admin/challenges/double-it").json()["deleted"]
    assert a.get("/api/admin/challenges/double-it").status_code == 404
    assert student("x@example.com").get("/api/challenges/double-it").status_code == 404


def test_projects_seeded_then_admin_add_edit_hide_delete():
    from app.seed_projects import seed_projects
    seed_all()
    with SessionLocal() as db:
        seed_projects(db)
    a, s = admin(), student("pr@example.com")
    first = s.get("/api/projects").json()["items"]
    assert len(first) == 12 and all(p["status"] == "planned" for p in first)
    pid = a.post("/api/admin/projects", json={"slug": "snake-game", "title": "Snake game", "level": "beginner",
                                              "summary": "Build it.", "body_md": "## Steps\n1. Draw the board"}).json()["id"]
    assert a.post("/api/admin/projects", json={"slug": "snake-game", "title": "Dup"}).status_code == 409
    assert next(p for p in s.get("/api/projects").json()["items"] if p["slug"] == "snake-game")["status"] == "available"
    a.patch(f"/api/admin/projects/{pid}", json={"published": False})
    assert all(p["slug"] != "snake-game" for p in s.get("/api/projects").json()["items"])
    assert a.delete(f"/api/admin/projects/{pid}").json()["deleted"]
    with SessionLocal() as db:
        seed_projects(db)                                   # never brings back deleted items once the table has rows
        assert db.query(AppSetting).count() == 0


def test_tutor_endpoint_is_gone():
    seed_all()
    assert student("t@example.com").post("/api/tutor/ask", json={"question": "What is a loop?"}).status_code == 404
