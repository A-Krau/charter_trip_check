"""Airport lookup backed by the bundled OurAirports extract."""

import csv
import gzip
import math
from dataclasses import asdict, dataclass
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "airports.csv.gz"
_TYPE_RANK = {"large": 0, "medium": 1, "small": 2}


@dataclass(frozen=True)
class Airport:
    ident: str
    type: str
    name: str
    lat: float
    lon: float
    country: str
    municipality: str
    iata: str
    icao: str
    gps: str
    local: str

    @property
    def code(self) -> str:
        """The code OpenSky uses. OurAirports idents are ICAO codes when one exists,
        and are more reliable than the separate icao_code column."""
        if len(self.ident) == 4 and self.ident.isalpha():
            return self.ident
        return self.icao or self.gps or self.ident

    @property
    def codes(self) -> set[str]:
        """Every code OpenSky might report for this airport."""
        return {c.upper() for c in (self.ident, self.icao, self.gps) if c}

    def to_dict(self) -> dict:
        d = asdict(self)
        d["code"] = self.code
        return d


class AirportIndex:
    def __init__(self, path: Path = DATA_FILE):
        self.airports: list[Airport] = []
        self._by_code: dict[str, Airport] = {}
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                a = Airport(**{**r, "lat": float(r["lat"]), "lon": float(r["lon"])})
                self.airports.append(a)
        # Register codes from the weakest to the strongest so that, for example,
        # an ICAO code always wins over some other airport's local code.
        for attr in ("local", "iata", "gps", "icao", "ident"):
            for a in sorted(self.airports, key=lambda a: -_TYPE_RANK.get(a.type, 3)):
                code = getattr(a, attr).upper()
                if code:
                    self._by_code[code] = a

    def get(self, code: str) -> Airport | None:
        code = code.strip().upper()
        if not code:
            return None
        a = self._by_code.get(code)
        # US convention: "TEB" -> "KTEB".
        if a is None and len(code) == 3:
            a = self._by_code.get("K" + code)
        return a

    def search(self, query: str, limit: int = 10) -> list[Airport]:
        q = query.strip().upper()
        if not q:
            return []
        exact = self.get(q)
        hits: list[tuple[tuple, Airport]] = []
        for a in self.airports:
            if a is exact:
                continue
            codes = (a.icao, a.iata, a.gps, a.ident, a.local)
            if any(c.upper().startswith(q) for c in codes if c):
                score = 0
            elif len(q) >= 3 and (q in a.name.upper() or q in a.municipality.upper()):
                score = 1
            else:
                continue
            hits.append(((score, _TYPE_RANK.get(a.type, 3), a.name), a))
        hits.sort(key=lambda h: h[0])
        result = [h[1] for h in hits[: limit - (1 if exact else 0)]]
        return ([exact] if exact else []) + result

    def nearest(self, lat: float, lon: float, max_km: float, limit: int = 3) -> list[tuple[Airport, float]]:
        """Airports within max_km of a point, closest first (small strips count a bit farther)."""
        dlat = max_km / 111.0
        dlon = max_km / (111.0 * max(math.cos(math.radians(lat)), 0.05))
        hits = []
        for a in self.airports:
            if abs(a.lat - lat) > dlat or abs(a.lon - lon) > dlon:
                continue
            d = haversine_km(lat, lon, a.lat, a.lon)
            if d <= max_km:
                hits.append((d * (1.0 if a.type != "small" else 1.5), d, a))
        hits.sort(key=lambda h: h[0])
        return [(a, d) for _, d, a in hits[:limit]]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))
