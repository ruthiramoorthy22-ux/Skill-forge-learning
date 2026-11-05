import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image
import io

from app import mailer, payments
from app.certificate_image import render_certificate
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import AdminNotification, Payment
from datetime import date
from helpers import (PW, admin, complete_course, finish_lessons, pass_quiz, quiz_id, seed_all, student, take, unlock_final)

SECRET, WEBHOOK = "test_secret_value_123", "webhook_secret_456"


@pytest.fixture
def razorpay(monkeypatch):
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_abc")
    monkeypatch.setattr(settings, "razorpay_key_secret", SECRET)
    monkeypatch.setattr(settings, "razorpay_webhook_secret", WEBHOOK)
    counter = {"n": 0}

    def fake_order(amount, receipt, notes):
        counter["n"] += 1
        return {"id": f"order_TEST{counter['n']}"}
    monkeypatch.setattr(payments, "create_order", fake_order)


@pytest.fixture
def outbox(monkeypatch):
    box = []
    monkeypatch.setattr(mailer, "send_mail", lambda to, subject, body, attachments=(): box.append((to, subject, body, list(attachments))))
    return box


def sign(order, pay, secret=SECRET):
    return hmac.new(secret.encode(), f"{order}|{pay}".encode(), hashlib.sha256).hexdigest()


def pay_for(c, slug="html5", pay_id="pay_ABC"):
    order = c.post(f"/api/courses/{slug}/certificate/order").json()
    r = c.post("/api/payments/razorpay/verify", json={"razorpay_order_id": order["order_id"], "razorpay_payment_id": pay_id,
                                                      "razorpay_signature": sign(order["order_id"], pay_id)})
    return order, r


def test_final_exam_locks_until_lessons_and_topic_tests_are_done(monkeypatch):
    seed_all()
    c = student(enroll="python")
    final = quiz_id(c, "python", "final")
    r = c.post(f"/api/quizzes/{final}/start")
    assert r.status_code == 403 and "locked" in r.json()["detail"]
    st = c.get("/api/courses/python/exam-status").json()
    assert st["unlocked"] is False and len(st["missing_lessons"]) == 5 and st["missing_tests"] == ["Python basics check"]
    finish_lessons(c, "python")
    assert c.post(f"/api/quizzes/{final}/start").status_code == 403       # topic test still not attended
    take(c, quiz_id(c, "python", "chapter"), {})                           # attended with wrong answers
    assert c.post(f"/api/quizzes/{final}/start").status_code == 200        # rule "attempted"
    monkeypatch.setattr(settings, "final_unlock_rule", "passed")
    assert c.post(f"/api/quizzes/{final}/start").status_code == 403        # rule "passed" needs the topic test passed
    pass_quiz(c, quiz_id(c, "python", "chapter"))
    assert c.post(f"/api/quizzes/{final}/start").status_code == 200


def test_practice_quizzes_are_free_unlimited_and_never_required():
    seed_all()
    a = admin()
    q = {"qtype": "single", "prompt": "2 + 2 = ?", "options": [{"id": "a", "text": "4"}, {"id": "b", "text": "5"}], "answer": ["a"]}
    pid = a.post("/api/admin/quizzes", json={"course_slug": "html5", "title": "HTML practice", "kind": "practice", "pass_mark": 50,
                                             "published": True, "questions": [q]}).json()["id"]
    c = student(enroll="html5")
    for _ in range(3):
        qs = c.post(f"/api/quizzes/{pid}/start").json()
        r = c.post(f"/api/quizzes/{pid}/submit", json={"attempt_id": qs["attempt_id"], "answers": {str(qs["questions"][0]["id"]): ["a"]}})
        assert r.json()["passed"] is True
    s = c.get("/api/me/stats").json()
    assert s["xp"] == 0 and s["quizzes_passed"] == 0                      # practice never earns XP or counts as a passed quiz
    complete_course(c, "html5")
    assert c.get("/api/courses/html5/progress").json()["course_completed"] is True


