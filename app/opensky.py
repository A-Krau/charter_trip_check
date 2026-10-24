"""Minimal OpenSky Network REST client (https://openskynetwork.github.io/opensky-api/rest.html)."""

import time

import httpx

from .config import Settings


class OpenSkyError(Exception):
    """A request to OpenSky failed in a way the user should hear about."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class OpenSkyClient:
    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.settings = settings
        self.http = http or httpx.Client(timeout=30.0)
        self._token: str | None = None
        self._token_expires = 0.0

    def _auth_headers(self, force_refresh: bool = False) -> dict[str, str]:
        if not self.settings.has_credentials:
            return {}
        if force_refresh or not self._token or time.time() > self._token_expires - 60:
            resp = self.http.post(
                self.settings.opensky_token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.settings.opensky_client_id,
                    "client_secret": self.settings.opensky_client_secret,
                },
            )
            if resp.status_code != 200:
                raise OpenSkyError(
                    "OpenSky rejected the API credentials. Check OPENSKY_CLIENT_ID and "
                    "OPENSKY_CLIENT_SECRET.",
                    resp.status_code,
                )
            body = resp.json()
            self._token = body["access_token"]
            self._token_expires = time.time() + float(body.get("expires_in", 1800))
        return {"Authorization": f"Bearer {self._token}"}

    def _get(self, path: str, params: dict) -> list | dict | None:
        url = self.settings.opensky_api_url.rstrip("/") + path
        resp = self.http.get(url, params=params, headers=self._auth_headers())
        if resp.status_code == 401 and self.settings.has_credentials:
            resp = self.http.get(url, params=params, headers=self._auth_headers(force_refresh=True))
        if resp.status_code == 404:
            return None  # OpenSky's way of saying "no results"
        if resp.status_code == 429:
            retry = resp.headers.get("X-Rate-Limit-Retry-After-Seconds")
            hint = f" Try again in about {int(retry) // 60 + 1} minutes." if retry and retry.isdigit() else ""
            raise OpenSkyError("OpenSky's daily request allowance is used up." + hint, 429)
        if resp.status_code >= 400:
            raise OpenSkyError(f"OpenSky returned HTTP {resp.status_code} for {path}.", resp.status_code)
        return resp.json()

    def departures(self, airport: str, begin: int, end: int) -> list[dict]:
        return self._get("/flights/departure", {"airport": airport, "begin": begin, "end": end}) or []

    def arrivals(self, airport: str, begin: int, end: int) -> list[dict]:
        return self._get("/flights/arrival", {"airport": airport, "begin": begin, "end": end}) or []

    def track(self, icao24: str, at: int) -> dict | None:
        return self._get("/tracks/all", {"icao24": icao24.lower(), "time": at})

    def aircraft_metadata(self, icao24: str) -> dict | None:
        """Undocumented endpoint used by the OpenSky website. Best effort only."""
        return self._get(f"/metadata/aircraft/icao/{icao24.lower()}", {})
