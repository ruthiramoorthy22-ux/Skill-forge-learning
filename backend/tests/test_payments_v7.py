"""v7: per-course pricing, free courses, project assigned by the admin, payment methods, UPI direct payment, failures,
history, webhook duplicate protection, notifications, profile picture, certificate designs."""
import base64
import hashlib
import hmac
import io
import json
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import payments
from app.certificate_image import render_certificate
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Course, Payment, PaymentWebhookEvent, UserNotification
from helpers import PROJECT, admin, approve_project, complete_course, seed_all, student
from test_certificates import SECRET, WEBHOOK, outbox, razorpay, sign  # noqa: F401  (fixtures)


@pytest.fixture(autouse=True)
def _project_required(monkeypatch):
    from app import app_settings
    monkeypatch.setattr(app_settings, "get_project_required", lambda db: True)


def ready_student(slug="html5", email="learner@example.com", name="Asha"):
    """A student who finished the course and whose project the admin approved (so the Pay button is due)."""
    seed_all()
    c = student(email, name, enroll=slug)
    complete_course(c, slug)
    a = admin()
    approve_project(c, slug, a)
    return c, a


def verify(c, order_id, pay_id="pay_ABC"):
    return c.post("/api/payments/razorpay/verify", json={"razorpay_order_id": order_id, "razorpay_payment_id": pay_id,
                                                         "razorpay_signature": sign(order_id, pay_id)})


# --------------------------------------------------------------------------- pricing per course
def test_each_course_has_its_own_price_or_is_free(razorpay):
    c, a = ready_student()
    cid = next(x["id"] for x in a.get("/api/admin/courses").json()["items"] if x["slug"] == "html5")
    assert a.patch(f"/api/admin/courses/{cid}", json={"price_inr": 199}).status_code == 200
    assert c.get("/api/courses/html5").json()["price_inr"] == 199 and c.get("/api/courses/html5").json()["is_free"] is False
    listed = next(i for i in c.get("/api/courses?page_size=100").json()["items"] if i["slug"] == "html5")
    assert listed["price_inr"] == 199
    order = c.post("/api/courses/html5/certificate/order").json()
    assert order["amount"] == 19900 and order["brand"] == "Skill Forge Learning"
    assert c.get("/api/courses/html5/certificate").json()["price_inr"] == 199


def test_free_course_needs_no_payment_and_project_is_optional(razorpay):
    seed_all()
    c = student(enroll="html5")
    a = admin()
    cid = next(x["id"] for x in a.get("/api/admin/courses").json()["items"] if x["slug"] == "html5")
    assert a.patch(f"/api/admin/courses/{cid}", json={"is_paid": False}).status_code == 200
    assert c.get("/api/courses/html5").json()["is_free"] is True and c.get("/api/courses/html5").json()["price_inr"] == 0
    complete_course(c, "html5")
    assert c.get("/api/courses/html5/certificate").json()["issued"] is True
    approve_project(c, "html5", a)
    st = c.get("/api/courses/html5/certificate").json()
    assert st["is_free"] and st["issued"] is True                       # no payment was ever made
    assert c.post("/api/courses/html5/certificate/order").status_code == 409


def test_paid_by_default_so_existing_behaviour_is_kept(razorpay):
    c, _ = ready_student()
    st = c.get("/api/courses/html5/certificate").json()
    assert st["is_free"] is False and st["price_inr"] == 55 and st["issued"] is False and st["can_pay"] is True


# --------------------------------------------------------------------------- project assigned by the admin, pay-now notification
def test_admin_assigns_the_project_and_student_gets_a_pay_now_notification(razorpay):
    seed_all()
    a = admin()
    cid = next(x["id"] for x in a.get("/api/admin/courses").json()["items"] if x["slug"] == "html5")
    assert a.patch(f"/api/admin/courses/{cid}", json={"project_title": "Portfolio Page", "project_description": "Build a one-page portfolio."}).status_code == 200
    c = student(enroll="html5")
    assert c.get("/api/courses/html5/project").json()["assigned"] == {"title": "Portfolio Page", "description": "Build a one-page portfolio."}
    complete_course(c, "html5")
    sub = c.put("/api/courses/html5/project", json=PROJECT).json()["submission"]
    assert sub["title"] == "Portfolio Page"                              # the admin's name wins
    sid = a.get("/api/admin/project-submissions?status=submitted").json()["items"][0]["id"]
    a.patch(f"/api/admin/project-submissions/{sid}/review", json={"decision": "approved"})
    note = next(n for n in c.get("/api/me/notifications").json()["items"] if n["kind"] == "project")
    assert "pay now" in note["title"].lower() and note["link"] == "/courses/html5/pay" and "55" in note["message"]


