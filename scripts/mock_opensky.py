"""A fake OpenSky API for trying the UI without credentials or network.

Serves made-up flights between KTEB and KPBI (and a few others) for any day.
Run:  python scripts/mock_opensky.py  (listens on :9100)
Then: OPENSKY_API_URL=http://127.0.0.1:9100/api DATA_DIR=./data \
      uvicorn app.main:create_app --factory --port 8000
"""

import json
import math
import random
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

AIRPORTS = {"KTEB": (40.8501, -74.0608), "KPBI": (26.6832, -80.0956), "KHPN": (41.067, -73.7076),
            "KBOS": (42.3656, -71.0096), "KMIA": (25.7932, -80.2906)}
# icao24, callsign, registration, type, maker/model, operator
FLEET = [
    ("a1b2c3", "EJA512", "N512QS", "C68A", "Cessna Citation Latitude", "NetJets"),
    ("a2c4e6", "LXJ401", "N401FX", "CL35", "Bombardier Challenger 350", "Flexjet"),
    ("a3d5f7", "N225JL", "N225JL", "GLF4", "Gulfstream IV-SP", "Jet Linx"),
    ("a4e6a8", "XOJ77", "N77XO", "CL60", "Bombardier Challenger 605", "XOJET"),
    ("a5f7b9", "EJA88", "N88QS", "E55P", "Embraer Phenom 300", "NetJets"),
    ("a6a8ca", "N612WU", "N612WU", "C56X", "Cessna Citation Excel", "Wheels Up"),
]


def flights_for(day: int, origin: str, dest: str) -> list[dict]:
    rnd = random.Random(f"{day}{origin}{dest}")
    out = []
    for icao, cs, *_ in rnd.sample(FLEET, rnd.randint(2, 4)):
        dep = day + rnd.randint(6, 20) * 3600 + rnd.randint(0, 59) * 60
        unknown_dest = rnd.random() < 0.2
        out.append({"icao24": icao, "callsign": cs.ljust(8), "firstSeen": dep, "lastSeen": dep + rnd.randint(150, 170) * 60,
                    "estDepartureAirport": origin, "estArrivalAirport": None if unknown_dest else dest})
    return out


def track(f: dict) -> dict:
    (la1, lo1), (la2, lo2) = AIRPORTS[f["estDepartureAirport"]], AIRPORTS["KPBI"]
    n, path = 60, []
    for i in range(n + 1):
        t = i / n
        alt = min(1, t * 6, (1 - t) * 6) * 12500
        lat = la1 + (la2 - la1) * t + math.sin(t * math.pi) * 0.8
        lon = lo1 + (lo2 - lo1) * t + math.sin(t * math.pi) * 1.6
        path.append([f["firstSeen"] + int((f["lastSeen"] - f["firstSeen"]) * t), lat, lon, alt, 200, i in (0, n)])
    return {"icao24": f["icao24"], "startTime": f["firstSeen"], "endTime": f["lastSeen"], "path": path}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body=None):
        data = json.dumps(body).encode() if body is not None else b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path in ("/api/flights/departure", "/api/flights/arrival"):
            day = int(q["begin"]) // 86400 * 86400
            if u.path.endswith("departure"):
                fl = [f for d in AIRPORTS if d != q["airport"] for f in flights_for(day, q["airport"], d)] if q["airport"] == "KTEB" else []
            else:
                fl = [f for f in flights_for(day, "KTEB", q["airport"]) if f["estArrivalAirport"]] if q["airport"] != "KTEB" else []
            return self._send(200, fl) if fl else self._send(404)
        if u.path == "/api/tracks/all":
            day = int(q["time"]) // 86400 * 86400
            for f in flights_for(day, "KTEB", "KPBI"):
                if f["icao24"] == q["icao24"]:
                    return self._send(200, track(f))
            return self._send(404)
        if u.path.startswith("/api/metadata/aircraft/icao/"):
            icao = u.path.rsplit("/", 1)[1]
            for a in FLEET:
                if a[0] == icao:
                    maker, model = a[4].split(" ", 1)
                    return self._send(200, {"icao24": icao, "registration": a[2], "typecode": a[3],
                                            "manufacturerName": maker, "model": model, "operator": a[5]})
            return self._send(404)
        self._send(404)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 9100), Handler).serve_forever()
