"""Settings read from environment variables (see .env.example)."""

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    opensky_client_id: str = field(default_factory=lambda: _env("OPENSKY_CLIENT_ID"))
    opensky_client_secret: str = field(default_factory=lambda: _env("OPENSKY_CLIENT_SECRET"))
    opensky_api_url: str = field(
        default_factory=lambda: _env("OPENSKY_API_URL", "https://opensky-network.org/api")
    )
    opensky_token_url: str = field(
        default_factory=lambda: _env(
            "OPENSKY_TOKEN_URL",
            "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token",
        )
    )
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", "/data")))
    # Optional OpenSky aircraft database CSV (aircraftDatabase.csv format) for
    # registration, type and operator lookups.
    aircraft_db_path: str = field(default_factory=lambda: _env("AIRCRAFT_DB_PATH"))
    max_window_days: int = field(default_factory=lambda: int(_env("MAX_WINDOW_DAYS", "7")))
    # Background map. The default OpenStreetMap tiles need no API key.
    map_tile_url: str = field(
        default_factory=lambda: _env("MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
    )
    map_attribution: str = field(
        default_factory=lambda: _env(
            "MAP_ATTRIBUTION",
            '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        )
    )
    # Darken light map tiles in the browser to keep the dark look.
    map_dark: bool = field(default_factory=lambda: _env("MAP_DARK", "true").lower() not in ("0", "false", "no"))

    @property
    def has_credentials(self) -> bool:
        return bool(self.opensky_client_id and self.opensky_client_secret)

    @property
    def cache_path(self) -> Path:
        return self.data_dir / "cache.sqlite3"
