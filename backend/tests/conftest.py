import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-secret-" + "x" * 40
os.environ["APP_ENV"] = "test"
os.environ.pop("JUDGE0_URL", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.ratelimit import auth_limiter  # noqa: E402
from app.routes_me import heartbeat_limiter  # noqa: E402
from app.routes_quiz import run_limiter, submit_limiter  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    for lim in (auth_limiter, heartbeat_limiter, run_limiter, submit_limiter):
        lim.hits.clear()
    yield


@pytest.fixture
def client():
    return TestClient(app, base_url="https://testserver")


@pytest.fixture(autouse=True)
def _project_gate_off_for_payment_mechanics(request, monkeypatch):
    """test_certificates.py tests payment/delivery mechanics, so the project requirement is switched off there.
    test_admin_controls.py and test_project_flow.py run with the real requirement."""
    from app import app_settings
    # The project requirement is off by default now; those two modules still test it, so it is switched on there.
    if request.module.__name__ in ("test_admin_controls", "test_project_flow") and request.node.name != "test_project_requirement_can_be_switched_off":
        monkeypatch.setattr(app_settings, "get_project_required", lambda db: True)
    elif request.module.__name__ == "test_certificates":
        monkeypatch.setattr(app_settings, "get_project_required", lambda db: False)


@pytest.fixture(autouse=True)
def _gateway_capture_check_is_not_called(monkeypatch):
    """The real check asks api.razorpay.com whether the payment was captured; tests replace it (test_payments_v7.py tests it with a fake HTTP)."""
    from app import payments
    monkeypatch.setattr(payments, "ensure_captured", lambda order_id, payment_id, amount: {"method": "upi", "status": "captured"})
