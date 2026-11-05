"""Project submission -> admin review -> certificate, student profile, and admin editing of student details."""
from datetime import date
from io import BytesIO

from PIL import Image, ImageChops

from app.certificate_image import render_certificate
from helpers import PROJECT, admin, approve_project, complete_course, seed_all, student
from test_certificates import SECRET, outbox, pay_for, razorpay, sign  # noqa: F401  (fixtures)


def test_project_needs_a_finished_course_and_valid_fields():
    seed_all()
    c = student("p1@example.com", enroll="html5")
    assert c.get("/api/courses/html5/project").json() == {"can_submit": False, "submission": None, "assigned": None}
    assert c.put("/api/courses/html5/project", json=PROJECT).status_code == 403
    complete_course(c, "html5")
    assert c.get("/api/courses/html5/project").json()["can_submit"] is True
    assert c.put("/api/courses/html5/project", json={**PROJECT, "title": "ab"}).status_code == 422
    assert c.put("/api/courses/html5/project", json={**PROJECT, "description": "too short"}).status_code == 422
    assert c.put("/api/courses/html5/project", json={**PROJECT, "repo_url": "javascript:alert(1)"}).status_code == 422
    assert c.put("/api/courses/html5/project", json={**PROJECT, "demo_url": "ftp://x.y"}).status_code == 422
    assert student("other@example.com").put("/api/courses/html5/project", json=PROJECT).status_code == 403   # not enrolled


def test_submission_notifies_admin_and_gates_payment_and_certificate(razorpay, outbox):
    seed_all()
    a, c = admin(), student("p2@example.com", "Pri", enroll="html5")
    complete_course(c, "html5")
    st = c.get("/api/courses/html5/certificate").json()
    assert st["project_required"] and not st["project_approved"] and "Submit your project" in st["locked_reason"]
    assert c.post("/api/courses/html5/certificate/order").status_code == 403          # cannot pay before approval
    sub = c.put("/api/courses/html5/project", json=PROJECT).json()["submission"]
    assert sub["status"] == "submitted"
    assert "waiting for the admin" in c.get("/api/courses/html5/certificate").json()["locked_reason"]
    assert any(n["kind"] == "project_submitted" and "Pocket Calculator" in n["message"] for n in a.get("/api/admin/notifications").json()["items"])
    row = a.get("/api/admin/project-submissions?status=submitted").json()["items"][0]
    assert row["student"] == "Pri" and row["course"] and row["repo_url"] == PROJECT["repo_url"] and row["paid"] is False
    # unlock is refused while the project is not approved
    r = a.post("/api/admin/certificate-unlock", json={"user_id": row["user_id"], "course_id": row["course_id"]})
    assert r.status_code == 409 and "approve" in r.json()["detail"]
    # approve, then pay -> certificate issued (auto mode)
    assert a.patch(f"/api/admin/project-submissions/{row['id']}/review", json={"decision": "approved"}).json()["status"] == "approved"
    assert c.get("/api/courses/html5/certificate").json()["project_approved"] is True
    _, paid = pay_for(c)
    assert paid.json()["issued"] is True
    assert c.put("/api/courses/html5/project", json=PROJECT).status_code == 409        # approved projects are final


def test_changes_requested_then_resubmit_then_release_without_payment():
    seed_all()
    a, c = admin(), student("p3@example.com", enroll="css3")
    complete_course(c, "css3")
    c.put("/api/courses/css3/project", json=PROJECT)
    sid = a.get("/api/admin/project-submissions").json()["items"][0]["id"]
    assert a.patch(f"/api/admin/project-submissions/{sid}/review", json={"decision": "changes_requested"}).status_code == 422
    a.patch(f"/api/admin/project-submissions/{sid}/review", json={"decision": "changes_requested", "feedback": "Add a reset button."})
    mine = c.get("/api/courses/css3/project").json()["submission"]
    assert mine["status"] == "changes_requested" and mine["admin_feedback"] == "Add a reset button."
    assert c.get("/api/courses/css3/certificate").json()["issued"] is False
    again = c.put("/api/courses/css3/project", json={**PROJECT, "title": "Calculator v2"}).json()["submission"]
    assert again["status"] == "submitted" and again["admin_feedback"] == "" and again["id"] == sid   # same row, resubmitted
    out = a.patch(f"/api/admin/project-submissions/{sid}/review", json={"decision": "approved", "release": True}).json()
    assert out["certificate_id"] and out["certificate_issued"] is True
    assert c.get("/api/courses/css3/certificate").json()["issued"] is True


