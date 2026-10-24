from tests.conftest import DAY, NOW, flight

D1 = NOW - 3 * DAY
TEB = (40.8501, -74.0608)


def est(client, icao, first, last, end):
    return client.get("/api/estimate", params={"icao24": icao, "first": first, "last": last, "end": end}).json()


def test_low_track_start_gives_high_confidence_origin(client, fake):
    # First seen on the ground at Teterboro.
    fake.tracks["a00001"] = {"icao24": "a00001", "path": [[D1, *TEB, 0, 90, True], [D1 + 600, 40.5, -74.2, 3000, 200, False]]}
    r = est(client, "a00001", D1, D1 + 9000, "origin")
    assert r["best"] == {"code": "KTEB", "confidence": "high", "source": "track"}
    assert r["track"]["candidates"][0]["code"] == "KTEB"


def test_high_track_start_falls_back_to_previous_landing(client, fake):
    # First seen at 7,000 m over New Jersey: too high to say.
    fake.tracks["a00002"] = {"icao24": "a00002", "path": [[D1, 40.6, -74.3, 7000, 200, False]]}
    fake.aircraft["a00002"] = [flight("a00002", "N1A", "KPBI", "KTEB", D1 - DAY, D1 - DAY + 9000)]
    r = est(client, "a00002", D1, D1 + 9000, "origin")
    assert r["track"]["confidence"] == "low"
    assert r["neighbour"]["code"] == "KTEB"
    assert r["best"]["code"] == "KTEB" and r["best"]["source"] == "neighbour"
    assert r["best"]["confidence"] == "medium"  # nearby candidates include KTEB


def test_destination_uses_track_end_and_next_departure(client, fake):
    fake.tracks["a00003"] = {"icao24": "a00003", "path": [[D1, *TEB, 0, 90, True], [D1 + 9000, 26.70, -80.10, 300, 180, False]]}
    fake.aircraft["a00003"] = [flight("a00003", "X", "KPBI", "KMIA", D1 + DAY, D1 + DAY + 3000)]
    r = est(client, "a00003", D1, D1 + 9000, "destination")
    assert r["best"]["code"] == "KPBI" and r["best"]["source"] == "track"
    assert r["neighbour"]["code"] == "KPBI"


def test_no_data(client, fake):
    r = est(client, "a00009", D1, D1 + 9000, "origin")
    assert r["best"] is None and r["track"] is None and r["neighbour"] is None