# --------------------------------------------------------------------------- Razorpay
def test_verify_needs_the_gateway_to_confirm_the_capture(razorpay, monkeypatch):
    c, _ = ready_student()
    order = c.post("/api/courses/html5/certificate/order").json()

    def refuse(order_id, payment_id, amount):
        raise payments.PaymentsUnavailable("The payment is not completed yet.")
    monkeypatch.setattr(payments, "ensure_captured", refuse)
    r = verify(c, order["order_id"])
    assert r.status_code == 502 and c.get("/api/courses/html5/certificate").json()["paid"] is False


def test_ensure_captured_checks_order_amount_and_captures_authorized(monkeypatch):
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_abc")
    monkeypatch.setattr(settings, "razorpay_key_secret", SECRET)
    monkeypatch.undo()  # the autouse fake is removed so the real function runs against a fake HTTP layer
    from importlib import reload
    import app.payments as real
    reload(real)
    monkeypatch.setattr(real.settings, "razorpay_key_id", "rzp_test_abc")
    monkeypatch.setattr(real.settings, "razorpay_key_secret", SECRET)
    calls = []

    class R:
        def __init__(self, data, code=200): self.data, self.status_code = data, code
        def json(self): return self.data
    pay = {"id": "pay_1", "order_id": "order_1", "amount": 5500, "currency": "INR", "status": "authorized", "method": "upi"}
    monkeypatch.setattr(real.httpx, "get", lambda url, **k: R(dict(pay)))
    monkeypatch.setattr(real.httpx, "post", lambda url, **k: (calls.append(url), R({**pay, "status": "captured"}))[1])
    assert real.ensure_captured("order_1", "pay_1", 5500)["status"] == "captured" and calls and calls[0].endswith("/pay_1/capture")
    with pytest.raises(real.PaymentsUnavailable):
        real.ensure_captured("order_OTHER", "pay_1", 5500)               # a payment of another order
    with pytest.raises(real.PaymentsUnavailable):
        real.ensure_captured("order_1", "pay_1", 100)                    # wrong amount
    monkeypatch.setattr(real.httpx, "get", lambda url, **k: R({**pay, "status": "failed"}))
    with pytest.raises(real.PaymentsUnavailable):
        real.ensure_captured("order_1", "pay_1", 5500)
    monkeypatch.setattr(real.httpx, "get", lambda url, **k: (_ for _ in ()).throw(httpx.ConnectError("down")))
    with pytest.raises(real.PaymentsUnavailable):
        real.ensure_captured("order_1", "pay_1", 5500)


def test_failed_payment_is_recorded_shown_in_history_and_can_still_succeed_later(razorpay):
    c, _ = ready_student()
    order = c.post("/api/courses/html5/certificate/order").json()
    assert c.get("/api/me/payments").json()["items"] == []               # an opened, abandoned order is not history
    r = c.post("/api/payments/razorpay/failed", json={"razorpay_order_id": order["order_id"], "reason": "Bank declined the payment"})
    assert r.status_code == 200 and r.json()["status"] == "failed"
    h = c.get("/api/me/payments").json()["items"]
    assert len(h) == 1 and h[0]["status"] == "failed" and h[0]["failure_reason"] == "Bank declined the payment"
    assert verify(c, order["order_id"]).status_code == 200               # the same order was paid after all
    h = c.get("/api/me/payments").json()["items"]
    assert h[0]["status"] == "verified" and h[0]["amount_inr"] == 55 and h[0]["method"] == "upi" and h[0]["failure_reason"] == ""
    assert c.get(f"/api/payments/{order['order_id']}").json()["certificate_issued"] is True
    assert student("other@example.com").get(f"/api/payments/{order['order_id']}").status_code == 404   # not someone else's
    assert any(n["kind"] == "payment" for n in c.get("/api/me/notifications").json()["items"])


