"""SQLite-backed cache with a configurable (default 24-hour) TTL.

The cache stores arbitrary JSON-serialisable values keyed by a string (usually
a URL or a "name::type" composite key). Reads from a previously-scraped team or
player within the TTL hit local cache and never touch the network.

Design notes:
- A single connection is opened lazily and guarded by a lock so the class is
  safe to share across threads (FastAPI, Streamlit).
- `get_or_set` is the primary convenience wrapper: pass a callable "loader"
  that performs the expensive network work only on a cache miss.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Callable, Optional

from app import config


class SQLiteCache:
    """Thread-safe SQLite TTL cache."""

    def __init__(
        self,
        path: Optional[str] = None,
        default_ttl: Optional[int] = None,
    ) -> None:
        self.path = path or config.SQLITE_CACHE_PATH
        self.default_ttl = default_ttl if default_ttl is not None else config.CACHE_TTL_SECONDS
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    # -- lifecycle -----------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL;")
        return self._conn

    def _init_db(self) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    key        TEXT PRIMARY KEY,
                    value      TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at)"
            )
            conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # -- core API ------------------------------------------------------------
    def get(self, key: str) -> Optional[Any]:
        """Return the cached value, or None if absent/expired."""
        conn = self._connect()
        now = time.time()
        with self._lock:
            row = conn.execute(
                "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        value, expires_at = row
        if expires_at <= now:
            # Lazily evict the stale entry.
            with self._lock:
                conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                conn.commit()
            return None
        return json.loads(value)

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store a JSON value with an expiry of `ttl` seconds (default 24h)."""
        ttl = ttl if ttl is not None else self.default_ttl
        now = time.time()
        payload = json.dumps(value, ensure_ascii=False, default=str)
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                INSERT INTO cache (key, value, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at
                """,
                (key, payload, now, now + ttl),
            )
            conn.commit()

    def get_or_set(
        self, key: str, loader: Callable[[], Any], ttl: Optional[int] = None
    ) -> Any:
        """Return cached value for `key`, invoking `loader` only on a miss."""
        cached = self.get(key)
        if cached is not None:
            return cached
        value = loader()
        self.set(key, value, ttl=ttl)
        return value

    def has(self, key: str) -> bool:
        return self.get(key) is not None

    def delete(self, key: str) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            conn.commit()

    def clear(self) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute("DELETE FROM cache")
            conn.commit()

    def purge_expired(self) -> int:
        """Remove expired entries; returns the number removed."""
        conn = self._connect()
        with self._lock:
            cur = conn.execute("DELETE FROM cache WHERE expires_at <= ?", (time.time(),))
            conn.commit()
            return cur.rowcount

    def size(self) -> int:
        conn = self._connect()
        with self._lock:
            row = conn.execute("SELECT COUNT(*) FROM cache").fetchone()
        return int(row[0])
