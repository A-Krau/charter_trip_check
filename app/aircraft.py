"""Who is this aircraft? Registration, type and operator lookups from several sources."""

import csv
import json
import logging
import re
from pathlib import Path

from .cache import Cache
from .opensky import OpenSkyClient, OpenSkyError

log = logging.getLogger(__name__)

OPERATORS_FILE = Path(__file__).parent / "data" / "operators.json"
METADATA_TTL = 30 * 24 * 3600
MISS_TTL = 2 * 24 * 3600

# --- US registrations (N-numbers) map one-to-one onto ICAO24 addresses A00001-ADF7C7 ---

_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I or O
_SUFFIX = 1 + len(_LETTERS) * (1 + len(_LETTERS))  # 601: "", A, AA..AZ, B, BA..
_BUCKET4 = 1 + len(_LETTERS) + 10  # 35: "", letter, digit
_BUCKET3 = 10 * _BUCKET4 + _SUFFIX
_BUCKET2 = 10 * _BUCKET3 + _SUFFIX
_BUCKET1 = 10 * _BUCKET2 + _SUFFIX
_US_FIRST = 0xA00001
_US_COUNT = 9 * _BUCKET1


def _suffix(offset: int) -> str:
    if offset == 0:
        return ""
    first = _LETTERS[(offset - 1) // 25]
    rest = (offset - 1) % 25
    return first if rest == 0 else first + _LETTERS[rest - 1]


def us_registration(icao24: str) -> str | None:
    """Convert a US ICAO24 hex address to its N-number, e.g. 'a00001' -> 'N1'."""
    try:
        i = int(icao24, 16) - _US_FIRST
    except ValueError:
        return None
    if not 0 <= i < _US_COUNT:
        return None
    out = "N" + str(i // _BUCKET1 + 1)
    i %= _BUCKET1
    for bucket in (_BUCKET2, _BUCKET3):
        if i < _SUFFIX:
            return out + _suffix(i)
        i -= _SUFFIX
        out += str(i // bucket)
        i %= bucket
    if i < _SUFFIX:
        return out + _suffix(i)
    i -= _SUFFIX
    out += str(i // _BUCKET4)
    i %= _BUCKET4
    if i == 0:
        return out
    if i <= len(_LETTERS):
        return out + _LETTERS[i - 1]
    return out + str(i - len(_LETTERS) - 1)


# --- Operators from the callsign prefix (ICAO three-letter designator) ---

_TAIL_CALLSIGN = re.compile(r"^N[1-9][0-9A-Z]{0,4}$")


def load_operators(path: Path = OPERATORS_FILE) -> dict[str, str]:
    with open(path, encoding="utf-8") as f:
        return {k.upper(): v for k, v in json.load(f).items() if not k.startswith("_")}


def operator_from_callsign(callsign: str, operators: dict[str, str]) -> str | None:
    cs = callsign.strip().upper()
    if len(cs) >= 4 and cs[:3].isalpha() and cs[3].isdigit():
        return operators.get(cs[:3])
    return None


# --- Combined lookup ---


def _pick(d: dict, *keys: str) -> str:
    for k in keys:
        v = d.get(k)
        if v:
            return str(v).strip()
    return ""


class AircraftDirectory:
    def __init__(self, cache: Cache, opensky: OpenSkyClient, db_path: str = ""):
        self.cache = cache
        self.opensky = opensky
        self.operators = load_operators()
        self._db: dict[str, dict] | None = None
        self._db_path = db_path
        self._metadata_api_ok = True

    def _local_db(self) -> dict[str, dict]:
        """Lazily load an optional OpenSky aircraftDatabase.csv."""
        if self._db is None:
            self._db = {}
            if self._db_path and Path(self._db_path).is_file():
                with open(self._db_path, encoding="utf-8", errors="replace", newline="") as f:
                    first = f.readline()
                    f.seek(0)
                    quote = "'" if first.startswith("'") else '"'
                    for r in csv.DictReader(f, quotechar=quote):
                        icao = (r.get("icao24") or "").strip().lower()
                        if icao:
                            self._db[icao] = {
                                "registration": _pick(r, "registration"),
                                "typecode": _pick(r, "typecode"),
                                "model": " ".join(
                                    x for x in (_pick(r, "manufacturername", "manufacturerName"), _pick(r, "model")) if x
                                ),
                                "operator": _pick(r, "operator"),
                                "owner": _pick(r, "owner"),
                            }
                log.info("loaded %d aircraft from %s", len(self._db), self._db_path)
        return self._db

    def _metadata(self, icao24: str) -> dict:
        key = f"meta:{icao24}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        info: dict = {}
        if self._metadata_api_ok:
            try:
                raw = self.opensky.aircraft_metadata(icao24) or {}
                info = {
                    "registration": _pick(raw, "registration"),
                    "typecode": _pick(raw, "typecode"),
                    "model": " ".join(x for x in (_pick(raw, "manufacturerName"), _pick(raw, "model")) if x),
                    "operator": _pick(raw, "operator"),
                    "owner": _pick(raw, "owner"),
                }
            except OpenSkyError as e:
                if e.status == 429:
                    raise
                # The endpoint is undocumented; stop calling it for this run if it misbehaves.
                log.warning("aircraft metadata lookup failed (%s); disabling it", e)
                self._metadata_api_ok = False
                return {}
            except Exception as e:  # network trouble
                log.warning("aircraft metadata lookup failed: %s", e)
                return {}
        self.cache.set(key, info, METADATA_TTL if any(info.values()) else MISS_TTL)
        return info

    def describe(self, icao24: str, callsign: str, offline: bool = False) -> dict:
        """offline=True uses only local data and earlier lookups, never the network."""
        icao24 = icao24.lower()
        info = dict(self._local_db().get(icao24) or {})
        if not info.get("registration") or not info.get("typecode"):
            meta = (self.cache.get(f"meta:{icao24}") or {}) if offline else self._metadata(icao24)
            for k, v in meta.items():
                if v and not info.get(k):
                    info[k] = v
        cs = callsign.strip().upper()
        if not info.get("registration"):
            info["registration"] = us_registration(icao24) or (cs if _TAIL_CALLSIGN.match(cs) else "")
        info["callsign_operator"] = operator_from_callsign(cs, self.operators) or ""
        for k in ("typecode", "model", "operator", "owner"):
            info.setdefault(k, "")
        return info