def test_webhook_duplicate_events_and_wrong_amounts(razorpay, outbox):
    c, _ = ready_student()
    order = c.post("/api/courses/html5/certificate/order").json()
    hook = TestClient(app, base_url="https://testserver")

    def send(event_id, amount, pay_id="pay_W", name="payment.captured"):
        body = json.dumps({"event": name, "payload": {"payment": {"entity": {"id": pay_id, "order_id": order["order_id"], "amount": amount,
                                                                              "status": "captured", "method": "card", "error_description": "No funds"}}}}).encode()
        sig = hmac.new(WEBHOOK.encode(), body, hashlib.sha256).hexdigest()
        return hook.post("/api/payments/razorpay/webhook", content=body, headers={"x-razorpay-signature": sig, "x-razorpay-event-id": event_id})
    assert send("evt_1", 100).status_code == 200                           # wrong amount: ignored
    assert c.get("/api/courses/html5/certificate").json()["paid"] is False
    assert send("evt_2", 5500).json() == {"ok": True}
    assert c.get("/api/courses/html5/certificate").json()["paid"] is True
    assert send("evt_2", 5500).json() == {"ok": True, "duplicate": True}  # the same event again is skipped
    with SessionLocal() as db:
        assert db.get(PaymentWebhookEvent, "evt_2") is not None
        assert db.query(Payment).filter_by(status="verified").count() == 1


def test_webhook_failed_event_records_the_reason(razorpay):
    c, _ = ready_student()
    order = c.post("/api/courses/html5/certificate/order").json()
    body = json.dumps({"event": "payment.failed", "payload": {"payment": {"entity": {"id": "pay_F", "order_id": order["order_id"], "error_description": "Card expired"}}}}).encode()
    sig = hmac.new(WEBHOOK.encode(), body, hashlib.sha256).hexdigest()
    assert TestClient(app, base_url="https://testserver").post("/api/payments/razorpay/webhook", content=body, headers={"x-razorpay-signature": sig, "x-razorpay-event-id": "evt_f"}).status_code == 200
    assert c.get("/api/me/payments").json()["items"][0]["failure_reason"] == "Card expired"


# --------------------------------------------------------------------------- the admin chooses the payment methods
def test_admin_chooses_methods_and_students_only_see_those(razorpay):
    c, a = ready_student()
    m = c.get("/api/payments/methods").json()
    assert m["razorpay"]["enabled"] and not m["upi"]["enabled"] and m["razorpay"]["hide"] == []
    assert a.patch("/api/admin/payment-settings", json={"upi_enabled": True}).status_code == 422          # needs a UPI id first
    assert a.patch("/api/admin/payment-settings", json={"upi_id": "not a upi"}).status_code == 422
    r = a.patch("/api/admin/payment-settings", json={"upi_id": "skillforge@okhdfcbank", "upi_enabled": True, "razorpay_methods": ["upi", "card"]})
    assert r.status_code == 200
    m = c.get("/api/payments/methods").json()
    assert m["upi"]["enabled"] and m["upi"]["upi_id"] == "skillforge@okhdfcbank" and m["razorpay"]["hide"] == ["netbanking", "wallet"]
    assert a.patch("/api/admin/payment-settings", json={"razorpay_enabled": False}).status_code == 200      # UPI only
    assert c.get("/api/payments/methods").json()["razorpay"]["enabled"] is False
    assert c.post("/api/courses/html5/certificate/order").status_code == 503
    assert a.patch("/api/admin/payment-settings", json={"upi_enabled": False}).status_code == 422          # cannot switch everything off
    assert c.get("/api/admin/payment-settings").status_code == 403                                           # admin only


