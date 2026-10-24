"""Best guess at the unknown end of a flight.

OpenSky leaves estDepartureAirport or estArrivalAirport empty when receivers
did not see the aircraft close to an airport. Two clues help:

1. Where the track starts (or ends): if the aircraft was low or on the ground,
   the nearest airport is very likely it. If it was already high, nearby
   airports are only loose candidates.
2. The aircraft's neighbouring flight: where it last landed before this flight
   (or next took off from after it) is usually where it was parked.
"""

import time

from .airports import AirportIndex, haversine_km
from .cache import Cache
from .opensky import OpenSkyClient, OpenSkyError

DAY = 86400
TRACK_TTL = 30 * DAY
LOW_M = 1500  # about 5,000 ft
GROUND_M = 600  # about 2,000 ft


class Estimator:
    def __init__(self, opensky: OpenSkyClient, cache: Cache, airports: AirportIndex):
        self.opensky = opensky
        self.cache = cache
        self.airports = airports

    def track(self, icao24: str, at: int) -> dict | None:
        """Cached track lookup, shared with the /api/track endpoint."""
        key = f"track:{icao24.lower()}:{at}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached or None
        raw = self.opensky.track(icao24, at)
        result = {"icao24": raw.get("icao24"), "path": raw["path"]} if raw and raw.get("path") else {}
        self.cache.set(key, result, TRACK_TTL if result else 3600)
        return result or None

    def _from_track(self, icao24: str, first_seen: int, end: str) -> dict | None:
        try:
            t = self.track(icao24, first_seen + 60)
        except OpenSkyError as e:
            if e.status == 429:
                raise
            return None
        path = [p for p in (t or {}).get("path", []) if p[1] is not None and p[2] is not None]
        if not path:
            return None
        point = path[0] if end == "origin" else path[-1]
        _, lat, lon, alt, _, on_ground = (point + [None] * 6)[:6]
        alt = alt if alt is not None else 99999
        low = on_ground or alt < LOW_M
        near = self.airports.nearest(lat, lon, max_km=15 if low else 80)
        if not near:
            return {"point": {"lat": lat, "lon": lon, "alt_m": None if alt == 99999 else alt}, "candidates": []}
        best_dist = near[0][1]
        if (on_ground or alt < GROUND_M) and best_dist < 8:
            confidence = "high"
        elif low and best_dist < 15:
            confidence = "medium"
        else:
            confidence = "low"
        return {
            "point": {"lat": lat, "lon": lon, "alt_m": None if alt == 99999 else alt, "on_ground": bool(on_ground)},
            "confidence": confidence,
            "candidates": [{**a.to_dict(), "distance_km": round(d, 1)} for a, d in near],
        }

    def _neighbour(self, icao24: str, first_seen: int, last_seen: int, end: str) -> dict | None:
        try:
            if end == "origin":
                flights = self.opensky.aircraft_flights(icao24, first_seen - 2 * DAY, first_seen - 1)
                before = [f for f in flights if (f.get("lastSeen") or 0) < first_seen and f.get("estArrivalAirport")]
                f = max(before, key=lambda f: f["lastSeen"], default=None)
                code, when = (f["estArrivalAirport"], f["lastSeen"]) if f else (None, None)
            else:
                flights = self.opensky.aircraft_flights(icao24, last_seen + 1, last_seen + 2 * DAY)
                after = [f for f in flights if (f.get("firstSeen") or 0) > last_seen and f.get("estDepartureAirport")]
                f = min(after, key=lambda f: f["firstSeen"], default=None)
                code, when = (f["estDepartureAirport"], f["firstSeen"]) if f else (None, None)
        except OpenSkyError as e:
            if e.status == 429:
                raise
            return None
        if not code:
            return None
        a = self.airports.get(code)
        return {"code": a.code if a else code, "time": when, "airport": a.to_dict() if a else None}

    def estimate(self, icao24: str, first_seen: int, last_seen: int, end: str) -> dict:
        key = f"est:{icao24.lower()}:{first_seen}:{end}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        result = {
            "end": end,
            "track": self._from_track(icao24, first_seen, end),
            "neighbour": self._neighbour(icao24, first_seen, last_seen, end),
        }
        # Pick one answer: a close, low track point beats the neighbouring flight.
        best = None
        tr = result["track"]
        if tr and tr.get("candidates") and tr["confidence"] in ("high", "medium"):
            best = {"code": tr["candidates"][0]["code"], "confidence": tr["confidence"], "source": "track"}
        elif result["neighbour"]:
            nb = result["neighbour"]
            # The previous landing is more believable if the track starts near it.
            agrees = bool(tr and nb["airport"] and haversine_km(
                tr["point"]["lat"], tr["point"]["lon"], nb["airport"]["lat"], nb["airport"]["lon"]) <= 80)
            best = {"code": nb["code"], "confidence": "medium" if agrees else "low", "source": "neighbour"}
        elif tr and tr.get("candidates"):
            best = {"code": tr["candidates"][0]["code"], "confidence": "low", "source": "track"}
        result["best"] = best
        # Settled flights won't change; recent ones may gain data (like the next flight).
        settled = last_seen < time.time() - 2 * DAY
        self.cache.set(key, result, TRACK_TTL if settled else 3600)
        return result
