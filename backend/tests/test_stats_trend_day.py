import datetime
from datetime import timezone

import models
from database import SessionLocal


def _owner_id(client, headers):
    return client.get("/api/auth/me", headers=headers).json()["id"]


def _add_focus_session(client, headers, start, end, mission_id=None, habit_id=None):
    owner_id = _owner_id(client, headers)
    db = SessionLocal()
    try:
        session = models.BatFocus(
            start_time=start,
            end_time=end,
            duration_minutes=int((end - start).total_seconds() / 60),
            mission_id=mission_id,
            habit_id=habit_id,
            owner_id=owner_id,
        )
        db.add(session)
        db.commit()
    finally:
        db.close()


def test_trend_zero_sessions_still_has_buckets(client, headers):
    r = client.get("/api/stats/focus/trend?granularity=day", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["granularity"] == "day"
    assert len(data["points"]) == 7
    assert all(p["minutes"] == 0 and p["sessions"] == 0 for p in data["points"])
    labels = [p["label"] for p in data["points"]]
    assert labels[-1] == datetime.datetime.now(timezone.utc).strftime("%a")

    week = client.get("/api/stats/focus/trend?granularity=week", headers=headers).json()
    assert len(week["points"]) == 8

    month = client.get("/api/stats/focus/trend?granularity=month", headers=headers).json()
    assert len(month["points"]) == 6


def test_trend_aggregates_into_correct_buckets(client, headers):
    now = datetime.datetime.now(timezone.utc)
    # Today: one session, 45 min.
    _add_focus_session(client, headers, now - datetime.timedelta(minutes=45), now)
    # Two days ago: one session, 20 min.
    two_days_ago = now - datetime.timedelta(days=2)
    _add_focus_session(
        client, headers,
        two_days_ago - datetime.timedelta(minutes=20), two_days_ago,
    )

    data = client.get("/api/stats/focus/trend?granularity=day", headers=headers).json()
    points = data["points"]
    assert points[-1]["minutes"] == 45
    assert points[-1]["sessions"] == 1
    assert points[-3]["minutes"] == 20
    assert points[-3]["sessions"] == 1
    # Buckets in between stay at zero (never skipped).
    assert points[-2]["minutes"] == 0

    month = client.get("/api/stats/focus/trend?granularity=month", headers=headers).json()
    assert month["points"][-1]["sessions"] == 2


def test_day_empty_date(client, headers):
    day = "2030-01-01"
    r = client.get(f"/api/stats/day?day={day}", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["date"] == day
    assert data["completed_count"] == 0
    assert data["total_count"] == 0
    assert data["completion_rate"] == 0.0
    assert data["status_distribution"] == {"on_time": 0, "overdue": 0, "uncompleted": 0}
    assert data["type_distribution"] == []
    assert data["tag_distribution"] == []


def test_day_mixed_completed_overdue_uncompleted(client, headers):
    # UTC date: the API interprets ?day= bounds in UTC (the storage timezone),
    # so the test must use the UTC date, not the server-local date.
    today = datetime.datetime.now(timezone.utc).date()
    past = today - datetime.timedelta(days=10)
    future = today + datetime.timedelta(days=10)

    on_time = client.post("/api/missions", headers=headers, json={
        "title": "Done on time", "due_date": today.isoformat(), "tags": "phantom-1, stealth",
    }).json()
    late = client.post("/api/missions", headers=headers, json={
        "title": "Done late", "due_date": past.isoformat(), "tags": "phantom-1",
    }).json()
    overdue = client.post("/api/missions", headers=headers, json={
        "title": "Still overdue", "due_date": past.isoformat(), "tags": "",
    }).json()
    future_mission = client.post("/api/missions", headers=headers, json={
        "title": "Due in future", "due_date": future.isoformat(),
    }).json()

    # on_time + late are completed today; overdue + future_mission stay pending.
    for mid in (on_time["id"], late["id"]):
        client.put(f"/api/missions/{mid}", headers=headers, json={"status": "completed"})

    # Habits: one daily habit completed today, one daily habit not completed.
    habit_done = client.post("/api/habits", headers=headers, json={"name": "Gym", "frequency": "daily"}).json()
    client.post("/api/habits", headers=headers, json={"name": "Read", "frequency": "daily"}).json()
    client.post(f"/api/habits/{habit_done['id']}/check-in", headers=headers)

    r = client.get(f"/api/stats/day?day={today.isoformat()}", headers=headers)
    assert r.status_code == 200
    data = r.json()

    # Missions due today: on_time only. Habits scheduled today: 2 daily.
    assert data["total_count"] == 3
    # Completed today: on_time (due + completed today) + habit_done.
    # The "late" mission was completed today but is NOT due today — it must
    # not inflate completed_count (surfaced separately instead).
    assert data["completed_count"] == 2
    assert data["completed_count"] <= data["total_count"]
    assert data["completion_rate"] == 66.67
    assert data["completion_rate"] <= 100.0
    assert data["completed_not_due_today"] == 1
    assert data["status_distribution"] == {"on_time": 1, "overdue": 0, "uncompleted": 0}
    assert data["type_distribution"] == [
        {"type": "mission", "count": 1},
        {"type": "habit", "count": 1},
    ]
    tags = {t["tag"]: t["count"] for t in data["tag_distribution"]}
    assert tags == {"phantom-1": 1, "stealth": 1}

    # Past day: late (completed after due) + overdue (still pending) both overdue.
    r_past = client.get(f"/api/stats/day?day={past.isoformat()}", headers=headers)
    past_data = r_past.json()
    assert past_data["status_distribution"] == {"on_time": 0, "overdue": 2, "uncompleted": 0}
    assert past_data["completed_count"] == 0

    # Future day: the future mission is uncompleted (not overdue yet).
    r_future = client.get(f"/api/stats/day?day={future.isoformat()}", headers=headers)
    future_data = r_future.json()
    assert future_data["status_distribution"] == {"on_time": 0, "overdue": 0, "uncompleted": 1}


def test_day_untagged_bucket_last(client, headers):
    # Same UTC-date reasoning as above.
    today = datetime.datetime.now(timezone.utc).date()
    m1 = client.post("/api/missions", headers=headers, json={
        "title": "Tagged", "due_date": today.isoformat(), "tags": "gotham",
    }).json()
    m2 = client.post("/api/missions", headers=headers, json={
        "title": "No tags", "due_date": today.isoformat(), "tags": "",
    }).json()
    client.put(f"/api/missions/{m1['id']}", headers=headers, json={"status": "completed"})
    client.put(f"/api/missions/{m2['id']}", headers=headers, json={"status": "completed"})

    data = client.get(f"/api/stats/day?day={today.isoformat()}", headers=headers).json()
    assert data["tag_distribution"][-1]["tag"] == "untagged"


def test_day_bad_date(client, headers):
    r = client.get("/api/stats/day?day=not-a-date", headers=headers)
    assert r.status_code == 422