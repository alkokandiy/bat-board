"""The rest day and "N times a week" over the HTTP API.

Also the route that quietly bypassed its own service: PUT /api/habits/{id}
set columns directly, so none of the rules habit_service enforces applied to
the website. A habit switched from weekly to daily kept its weekdays, and
the two surfaces could end up disagreeing about the same habit — Alfred went
through the service and the screen did not.
"""


def _habit(client, h, **kw):
    kw.setdefault("name", "Run")
    r = client.post("/api/habits", headers=h, json=kw)
    assert r.status_code == 201, r.text
    return r.json()


class TestTimesPerWeekOverHttp:
    def test_three_times_a_week_round_trips(self, client, auth_headers):
        h = auth_headers("rest_three")
        made = _habit(client, h, name="Gym", frequency="weekly",
                      times_per_period=3)
        assert made["times_per_period"] == 3
        assert made["times_target"] == 3
        assert made["done_this_period"] == 0

    def test_progress_shows_after_a_check_in(self, client, auth_headers):
        h = auth_headers("rest_prog")
        made = _habit(client, h, name="Gym", frequency="weekly",
                      times_per_period=3)
        client.post(f"/api/habits/{made['id']}/check-in", headers=h)
        row = next(x for x in client.get("/api/habits", headers=h).json()
                   if x["id"] == made["id"])
        assert row["done_this_period"] == 1
        assert row["times_target"] == 3
        assert row["streak"] == 0, "one of three is not a kept week"

    def test_days_and_a_count_together_are_refused(self, client, auth_headers):
        h = auth_headers("rest_both")
        r = client.post("/api/habits", headers=h, json={
            "name": "Gym", "frequency": "weekly", "weekdays": "0,3",
            "times_per_period": 3})
        assert r.status_code == 400
        assert "not both" in r.json()["detail"]

    def test_an_ordinary_habit_is_unchanged(self, client, auth_headers):
        h = auth_headers("rest_plain")
        made = _habit(client, h, name="Water")
        assert made["times_target"] == 1
        assert made["resting_today"] is False


class TestRestDaysOverHttp:
    def test_resting_and_coming_back(self, client, auth_headers):
        h = auth_headers("rest_cycle")
        made = _habit(client, h, name="Run")
        hid = made["id"]

        r = client.post(f"/api/habits/{hid}/rest", headers=h, json={"note": "ill"})
        assert r.status_code == 200, r.text
        assert r.json()["resting"] is True

        row = next(x for x in client.get("/api/habits", headers=h).json()
                   if x["id"] == hid)
        assert row["resting_today"] is True

        listed = client.get(f"/api/habits/{hid}/rest", headers=h).json()
        assert len(listed) == 1 and listed[0]["note"] == "ill"

        back = client.delete(f"/api/habits/{hid}/rest", headers=h)
        assert back.status_code == 200
        assert back.json()["was_resting"] is True
        row = next(x for x in client.get("/api/habits", headers=h).json()
                   if x["id"] == hid)
        assert row["resting_today"] is False

    def test_a_rest_leaves_the_denominator(self, client, auth_headers):
        h = auth_headers("rest_denom")
        hid = _habit(client, h, name="Run")["id"]
        before = next(x for x in client.get("/api/habits", headers=h).json()
                      if x["id"] == hid)["adherence_window"]
        client.post(f"/api/habits/{hid}/rest", headers=h, json={})
        after = next(x for x in client.get("/api/habits", headers=h).json()
                     if x["id"] == hid)["adherence_window"]
        assert after == before - 1

    def test_someone_elses_habit_is_a_404(self, client, auth_headers):
        mine = auth_headers("rest_mine")
        theirs = auth_headers("rest_theirs")
        hid = _habit(client, mine, name="Private")["id"]
        assert client.post(f"/api/habits/{hid}/rest", headers=theirs,
                           json={}).status_code == 404
        assert client.delete(f"/api/habits/{hid}/rest",
                             headers=theirs).status_code == 404
        assert client.get(f"/api/habits/{hid}/rest",
                          headers=theirs).status_code == 404

    def test_a_malformed_date_is_a_400(self, client, auth_headers):
        h = auth_headers("rest_baddate")
        hid = _habit(client, h, name="Run")["id"]
        r = client.post(f"/api/habits/{hid}/rest", headers=h,
                        json={"on": "tuesday"})
        assert r.status_code == 400


class TestThePutRouteObeysItsOwnService:
    def test_switching_frequency_clears_the_old_fields(self, client, auth_headers):
        """Set directly, a weekly habit turned daily kept its weekdays."""
        h = auth_headers("rest_put")
        hid = _habit(client, h, name="Gym", frequency="weekly",
                     weekdays="0,3")["id"]
        r = client.put(f"/api/habits/{hid}", headers=h, json={"frequency": "daily"})
        assert r.status_code == 200, r.text
        assert r.json()["weekdays"] is None
        assert r.json()["frequency"] == "daily"

    def test_a_contradictory_edit_is_refused(self, client, auth_headers):
        h = auth_headers("rest_put2")
        hid = _habit(client, h, name="Gym", frequency="weekly",
                     weekdays="0,3")["id"]
        r = client.put(f"/api/habits/{hid}", headers=h,
                       json={"times_per_period": 3})
        assert r.status_code == 400
        assert "not both" in r.json()["detail"]

    def test_an_ordinary_rename_still_works(self, client, auth_headers):
        h = auth_headers("rest_put3")
        hid = _habit(client, h, name="Old")["id"]
        r = client.put(f"/api/habits/{hid}", headers=h, json={"name": "New"})
        assert r.status_code == 200
        assert r.json()["name"] == "New"

    def test_an_unknown_habit_is_a_404(self, client, auth_headers):
        h = auth_headers("rest_put4")
        assert client.put("/api/habits/999999", headers=h,
                          json={"name": "x"}).status_code == 404
