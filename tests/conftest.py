import pytest
from fastapi.testclient import TestClient

from app.cache import Cache
from app.config import Settings
from app.main import create_app

NOW = 1761264000  # 2025-10-24 00:00 UTC
DAY = 86400


class FakeOpenSky:
    """Stands in for OpenSkyClient; serves canned flights per (kind, airport, day)."""

    def __init__(self):
        self.departures_by_day: dict[tuple[str, int], list[dict]] = {}
        self.arrivals_by_day: dict[tuple[str, int], list[dict]] = {}
        self.calls: list[tuple] = []
        self.metadata: dict[str, dict] = {}
        self.tracks: dict[str, dict] = {}

    def departures(self, airport, begin, end):
        self.calls.append(("dep", airport, begin))
        return self.departures_by_day.get((airport, begin), [])

    def arrivals(self, airport, begin, end):
        self.calls.append(("arr", airport, begin))
        return self.arrivals_by_day.get((airport, begin), [])

    def aircraft_metadata(self, icao24):
        self.calls.append(("meta", icao24))
        return self.metadata.get(icao24)

    def track(self, icao24, at):
        return self.tracks.get(icao24)


def flight(icao24, callsign, dep, arr, first, last):
    return {"icao24": icao24, "callsign": callsign, "estDepartureAirport": dep,
            "estArrivalAirport": arr, "firstSeen": first, "lastSeen": last}


@pytest.fixture
def fake():
    return FakeOpenSky()


@pytest.fixture
def client(fake, tmp_path):
    settings = Settings(data_dir=tmp_path, opensky_client_id="", opensky_client_secret="")
    app = create_app(settings, opensky=fake, cache=Cache(":memory:"), clock=lambda: NOW)
    return TestClient(app)
