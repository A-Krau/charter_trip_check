from tests.conftest import DAY, NOW, flight

D1 = NOW - 3 * DAY  # a settled day


def test_confirmed_and_unconfirmed_matches(client, fake):
    fake.departures_by_day[("KTEB", D1)] = [
        flight("a00001", "EJA512  ", "KTEB", "KPBI", D1 + 3600, D1 + 13000),
        flight("a00002", "N1A     ", "KTEB", "KBOS", D1 + 4000, D1 + 8000),  # wrong destination
        flight("a00003", "LXJ401  ", "KTEB", None, D1 + 5000, D1 + 9000),    # destination unknown
    ]
    fake.arrivals_by_day[("KPBI", D1)] = [
        flight("a00001", "EJA512  ", "KTEB", "KPBI", D1 + 3600, D1 + 13000),  # same flight, seen at arrival
        flight("a00004", "XOJ77   ", None, "KPBI", D1 + 2000, D1 + 12000),
    ]
    fake.metadata["a00001"] = {"registration": "N1", "typecode": "C68A",
                               "manufacturerName": "Cessna", "model": "Citation Latitude",
                               "operator": "NetJets"}

    r = client.get("/api/search", params={"from": "TEB", "to": "PBI", "begin": D1, "end": D1 + DAY - 1})
    assert r.status_code == 200
    flights = r.json()["flights"]
    by_icao = {f["icao24"]: f for f in flights}
    assert set(by_icao) == {"a00001", "a00003", "a00004"}
    assert by_icao["a00001"]["match"] == "confirmed"
    assert by_icao["a00001"]["typecode"] == "C68A"
    assert by_icao["a00001"]["callsign_operator"] == "NetJets"
    assert by_icao["a00003"]["match"] == "origin_only"
    assert by_icao["a00003"]["callsign_operator"] == "Flexjet"
    assert by_icao["a00004"]["match"] == "dest_only"
    assert by_icao["a00004"]["departure"]["airport"] is None
    assert by_icao["a00004"]["arrival"]["airport"] == "KPBI"
    assert by_icao["a00003"]["arrival"]["airport"] is None
    assert flights[0]["icao24"] == "a00001"  # confirmed first
    # Unconfirmed flights do not cost metadata lookups.
    assert ("meta", "a00003") not in fake.calls


def test_window_filters_and_caches(client, fake):
    fake.departures_by_day[("KTEB", D1)] = [
        flight("a00001", "EJA512", "KTEB", "KPBI", D1 + 3600, D1 + 13000),
        flight("a00005", "EJA9", "KTEB", "KPBI", D1 + 80000, D1 + 85000),
    ]
    params = {"from": "KTEB", "to": "KPBI", "begin": D1, "end": D1 + 20000}
    first = client.get("/api/search", params=params).json()["flights"]
    assert [f["icao24"] for f in first] == ["a00001"]
    calls = len([c for c in fake.calls if c[0] in ("dep", "arr")])
    client.get("/api/search", params=params)
    assert len([c for c in fake.calls if c[0] in ("dep", "arr")]) == calls  # served from cache


def test_multi_day_window_queries_each_day(client, fake):
    client.get("/api/search", params={"from": "KTEB", "to": "KPBI", "begin": D1, "end": D1 + 2 * DAY + 5})
    days = sorted({c[2] for c in fake.calls if c[0] == "dep"})
    assert days == [D1, D1 + DAY, D1 + 2 * DAY]


def test_validation(client):
    assert client.get("/api/search", params={"from": "KTEB", "to": "KTEB", "begin": 0, "end": 10}).status_code == 400
    assert client.get("/api/search", params={"from": "KTEB", "to": "ZZZZ9", "begin": 0, "end": 10}).status_code == 404
    assert client.get("/api/search", params={"from": "KTEB", "to": "KPBI", "begin": 0, "end": 30 * DAY}).status_code == 400


def test_track_and_index(client, fake):
    fake.tracks["a00001"] = {"icao24": "a00001", "path": [[D1, 40.85, -74.06, 0, 90, True]]}
    assert client.get("/api/track", params={"icao24": "a00001", "time": D1}).json()["path"][0][1] == 40.85
    assert client.get("/api/track", params={"icao24": "a00009", "time": D1}).status_code == 404
    assert client.get("/").status_code == 200