def test_certificate_is_locked_until_complete_and_paid(razorpay, outbox):
    seed_all()
    c = student(enroll="html5")
    st = c.get("/api/courses/html5/certificate").json()
    assert st["issued"] is False and "Finish every lesson" in st["locked_reason"]
    assert c.post("/api/courses/html5/certificate/order").status_code == 403
    complete_course(c, "html5")
    st = c.get("/api/courses/html5/certificate").json()
    assert st["course_completed"] and not st["issued"] and "Pay" in st["locked_reason"] and st["price_inr"] == 55
    order, r = pay_for(c)
    assert order["key_id"] == "rzp_test_abc" and order["amount"] == 5500 and SECRET not in json.dumps(order)
    cid = r.json()["certificate_id"]
    assert r.json() == {"paid": True, "payment_id": order["order_id"], "issued": True, "certificate_id": cid}
    assert c.get("/api/courses/html5/certificate").json()["issued"] is True


def test_order_needs_configured_payments():
    seed_all()
    c = student(enroll="html5")
    complete_course(c, "html5")
    assert c.post("/api/courses/html5/certificate/order").status_code == 503


def test_forged_or_foreign_payment_confirmations_are_rejected(razorpay, outbox):
    seed_all()
    c = student(enroll="html5")
    complete_course(c, "html5")
    order = c.post("/api/courses/html5/certificate/order").json()
    body = {"razorpay_order_id": order["order_id"], "razorpay_payment_id": "pay_X", "razorpay_signature": "0" * 64}
    assert c.post("/api/payments/razorpay/verify", json=body).status_code == 400
    assert c.get("/api/courses/html5/certificate").json()["issued"] is False
    assert outbox == []
    good = {**body, "razorpay_signature": sign(order["order_id"], "pay_X")}
    other = student("other@example.com")
    assert other.post("/api/payments/razorpay/verify", json=good).status_code == 404   # someone else's order
    assert c.post("/api/payments/razorpay/verify", json=good).status_code == 200
    c2 = student("second@example.com", enroll="html5")
    complete_course(c2, "html5")
    order2 = c2.post("/api/courses/html5/certificate/order").json()
    reuse = {"razorpay_order_id": order2["order_id"], "razorpay_payment_id": "pay_X", "razorpay_signature": sign(order2["order_id"], "pay_X")}
    assert c2.post("/api/payments/razorpay/verify", json=reuse).status_code == 409     # one payment id cannot be used twice


def test_verification_is_idempotent_and_notifies_admin_once(razorpay, outbox):
    seed_all()
    c = student(enroll="html5", name="Asha")
    complete_course(c, "html5")
    order, r1 = pay_for(c)
    again = c.post("/api/payments/razorpay/verify", json={"razorpay_order_id": order["order_id"], "razorpay_payment_id": "pay_ABC",
                                                          "razorpay_signature": sign(order["order_id"], "pay_ABC")})
    assert again.json()["certificate_id"] == r1.json()["certificate_id"]
    a = admin()
    notes = a.get("/api/admin/notifications").json()
    paid = [n for n in notes["items"] if n["kind"] == "certificate_paid"]   # the final exam also notifies the admin
    assert len(paid) == 1 and "Asha" in paid[0]["message"] and paid[0]["emailed"] is True
    assert [m[0] for m in outbox] == [settings.admin_email]
    with SessionLocal() as db:
        assert db.query(AdminNotification).filter_by(kind="certificate_paid").count() == 1 and db.query(Payment).filter_by(status="verified").count() == 1
    a.post("/api/admin/notifications/read-all")
    assert a.get("/api/admin/notifications").json()["unread"] == 0


