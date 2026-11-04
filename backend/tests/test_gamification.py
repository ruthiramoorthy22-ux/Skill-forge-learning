from datetime import date, timedelta

from app.db import SessionLocal
from app.gamification import streak_from_days
from app.models import XPEvent
from helpers import admin, seed_all, student

T = date(2026, 10, 30)


def test_streak_rules():
    assert streak_from_days({T, T - timedelta(1), T - timedelta(2)}, T) == 3
    assert streak_from_days({T - timedelta(1)}, T) == 1           # yesterday still counts until today ends
    assert streak_from_days({T - timedelta(2)}, T) == 0
    assert streak_from_days({T, T - timedelta(2)}, T) == 1


def test_lesson_xp_stats_and_achievement_are_server_side_and_not_farmable():
    seed_all()
    c = student(enroll="python")
    first = c.post("/api/courses/python/lessons/first-program/complete").json()
    assert "first_lesson" in first["new_achievements"]
    c.post("/api/courses/python/lessons/first-program/complete")
    s = c.get("/api/me/stats").json()
    assert s["xp"] == 10 and s["lessons"] == 1 and s["streak"] == 1 and s["today_lessons"] == 1
    assert [a["earned"] for a in s["achievements"] if a["code"] == "first_lesson"] == [True]
    assert s["recent_activity"][0]["kind"] == "lesson_complete"
    with SessionLocal() as db:
        assert db.query(XPEvent).count() == 1


def test_leaderboard_is_opt_in_and_shows_no_email():
    seed_all()
    c = student(name="Asha", enroll="python")
    c.post("/api/courses/python/lessons/loops/complete")
    assert c.get("/api/leaderboard").json()["items"] == []
    c.patch("/api/me/privacy", json={"show_on_leaderboard": True})
    items = c.get("/api/leaderboard").json()["items"]
    assert items == [{"display_name": "Asha", "xp": 10}]


def test_recommendations_follow_progress():
    seed_all()
    c = student()
    assert {i["course_slug"] for i in c.get("/api/me/recommendations").json()["items"]} == {"python", "html5", "css3"}
    c.post("/api/courses/python/enroll")
    first = c.get("/api/me/recommendations").json()["items"][0]
    assert first["type"] == "lesson" and first["lesson_slug"] == "first-program"


def test_heartbeat_requires_login_and_drives_admin_online_view(client):
    assert client.post("/api/activity/heartbeat").status_code == 401
    c = student(name="Online One")
    c.post("/api/activity/heartbeat")
    a = admin()
    live = a.get("/api/admin/live").json()
    assert [o["display_name"] for o in live["online"]] == ["Online One"]
    assert a.get("/api/admin/overview").json()["online_now"] == 1