def test_certificate_never_prints_the_project_name():
    plain = render_certificate("Asha K", "HTML5", date(2026, 11, 1), "ID1")
    again = render_certificate("Asha K", "HTML5", date(2026, 11, 1), "ID1")
    assert ImageChops.difference(plain.convert("RGB"), again.convert("RGB")).getbbox() is None
    seed_all()
    a, c = admin(), student("p4@example.com", "Asha K", enroll="html5")
    complete_course(c, "html5")
    approve_project(c, "html5", a, release=True)
    cid = c.get("/api/courses/html5/certificate").json()["certificate_id"]
    png = c.get(f"/api/certificates/{cid}/download?format=png")
    assert png.status_code == 200 and Image.open(BytesIO(png.content)).size == plain.size


def test_project_requirement_can_be_switched_off():
    seed_all()
    a, c = admin(), student("p5@example.com", enroll="html5")
    complete_course(c, "html5")
    a.patch("/api/admin/settings", json={"project_required": False})
    assert a.get("/api/admin/settings").json()["project_required"] is False
    uid, cid = c.get("/api/auth/me").json()["id"], next(x["id"] for x in a.get("/api/admin/courses").json()["items"] if x["slug"] == "html5")
    assert a.post("/api/admin/certificate-unlock", json={"user_id": uid, "course_id": cid}).json()["certificate_id"]


def test_student_profile_saves_and_validates():
    seed_all()
    c = student("p6@example.com", "Ravi")
    assert c.get("/api/me/profile").json() == {"display_name": "Ravi", "email": "p6@example.com", "phone": "", "college_name": "",
                                               "school_name": "", "tenth_mark": "", "twelfth_mark": "", "degree": "", "year_of_study": "", "city": "", "avatar": ""}
    body = {"display_name": "Ravi Kumar", "phone": "+91 98765 43210", "college_name": "Chennai Institute of Technology",
            "school_name": "St. Mary's School", "degree": "B.E. CSE", "year_of_study": "3rd year", "city": "Chennai"}
    out = c.put("/api/me/profile", json=body).json()
    assert out["display_name"] == "Ravi Kumar" and out["college_name"] == "Chennai Institute of Technology" and out["email"] == "p6@example.com"
    assert c.get("/api/me/profile").json()["phone"] == "+91 98765 43210"
    assert c.get("/api/auth/me").json()["display_name"] == "Ravi Kumar"
    assert c.put("/api/me/profile", json={**body, "phone": "abc"}).status_code == 422
    assert c.put("/api/me/profile", json={**body, "display_name": "   "}).status_code == 422
    from fastapi.testclient import TestClient
    from app.main import app
    assert TestClient(app, base_url="https://testserver").get("/api/me/profile").status_code == 401


def test_name_locks_after_certificate_but_admin_can_edit_everything():
    seed_all()
    a, c = admin(), student("p7@example.com", "Meena", enroll="html5")
    complete_course(c, "html5")
    approve_project(c, "html5", a, release=True)
    assert c.put("/api/me/profile", json={"display_name": "Meena Devi"}).status_code == 409
    uid = c.get("/api/auth/me").json()["id"]
    edit = {"display_name": "Meena Devi", "email": "meena.new@example.com", "phone": "9876543210", "college_name": "CIT",
            "school_name": "Govt School", "degree": "B.E.", "year_of_study": "2", "city": "Madurai"}
    assert a.put(f"/api/admin/students/{uid}/profile", json=edit).json()["college_name"] == "CIT"
    d = a.get(f"/api/admin/students/{uid}").json()
    assert d["display_name"] == "Meena Devi" and d["email"] == "meena.new@example.com" and d["profile"]["school_name"] == "Govt School"
    assert any(s["id"] == uid and s["college_name"] == "CIT" and s["phone"] == "9876543210" for s in a.get("/api/admin/students").json()["items"])
    other = student("p8@example.com")
    assert a.put(f"/api/admin/students/{uid}/profile", json={**edit, "email": "p8@example.com"}).status_code == 409
    assert a.put("/api/admin/students/nope/profile", json=edit).status_code == 404
    assert other.put(f"/api/admin/students/{uid}/profile", json=edit).status_code == 403
    assert any(x["action"] == "student.edit" for x in a.get("/api/admin/audit-logs").json()["items"])
    csv = a.get("/api/admin/students/export.csv").text
    assert "college_name" in csv and "CIT" in csv
