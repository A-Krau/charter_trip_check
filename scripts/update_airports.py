"""Refresh app/data/airports.csv.gz from OurAirports (public domain).

Keeps only open airports (small, medium, large) and the columns the app uses.
Run: python scripts/update_airports.py [path-to-airports.csv]
"""

import csv
import gzip
import io
import sys
import urllib.request
from pathlib import Path

SOURCE_URL = "https://raw.githubusercontent.com/davidmegginson/ourairports-data/main/airports.csv"
OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "airports.csv.gz"
KEEP_TYPES = {"large_airport", "medium_airport", "small_airport"}
FIELDS = ["ident", "type", "name", "lat", "lon", "country", "municipality", "iata", "icao", "gps", "local"]


def main() -> None:
    if len(sys.argv) > 1:
        text = Path(sys.argv[1]).read_text(encoding="utf-8")
    else:
        with urllib.request.urlopen(SOURCE_URL, timeout=60) as resp:
            text = resp.read().decode("utf-8")

    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        if r["type"] not in KEEP_TYPES:
            continue
        rows.append({
            "ident": r["ident"],
            "type": r["type"].removesuffix("_airport"),
            "name": r["name"],
            "lat": f'{float(r["latitude_deg"]):.5f}',
            "lon": f'{float(r["longitude_deg"]):.5f}',
            "country": r["iso_country"],
            "municipality": r["municipality"],
            "iata": r["iata_code"],
            "icao": r["icao_code"],
            "gps": r["gps_code"],
            "local": r["local_code"],
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} airports to {OUT}")


if __name__ == "__main__":
    main()
