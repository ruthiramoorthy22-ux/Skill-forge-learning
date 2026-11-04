from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_reports_unconfigured_services():
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert body["code_execution"] == "not_connected"


def test_categories_cover_twelve_groups_plus_additional_paths():
    assert len(client.get("/api/categories").json()["items"]) == 13


def test_course_slugs_are_unique():
    items = client.get("/api/courses?page_size=100").json()["items"]
    total = client.get("/api/courses").json()["total"]
    all_items = []
    for p in range(1, (total // 100) + 2):
        all_items += client.get(f"/api/courses?page_size=100&page={p}").json()["items"]
    slugs = [c["slug"] for c in all_items]
    assert len(slugs) == len(set(slugs)) == total
    assert items


def test_filters_and_search():
    r = client.get("/api/courses?category=cybersecurity&level=beginner").json()
    assert r["total"] > 0
    assert all(c["category_id"] == "cybersecurity" and c["level"] == "beginner" for c in r["items"])
    assert any(c["title"] == "Python" for c in client.get("/api/courses?q=pyth").json()["items"])


def test_no_course_claims_to_be_available_yet():
    assert client.get("/api/courses?status=available").json()["total"] == 0


def test_validation_errors():
    assert client.get("/api/courses?page_size=1000").status_code == 422
    assert client.get("/api/courses?level=expert").status_code == 422


def test_unknown_course_404():
    assert client.get("/api/courses/does-not-exist").status_code == 404