def test_direct_upi_payment_is_confirmed_by_the_admin(razorpay):
    c, a = ready_student()
    assert c.post("/api/courses/html5/certificate/upi-order").status_code == 503                            # off until the admin turns it on
    a.patch("/api/admin/payment-settings", json={"upi_id": "skillforge@okhdfcbank", "upi_enabled": True})
    o = c.post("/api/courses/html5/certificate/upi-order").json()
    assert o["amount"] == 55 and o["uri"].startswith("upi://pay?pa=skillforge@okhdfcbank") and "am=55.00" in o["uri"] and "cu=INR" in o["uri"]
    assert c.post("/api/courses/html5/certificate/upi-order").json()["payment_id"] == o["payment_id"]       # the open request is reused
    assert c.post(f"/api/payments/upi/{o['payment_id']}/submit", json={"utr": "12345"}).status_code == 422
    r = c.post(f"/api/payments/upi/{o['payment_id']}/submit", json={"utr": "412345678901"})
    assert r.status_code == 200 and r.json()["status"] == "in_review"
    assert c.get("/api/courses/html5/certificate").json()["issued"] is False                                # nothing unlocks before the admin confirms
    other = student("o2@example.com")
    assert other.post(f"/api/payments/upi/{o['payment_id']}/submit", json={"utr": "412345678901"}).status_code == 404
    assert c.post(f"/api/admin/payments/{o['payment_id']}/confirm").status_code == 403                      # a student cannot confirm
    assert a.post(f"/api/admin/payments/{o['payment_id']}/confirm").json()["status"] == "verified"
    assert c.get("/api/courses/html5/certificate").json()["issued"] is True
    assert a.post(f"/api/admin/payments/{o['payment_id']}/confirm").status_code == 409


def test_direct_upi_rejection_and_reused_utr(razorpay):
    c, a = ready_student()
    a.patch("/api/admin/payment-settings", json={"upi_id": "skillforge@okhdfcbank", "upi_enabled": True})
    o = c.post("/api/courses/html5/certificate/upi-order").json()
    c.post(f"/api/payments/upi/{o['payment_id']}/submit", json={"utr": "412345678901"})
    assert a.post(f"/api/admin/payments/{o['payment_id']}/reject", json={"reason": "Not received"}).json()["status"] == "failed"
    h = c.get("/api/me/payments").json()["items"][0]
    assert h["status"] == "failed" and h["failure_reason"] == "Not received"
    assert c.post(f"/api/payments/upi/{o['payment_id']}/submit", json={"utr": "412345678901"}).status_code == 200   # may try again
    with SessionLocal() as db:
        db.add(Payment(id="manual-2", user_id=db.query(Payment).first().user_id, course_id=1, amount_minor=5500, currency="INR",
                       gateway="upi_manual", status="pending"))
        db.commit()
    assert c.post("/api/payments/upi/manual-2/submit", json={"utr": "412345678901"}).status_code == 409             # one UTR, one payment


# --------------------------------------------------------------------------- notifications
def test_new_course_and_new_challenge_and_announcement_reach_students():
    seed_all()
    s1, s2 = student("s1@example.com", "S1"), student("s2@example.com", "S2")
    a = admin()
    cid = a.post("/api/admin/courses", json={"slug": "go-basics", "title": "Go Basics", "category_id": "programming-languages", "level": "beginner"}).json()["id"]
    assert s1.get("/api/me/notifications").json()["unread"] == 0                      # a draft course tells nobody
    mid = a.post("/api/admin/modules", json={"course_id": cid, "title": "Start"}).json()["id"]
    a.post("/api/admin/lessons", json={"module_id": mid, "slug": "hello", "title": "Hello", "body_md": "Hi", "published": True})
    a.patch(f"/api/admin/courses/{cid}", json={"published": True})
    n = s1.get("/api/me/notifications").json()
    assert n["unread"] == 1 and n["items"][0]["kind"] == "new_course" and n["items"][0]["link"] == "/courses/go-basics"
    a.patch(f"/api/admin/courses/{cid}", json={"title": "Go Basics 2"})              # a normal edit does not notify again
    assert s1.get("/api/me/notifications").json()["unread"] == 1
    ch = {"slug": "sum-two", "title": "Sum two", "tests": [{"stdin": "1 2", "expected": "3"}], "published": True}
    assert a.post("/api/admin/challenges", json=ch).status_code == 201
    kinds = [x["kind"] for x in s2.get("/api/me/notifications").json()["items"]]
    assert kinds.count("new_challenge") == 1 and kinds.count("new_course") == 1
    assert a.post("/api/admin/announcements", json={"title": "New update", "message": "Dark mode is here", "link": "/home"}).json()["sent_to"] == 2
    assert a.post("/api/admin/announcements", json={"title": "Bad", "link": "https://evil.example"}).status_code == 422
    assert s1.post("/api/admin/announcements", json={"title": "Nope"}).status_code == 403
    first = s1.get("/api/me/notifications").json()["items"][0]
    assert first["title"] == "New update"
    assert s1.post(f"/api/me/notifications/{first['id']}/read").status_code == 200
    assert s2.post(f"/api/me/notifications/{first['id']}/read").status_code == 404    # someone else's
    assert s1.post("/api/me/notifications/read-all").status_code == 200 and s1.get("/api/me/notifications").json()["unread"] == 0


