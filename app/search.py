"""Find the flights between two airports in a time window."""

import time
from collections.abc import Callable

from .aircraft import AircraftDirectory
from .airports import Airport
from .cache import Cache
from .opensky import OpenSkyClient

DAY = 86400
# OpenSky builds flight lists in a nightly batch, so a day can still change
# for a while after it ends. Settled days are kept for a month.
SETTLED_AFTER = 2 * DAY
RECENT_TTL = 30 * 60
SETTLED_TTL = 30 * DAY


class RouteSearch:
    def __init__(self, opensky: OpenSkyClient, cache: Cache, aircraft: AircraftDirectory,
                 clock: Callable[[], float] = time.time):
        self.opensky = opensky
        self.cache = cache
        self.aircraft = aircraft
        self.clock = clock

    def _day_flights(self, kind: str, airport: str, day: int) -> list[dict]:
        key = f"{kind}:{airport}:{day}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        fetch = self.opensky.departures if kind == "dep" else self.opensky.arrivals
        flights = fetch(airport, day, day + DAY - 1)
        settled = day + DAY + SETTLED_AFTER < self.clock()
        self.cache.set(key, flights, SETTLED_TTL if settled else RECENT_TTL)
        return flights

    def search(self, origin: Airport, dest: Airport, begin: int, end: int) -> dict:
        end = min(end, int(self.clock()))
        days = range(begin - begin % DAY, end + 1, DAY)

        def in_window(f: dict) -> bool:
            return any(begin <= (f.get(k) or 0) <= end for k in ("firstSeen", "lastSeen"))

        flights: dict[tuple, dict] = {}

        def add(f: dict, match: str) -> None:
            key = (f["icao24"], f.get("firstSeen"))
            if key in flights:
                # Seen from both ends; keep the stronger match.
                if match == "confirmed":
                    flights[key]["match"] = match
                return
            flights[key] = {"raw": f, "match": match}

        for day in days:
            for f in self._day_flights("dep", origin.code, day):
                if not in_window(f):
                    continue
                arr = f.get("estArrivalAirport")
                if arr in dest.codes:
                    add(f, "confirmed")
                elif not arr:
                    add(f, "origin_only")
            for f in self._day_flights("arr", dest.code, day):
                if not in_window(f):
                    continue
                dep = f.get("estDepartureAirport")
                if dep in origin.codes:
                    add(f, "confirmed")
                elif not dep:
                    add(f, "dest_only")

        results = []
        for item in flights.values():
            f, match = item["raw"], item["match"]
            callsign = (f.get("callsign") or "").strip()
            # Unconfirmed flights can be numerous, so they only get offline lookups.
            info = self.aircraft.describe(f["icao24"], callsign, offline=match != "confirmed")
            results.append({
                "icao24": f["icao24"],
                "callsign": callsign,
                **info,
                "departure": {
                    "airport": f.get("estDepartureAirport") or (origin.code if match != "dest_only" else None),
                    "time": f.get("firstSeen"),
                },
                "arrival": {
                    "airport": f.get("estArrivalAirport") or (dest.code if match != "origin_only" else None),
                    "time": f.get("lastSeen"),
                },
                "match": match,
            })
        results.sort(key=lambda r: (r["match"] != "confirmed", -(r["departure"]["time"] or 0)))
        return {
            "origin": origin.to_dict(),
            "destination": dest.to_dict(),
            "begin": begin,
            "end": end,
            "flights": results,
        }
