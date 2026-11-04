from app.config import settings
from app.create_admin import create_admin
from app.db import SessionLocal
from app.models import User

GOOD = {"email": "asha@example.com", "display_name": "Asha", "password": "correct-horse-battery"}
ADMIN_PW = "a-very-long-admin-pass"


def register(client, **over):
    return client.post("/api/auth/register", json={**GOOD, **over})


def make_admin():
    with SessionLocal() as db:
        create_admin(db, settings.admin_email, ADMIN_PW)


def test_register_signs_in_and_hides_secrets(client):
    r = register(client)
    assert r.status_code == 201
    assert "password" not in r.text
    me = client.get("/api/auth/me").json()
    assert me["email"] == "asha@example.com" and me["role"] == "student"


def test_passwords_are_stored_hashed(client):
    register(client)
    with SessionLocal() as db:
        u = db.query(User).one()
        assert u.password_hash != GOOD["password"] and u.password_hash.startswith("$argon2")


def test_duplicate_email_rejected(client):
    register(client)
    assert register(client, email="ASHA@example.com").status_code == 409


def test_weak_password_and_bad_email_rejected(client):
    assert register(client, password="short").status_code == 422
    assert register(client, email="not-an-email").status_code == 422


def test_admin_email_cannot_be_registered(client):
    assert register(client, email=settings.admin_email).status_code == 400


def test_login_logout_flow(client):
    register(client)
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    bad = client.post("/api/auth/login", json={"email": GOOD["email"], "password": "wrong-password"})
    assert bad.status_code == 401
    ok = client.post("/api/auth/login", json={"email": GOOD["email"], "password": GOOD["password"]})
    assert ok.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_unknown_email_gets_same_error(client):
    r = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever-pass"})
    assert r.status_code == 401 and r.json()["detail"] == "Incorrect email or password."


def test_me_requires_login_and_rejects_forged_cookie(client):
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.set("__session", "garbage")
    assert client.get("/api/auth/me").status_code == 401


def test_student_cannot_reach_admin_api(client):
    assert client.get("/api/admin/overview").status_code == 401
    register(client)
    assert client.get("/api/admin/overview").status_code == 403


def test_student_cannot_self_promote(client):
    register(client)
    r = client.patch("/api/me", json={"display_name": "Hacker", "role": "admin"})
    assert r.status_code == 200 and r.json()["role"] == "student"
    assert client.get("/api/admin/overview").status_code == 403


def test_student_admin_login_denied_without_session(client):
    register(client)
    client.post("/api/auth/logout")
    r = client.post("/api/auth/admin/login", json={"email": GOOD["email"], "password": GOOD["password"]})
    assert r.status_code == 403
    assert client.get("/api/auth/me").status_code == 401


def test_provisioned_admin_can_sign_in_and_see_real_counts(client):
    make_admin()
    register(client)
    client.post("/api/auth/logout")
    r = client.post("/api/auth/admin/login", json={"email": settings.admin_email, "password": ADMIN_PW})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert client.get("/api/admin/overview").json()["total_students"] == 1


def test_short_admin_password_refused():
    import pytest
    with SessionLocal() as db, pytest.raises(ValueError):
        create_admin(db, settings.admin_email, "short")


def test_disabled_account_cannot_sign_in(client):
    register(client)
    client.post("/api/auth/logout")
    with SessionLocal() as db:
        db.query(User).one().status = "disabled"
        db.commit()
    r = client.post("/api/auth/login", json={"email": GOOD["email"], "password": GOOD["password"]})
    assert r.status_code == 403


def test_login_rate_limit(client):
    codes = [client.post("/api/auth/login", json={"email": "x@example.com", "password": "bad-pass-1"}).status_code
             for _ in range(12)]
    assert 429 in codes
