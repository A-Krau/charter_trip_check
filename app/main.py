"""Charter Trip Check web app: FastAPI backend plus the static map UI."""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .aircraft import AircraftDirectory
from .airports import AirportIndex
from .cache import Cache
from .config import Settings
from .estimate import Estimator
from .opensky import OpenSkyClient, OpenSkyError
from .search import DAY, RouteSearch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
STATIC_DIR = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None, opensky: OpenSkyClient | None = None,
               cache: Cache | None = None, clock=None) -> FastAPI:
    settings = settings or Settings()
    cache = cache or Cache(settings.cache_path)
    opensky = opensky or OpenSkyClient(settings)
    airports = AirportIndex()
    aircraft = AircraftDirectory(cache, opensky, settings.aircraft_db_path)
    extra_ops = settings.data_dir / "operators.json"
    if extra_ops.is_file():
        from .aircraft import load_operators
        aircraft.operators.update(load_operators(extra_ops))
    estimator = Estimator(opensky, cache, airports)
    search = RouteSearch(opensky, cache, aircraft, **({"clock": clock} if clock else {}))

    app = FastAPI(title="Charter Trip Check", docs_url="/api/docs", openapi_url="/api/openapi.json")

    def airport_or_404(code: str):
        a = airports.get(code)
        if a is None:
            raise HTTPException(404, f"Unknown airport: {code}")
        return a

    @app.get("/api/status")
    def status():
        return {
            "authenticated": settings.has_credentials,
            "max_window_days": settings.max_window_days,
            "map": {"url": settings.map_tile_url, "attribution": settings.map_attribution, "dark": settings.map_dark},
        }

    @app.get("/api/airports")
    def airport_search(q: str = Query(..., min_length=1), limit: int = Query(8, le=25)):
        return [a.to_dict() for a in airports.search(q, limit)]

    @app.get("/api/airports/{code}")
    def airport_get(code: str):
        return airport_or_404(code).to_dict()

    @app.get("/api/search")
    def route_search(
        origin: str = Query(..., alias="from"),
        dest: str = Query(..., alias="to"),
        begin: int = Query(..., description="Window start, Unix seconds"),
        end: int = Query(..., description="Window end, Unix seconds"),
    ):
        o, d = airport_or_404(origin), airport_or_404(dest)
        if o.code == d.code:
            raise HTTPException(400, "Departure and arrival airports are the same.")
        if end <= begin:
            raise HTTPException(400, "The window must end after it starts.")
        if end - begin > settings.max_window_days * DAY:
            raise HTTPException(400, f"The window can be at most {settings.max_window_days} days.")
        try:
            return search.search(o, d, begin, end)
        except OpenSkyError as e:
            raise HTTPException(502 if e.status != 429 else 429, str(e))
        except Exception as e:  # network failure talking to OpenSky
            logging.exception("search failed")
            raise HTTPException(502, f"Could not reach OpenSky: {e.__class__.__name__}")

    def opensky_errors(fn):
        try:
            return fn()
        except OpenSkyError as e:
            raise HTTPException(502 if e.status != 429 else 429, str(e))
        except Exception as e:  # network failure talking to OpenSky
            logging.exception("OpenSky call failed")
            raise HTTPException(502, f"Could not reach OpenSky: {e.__class__.__name__}")

    @app.get("/api/track")
    def track(icao24: str, time: int):
        result = opensky_errors(lambda: estimator.track(icao24, time))
        if not result:
            raise HTTPException(404, "No track available for this flight.")
        return result

    @app.get("/api/estimate")
    def estimate(
        icao24: str,
        first: int = Query(..., description="firstSeen of the flight"),
        last: int = Query(..., description="lastSeen of the flight"),
        end: str = Query(..., pattern="^(origin|destination)$"),
    ):
        return opensky_errors(lambda: estimator.estimate(icao24, first, last, end))

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    return app
