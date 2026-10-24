"""Small SQLite key/value cache with per-entry expiry."""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class Cache:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL, expires REAL)"
        )
        self._db.commit()

    def get(self, key: str) -> Any | None:
        with self._lock:
            row = self._db.execute("SELECT value, expires FROM cache WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        value, expires = row
        if expires is not None and expires < time.time():
            return None
        return json.loads(value)

    def set(self, key: str, value: Any, ttl: float | None) -> None:
        """Store a value. ttl=None keeps it forever."""
        expires = None if ttl is None else time.time() + ttl
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO cache (key, value, expires) VALUES (?, ?, ?)",
                (key, json.dumps(value), expires),
            )
            self._db.commit()
