"""Phase 2: bat_focus.mode — validation, storage, stats grouping, migration."""

import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

import models
from database import SessionLocal


def _start(client, h, **body):
    return client.post("/api/focus/sessions", headers=h, json=body)


def _add_finished_session(owner_username, mode, minutes):
    """Insert a completed session directly (mode may be None, like old rows)."""
    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username=owner_username).first()
        end = datetime.now(timezone.utc)
        db.add(models.BatFocus(
            owner_id=user.id, mode=mode, duration_minutes=minutes,
            start_time=end - timedelta(minutes=minutes), end_time=end,
        ))
        db.commit()
    finally:
        db.close()


@pytest.mark.parametrize("mode", ["normal", "flip", "signal", "batmobile"])
def test_start_records_and_returns_each_mode(client, auth_headers, mode):
    h = auth_headers("mode_user")
    r = _start(client, h, mode=mode)
    assert r.status_code == 201, r.text
    assert r.json()["mode"] == mode
    listed = client.get("/api/focus/sessions", headers=h).json()
    assert any(s["id"] == r.json()["id"] and s["mode"] == mode for s in listed)


def test_mode_is_optional(client, auth_headers):
    h = auth_headers("mode_optional")
    assert _start(client, h).json()["mode"] is None
    assert _start(client, h, mode=None).json()["mode"] is None


@pytest.mark.parametrize("bad", ["Normal", "turbo", "", "N", 5])
def test_unknown_mode_is_rejected_with_422(client, auth_headers, bad):
    h = auth_headers("mode_bad")
    assert _start(client, h, mode=bad).status_code == 422


def test_mode_is_fixed_at_start(client, auth_headers):
    """Switching the timer's mode mid-session doesn't change what was recorded."""
    h = auth_headers("mode_fixed")
    s = _start(client, h, mode="flip").json()
    r = client.put(f"/api/focus/sessions/{s['id']}", headers=h, json={"mode": "signal"})
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "flip"


def test_stats_group_minutes_by_mode_with_nulls_as_unknown(client, auth_headers):
    h = auth_headers("mode_stats")
    _add_finished_session("mode_stats", "flip", 30)
    _add_finished_session("mode_stats", "flip", 10)
    _add_finished_session("mode_stats", "signal", 20)
    _add_finished_session("mode_stats", None, 40)  # recorded before modes existed

    stats = client.get("/api/stats/focus?period=all", headers=h).json()
    by_mode = {m["mode"]: m for m in stats["mode_breakdown"]}
    assert by_mode["flip"]["minutes"] == 40 and by_mode["flip"]["sessions"] == 2
    assert by_mode["signal"]["minutes"] == 20
    assert by_mode["unknown"]["minutes"] == 40 and by_mode["unknown"]["sessions"] == 1
    assert "normal" not in by_mode  # modes never used don't appear
    assert sum(m["percent"] for m in by_mode.values()) == pytest.approx(100, abs=0.2)
    # Known modes first (largest first); "unknown" last.
    assert [m["mode"] for m in stats["mode_breakdown"]] == ["flip", "signal", "unknown"]


def test_stats_mode_breakdown_empty_for_new_user(client, auth_headers):
    h = auth_headers("mode_stats_empty")
    assert client.get("/api/stats/focus?period=all", headers=h).json()["mode_breakdown"] == []


def test_migration_013_adds_nullable_mode_and_keeps_existing_rows(tmp_path):
    """Upgrade a database that is at 012 and has focus rows; check the column."""
    db_file = tmp_path / "migrate.db"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_file}",
    }
    backend = os.path.dirname(os.path.dirname(__file__))

    def alembic(*args):
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=backend, env=env, capture_output=True, text=True,
        )

    r = alembic("upgrade", "012")
    assert r.returncode == 0, r.stderr[-800:]
    con = sqlite3.connect(db_file)
    con.execute(
        "INSERT INTO bat_account (username, hashed_password, points, bat_level, is_active, "
        "created_at, updated_at, token_version) VALUES ('old','x',0,'The Orphan',1,"
        "datetime('now'),datetime('now'),0)"
    )
    con.execute(
        "INSERT INTO bat_focus (start_time, end_time, duration_minutes, owner_id) "
        "VALUES (datetime('now'), datetime('now'), 25, 1)"
    )
    con.commit()
    assert "mode" not in {row[1] for row in con.execute("PRAGMA table_info(bat_focus)")}
    con.close()

    r = alembic("upgrade", "head")
    assert r.returncode == 0, r.stderr[-800:]
    con = sqlite3.connect(db_file)
    cols = {row[1]: row for row in con.execute("PRAGMA table_info(bat_focus)")}
    assert "mode" in cols and cols["mode"][3] == 0  # notnull = 0 → nullable
    assert con.execute("SELECT duration_minutes, mode FROM bat_focus").fetchall() == [(25, None)]
    con.close()

    r = alembic("downgrade", "012")
    assert r.returncode == 0, r.stderr[-800:]
    con = sqlite3.connect(db_file)
    assert "mode" not in {row[1] for row in con.execute("PRAGMA table_info(bat_focus)")}
    assert con.execute("SELECT duration_minutes FROM bat_focus").fetchall() == [(25,)]
    con.close()
    assert alembic("upgrade", "head").returncode == 0  # and back up again