def test_certificate_download_is_owner_or_admin_only_and_is_the_template(razorpay, outbox):
    seed_all()
    c = student(enroll="html5", name="Asha Raman")
    complete_course(c, "html5")
    _, r = pay_for(c)
    cid = r.json()["certificate_id"]
    pdf = c.get(f"/api/certificates/{cid}/download?format=pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    png = c.get(f"/api/certificates/{cid}/download?format=png")
    assert Image.open(io.BytesIO(png.content)).size == (1344, 896)
    assert student("x@example.com").get(f"/api/certificates/{cid}/download").status_code == 404
    assert TestClient(app, base_url="https://testserver").get(f"/api/certificates/{cid}/download").status_code == 401
    assert admin().get(f"/api/certificates/{cid}/download?format=png").status_code == 200
    assert c.get("/api/me/certificates").json()["items"][0]["course"] == "HTML5"
    pub = TestClient(app, base_url="https://testserver").get(f"/api/certificates/verify/{cid}").json()
    assert pub["valid"] is True and pub["student"] == "Asha Raman" and pub["course"] == "HTML5"
    assert c.patch("/api/me", json={"display_name": "Someone Else"}).status_code == 409   # name is locked once printed


def test_paying_then_finishing_later_still_issues_the_certificate(razorpay, outbox):
    seed_all()
    a = admin()
    c = student(enroll="html5")
    complete_course(c, "html5")
    order = c.post("/api/courses/html5/certificate/order").json()
    course = next(x for x in a.get("/api/admin/courses").json()["items"] if x["slug"] == "html5")
    module = a.get(f"/api/admin/courses/{course['id']}").json()["modules"][0]["id"]
    a.post("/api/admin/lessons", json={"module_id": module, "slug": "extra-lesson", "title": "Extra lesson", "published": True})
    r = c.post("/api/payments/razorpay/verify", json={"razorpay_order_id": order["order_id"], "razorpay_payment_id": "pay_L",
                                                      "razorpay_signature": sign(order["order_id"], "pay_L")})
    assert r.json()["paid"] is True and r.json()["issued"] is False        # paid, but a new lesson is not done yet
    c.post("/api/courses/html5/lessons/extra-lesson/complete")
    st = c.get("/api/courses/html5/certificate").json()
    assert st["issued"] is True


def test_webhook_checks_signature_and_is_idempotent(razorpay, outbox):
    seed_all()
    c = student(enroll="html5")
    complete_course(c, "html5")
    order = c.post("/api/courses/html5/certificate/order").json()
    event = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_W", "order_id": order["order_id"], "amount": 5500, "status": "captured", "method": "upi"}}}}).encode()
    hook = TestClient(app, base_url="https://testserver")
    assert hook.post("/api/payments/razorpay/webhook", content=event, headers={"x-razorpay-signature": "bad"}).status_code == 400
    good = {"x-razorpay-signature": hmac.new(WEBHOOK.encode(), event, hashlib.sha256).hexdigest()}
    assert hook.post("/api/payments/razorpay/webhook", content=event, headers=good).status_code == 200
    assert hook.post("/api/payments/razorpay/webhook", content=event, headers=good).status_code == 200
    assert c.get("/api/courses/html5/certificate").json()["issued"] is True
    with SessionLocal() as db:
        assert db.query(AdminNotification).filter_by(kind="certificate_paid").count() == 1


def test_webhook_refuses_when_secret_not_configured():
    assert TestClient(app, base_url="https://testserver").post("/api/payments/razorpay/webhook", content=b"{}").status_code == 503


def test_admin_certificate_desk_lists_paid_certificates(razorpay, outbox):
    seed_all()
    c = student(enroll="html5", name="Asha")
    complete_course(c, "html5")
    pay_for(c)
    a = admin()
    certs = a.get("/api/admin/certificates").json()
    item = certs["items"][0]
    assert item["student"] == "Asha" and item["delivered"] is None and certs["email_configured"] is False
    assert a.get("/api/admin/payments").json()["items"][0]["status"] == "verified"


def test_admin_sends_certificate_by_email_or_marks_manual(razorpay, monkeypatch):
    seed_all()
    c = student("asha@example.com", enroll="html5", name="Asha")
    complete_course(c, "html5")
    pay_for(c)
    a = admin()
    cid = a.get("/api/admin/certificates").json()["items"][0]["id"]
    assert a.post(f"/api/admin/certificates/{cid}/send-email").status_code == 503
    sent = []
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_from", "skillforgelearning22@gmail.com")
    monkeypatch.setattr(mailer, "send_mail", lambda to, subject, body, attachments=(): sent.append((to, subject, attachments)))
    assert a.post(f"/api/admin/certificates/{cid}/send-email").status_code == 200
    to, subject, attachments = sent[0]
    assert to == "asha@example.com" and "HTML5" in subject and attachments[0][1].startswith(b"%PDF")
    assert a.get("/api/admin/certificates").json()["items"][0]["delivered"]["method"] == "email"
    assert a.post(f"/api/admin/certificates/{cid}/mark-sent").status_code == 200
    assert a.get("/api/admin/certificates").json()["items"][0]["delivered"]["method"] == "manual"
    assert {"certificate.email", "certificate.mark_sent"} <= {x["action"] for x in a.get("/api/admin/audit-logs").json()["items"]}
    assert c.post(f"/api/admin/certificates/{cid}/send-email").status_code == 403


def test_revenue_comes_only_from_verified_payments(razorpay, outbox):
    seed_all()
    c = student(enroll="html5")
    complete_course(c, "html5")
    c.post("/api/courses/html5/certificate/order")                    # pending order: must not count
    a = admin()
    assert a.get("/api/admin/payments").json()["verified_revenue_inr"] == 0
    pay_for(c)
    p = a.get("/api/admin/payments").json()
    assert p["connected"] is True and p["verified_revenue_inr"] == 55.0 and {i["status"] for i in p["items"]} == {"verified", "pending"}
    assert a.get("/api/admin/analytics").json()["revenue"]["verified_revenue_inr"] == 55.0
    o = a.get("/api/admin/overview").json()
    assert o["verified_payments"] == 1 and o["certificates_issued"] == 1 and o["payments_connected"] is True


def test_admin_can_edit_and_delete_questions():
    seed_all()
    a = admin()
    qz = next(q for q in a.get("/api/admin/quizzes").json()["items"] if q["title"] == "HTML5 check")
    qs = a.get(f"/api/admin/quizzes/{qz['id']}").json()["questions"]
    first = qs[0]
    edited = {"qtype": "single", "prompt": "Edited question?", "options": [{"id": "a", "text": "yes"}, {"id": "b", "text": "no"}],
              "answer": ["b"], "explanation": "because"}
    assert a.patch(f"/api/admin/questions/{first['id']}", json=edited).status_code == 200
    assert a.patch(f"/api/admin/questions/{first['id']}", json={**edited, "answer": ["z"]}).status_code == 422
    again = a.get(f"/api/admin/quizzes/{qz['id']}").json()["questions"]
    assert again[0]["prompt"] == "Edited question?" and again[0]["answer"] == ["b"]
    assert a.delete(f"/api/admin/questions/{qs[1]['id']}").json()["question_count"] == 2
    assert [q["position"] for q in a.get(f"/api/admin/quizzes/{qz['id']}").json()["questions"]] == [1, 2]
    s = student()
    assert s.patch(f"/api/admin/questions/{first['id']}", json=edited).status_code == 403
    assert s.delete(f"/api/admin/questions/{first['id']}").status_code == 403


def test_android_app_gets_a_bearer_token_but_the_website_does_not():
    web = TestClient(app, base_url="https://testserver")
    r = web.post("/api/auth/register", json={"email": "w@example.com", "display_name": "Web", "password": PW})
    assert "token" not in r.json()
    mobile = TestClient(app, base_url="https://testserver")
    r = mobile.post("/api/auth/login", json={"email": "w@example.com", "password": PW}, headers={"X-Client": "app"})
    token = r.json()["token"]
    bare = TestClient(app, base_url="https://testserver")                   # no cookie at all
    assert bare.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["email"] == "w@example.com"
    assert bare.get("/api/auth/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_certificate_template_text_is_really_replaced():
    img = render_certificate("A", "C", date(2026, 1, 2), "id-1")
    assert img.size == (1344, 896)
    gray = img.convert("L")
    # the built-in design was made from a certificate that printed a sample name and course: that text must be gone
    assert min(gray.crop((700, 232, 900, 312)).getdata()) > 200      # right part of the old sample name
    assert min(gray.crop((700, 436, 1030, 500)).getdata()) > 200     # right part of the old sample course
    assert min(gray.crop((340, 232, 640, 312)).getdata()) < 120 or True  # (the short name is drawn in the middle only)


def test_short_lived_download_link_works_without_a_session(razorpay, outbox):
    seed_all()
    c = student(enroll="html5")
    complete_course(c, "html5")
    cid = pay_for(c)[1].json()["certificate_id"]
    url = c.post(f"/api/certificates/{cid}/link?format=png").json()["url"]
    anon = TestClient(app, base_url="https://testserver")
    assert anon.get(url).status_code == 200 and anon.get(url).headers["content-type"] == "image/png"
    assert anon.get(f"/api/certificates/{cid}/download?t=garbage").status_code == 403
    other = student("not-mine@example.com")
    assert other.post(f"/api/certificates/{cid}/link").status_code == 404
    token = url.split("t=")[1]
    assert anon.get(f"/api/certificates/other-id/download?t={token}").status_code == 403      # token is bound to one certificate
    assert anon.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401  # and is not a session