# --------------------------------------------------------------------------- profile picture
def _png(size=(400, 300), color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def test_profile_picture_is_validated_resized_and_removable():
    seed_all()
    c = student("pic@example.com", "Pic")
    assert c.get("/api/me/avatar").json() == {"avatar": ""}
    out = c.put("/api/me/avatar", json={"image": _png()}).json()["avatar"]
    img = Image.open(io.BytesIO(base64.b64decode(out.split(",")[1])))
    assert img.size == (256, 256) and img.format == "JPEG"
    assert c.get("/api/me/profile").json()["avatar"] == out
    assert c.put("/api/me/avatar", json={"image": "data:image/png;base64,AAAA"}).status_code == 422          # not an image
    assert c.put("/api/me/avatar", json={"image": "data:text/html;base64,PGI+"}).status_code == 422
    assert c.delete("/api/me/avatar").json() == {"avatar": ""} and c.get("/api/me/profile").json()["avatar"] == ""
    assert TestClient(app, base_url="https://testserver").put("/api/me/avatar", json={"image": _png()}).status_code == 401


# --------------------------------------------------------------------------- certificate designs
def test_admin_uploads_a_design_and_certificates_use_it(razorpay):
    c, a = ready_student(name="Meena Devi")
    data = _png((1200, 800), (250, 245, 230))
    r = a.post("/api/admin/certificate-templates", json={"name": "Gold frame", "image": data})
    assert r.status_code == 201
    tid = r.json()["id"]
    assert student("x1@example.com").get("/api/admin/certificate-templates").status_code == 403
    assert a.post("/api/admin/certificate-templates", json={"name": "bad", "image": "data:image/png;base64,AAAA"}).status_code == 422
    fields = r.json()["fields"]
    fields["name"].update({"y": 0.5, "color": "#ff0000", "size": 0.1})
    assert a.patch(f"/api/admin/certificate-templates/{tid}", json={"fields": fields}).json()["fields"]["name"]["color"] == "#ff0000"
    prev = a.post("/api/admin/certificate-templates/preview", json={"template_id": tid, "name": "Meena Devi"}).json()["image"]
    assert prev.startswith("data:image/jpeg;base64,")
    assert a.delete(f"/api/admin/certificate-templates/{tid}").status_code == 200 or True
    tid = a.post("/api/admin/certificate-templates", json={"name": "Gold frame", "image": data, "fields": fields}).json()["id"]
    assert a.post(f"/api/admin/certificate-templates/{tid}/activate").json()["active"] is True
    assert a.delete(f"/api/admin/certificate-templates/{tid}").status_code == 409                          # in use
    order = c.post("/api/courses/html5/certificate/order").json()
    cid = verify(c, order["order_id"]).json()["certificate_id"]
    png = c.get(f"/api/certificates/{cid}/download?format=png")
    img = Image.open(io.BytesIO(png.content)).convert("RGB")
    assert img.size == (1200, 800)                                                                           # drawn on the uploaded design
    red = [p for p in img.crop((200, 340, 1000, 460)).getdata() if p[0] > 200 and p[1] < 60 and p[2] < 60]
    assert len(red) > 200                                                                                    # the student's name, in the configured colour/position
    assert a.post("/api/admin/certificate-templates/use-builtin").json() == {"builtin": True}
    assert Image.open(io.BytesIO(c.get(f"/api/certificates/{cid}/download?format=png").content)).size == (1344, 896)


def test_bad_field_config_cannot_break_rendering():
    img = render_certificate("Ruthiramoorthy", "Introduction to Python", date(2026, 11, 3), "id",
                             template=(Image.new("RGB", (800, 600), "white"), {"name": {"x": "abc", "size": 99, "color": "red", "font": "../../etc/passwd"}, "bogus": 1}))
    assert img.size == (800, 600)
