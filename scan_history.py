"""
scan_history.py — SQLite riwayat pemindaian nama (Smart 3-Letter Scanner).

Simpan semua nama yang sudah dipindai beserta statusnya dalam SQLite agar
riwayat tetap tersimpan setelah aplikasi ditutup. Mencegah pemindaian nama yang
sama berulang kali. Sediakan daftar history, filter, dan opsi rescan manual.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

DB_PATH = "scan_history.db"

# Status yang tersimpan per nama
STATUS_SCANNED = "scanned"
STATUS_AVAILABLE = "available"
STATUS_TAKEN = "taken"
STATUS_ERROR = "error"
STATUS_CLAIMED = "claimed"
STATUS_UNKNOWN = "unknown"
STATUS_RATE_LIMITED = "rate_limited"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE,
    status TEXT NOT NULL,
    source TEXT,
    reason TEXT,
    scanned_at REAL NOT NULL,
    UNIQUE(name)
);
CREATE INDEX IF NOT EXISTS idx_scans_name ON scans(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_scans_status ON scans(status);
CREATE INDEX IF NOT EXISTS idx_scans_scanned_at ON scans(scanned_at);
"""


class ScanHistory:
    """Akses thread-safe ke database riwayat pemindaian SQLite."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._connection: Optional[sqlite3.Connection] = None
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
            self._connection.executescript(_SCHEMA)
            self._connection.commit()
        return self._connection

    def _init_db(self) -> None:
        with self._lock:
            conn = self._conn()
            conn.executescript(_SCHEMA)
            conn.commit()

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                try:
                    self._connection.close()
                except Exception:  # noqa: BLE001
                    pass
                self._connection = None

    # ------------------------------------------------------------------ #
    # Write
    # ------------------------------------------------------------------ #
    def record(self, name: str, status: str, source: str = "", reason: str = "") -> None:
        """Catat/update hasil pemindaian untuk suatu nama (upsert)."""
        name = (name or "").strip().lower()
        if not name:
            return
        with self._lock:
            conn = self._conn()
            conn.execute(
                """
                INSERT INTO scans (name, status, source, reason, scanned_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    status=excluded.status,
                    source=excluded.source,
                    reason=excluded.reason,
                    scanned_at=excluded.scanned_at
                """,
                (name, status, source, reason, time.time()),
            )
            conn.commit()

    def record_many(self, rows: List[Tuple[str, str, str, str]]) -> None:
        """Bulk catat hasil pemindaian."""
        with self._lock:
            conn = self._conn()
            conn.executemany(
                """
                INSERT INTO scans (name, status, source, reason, scanned_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    status=excluded.status,
                    source=excluded.source,
                    reason=excluded.reason,
                    scanned_at=excluded.scanned_at
                """,
                [(n.lower(), s, src, r, time.time()) for n, s, src, r in rows],
            )
            conn.commit()

    def mark_claimed(self, name: str) -> None:
        self.record(name, STATUS_CLAIMED, "claimer", "claimed")

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #
    def get_status(self, name: str) -> Optional[Dict[str, Any]]:
        """Ambil status terakhir untuk satu nama."""
        name = (name or "").strip().lower()
        if not name:
            return None
        with self._lock:
            cur = self._conn().execute(
                "SELECT name, status, source, reason, scanned_at FROM scans WHERE name=? COLLATE NOCASE",
                (name,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def is_scanned(self, name: str) -> bool:
        return self.get_status(name) is not None

    def list_all(self, limit: int = 0, offset: int = 0) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn().execute(
                "SELECT name, status, source, reason, scanned_at FROM scans "
                "ORDER BY scanned_at DESC LIMIT ? OFFSET ?",
                (limit if limit > 0 else -1, offset),
            )
            return [dict(r) for r in cur.fetchall()]

    def list_by_status(self, status: str, limit: int = 0) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn().execute(
                "SELECT name, status, source, reason, scanned_at FROM scans "
                "WHERE status=? ORDER BY scanned_at DESC LIMIT ?",
                (status, limit if limit > 0 else -1),
            )
            return [dict(r) for r in cur.fetchall()]

    def search(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        q = f"%{query.lower()}%"
        with self._lock:
            cur = self._conn().execute(
                "SELECT name, status, source, reason, scanned_at FROM scans "
                "WHERE name LIKE ? COLLATE NOCASE ORDER BY scanned_at DESC LIMIT ?",
                (q, limit),
            )
            return [dict(r) for r in cur.fetchall()]

    def count(self) -> int:
        with self._lock:
            cur = self._conn().execute("SELECT COUNT(*) AS c FROM scans")
            return int(cur.fetchone()["c"])

    def count_by_status(self) -> Dict[str, int]:
        with self._lock:
            cur = self._conn().execute(
                "SELECT status, COUNT(*) AS c FROM scans GROUP BY status"
            )
            return {r["status"]: r["c"] for r in cur.fetchall()}

    def distinct_names(self) -> List[str]:
        with self._lock:
            cur = self._conn().execute("SELECT DISTINCT name FROM scans ORDER BY name")
            return [r["name"] for r in cur.fetchall()]

    def delete(self, name: str) -> bool:
        with self._lock:
            cur = self._conn().execute("DELETE FROM scans WHERE name=? COLLATE NOCASE", (name,))
            self._conn().commit()
            return cur.rowcount > 0

    def clear(self) -> int:
        with self._lock:
            cur = self._conn().execute("DELETE FROM scans")
            self._conn().commit()
            return cur.rowcount

    def names_needing_rescan(self, statuses: Tuple[str, ...] = (STATUS_ERROR, STATUS_UNKNOWN, STATUS_RATE_LIMITED),
                             older_than_seconds: Optional[float] = None) -> List[str]:
        """Nama yang layak di-rescan ulang (default: error/unknown/rate-limited)."""
        with self._lock:
            if older_than_seconds is not None:
                cutoff = time.time() - older_than_seconds
                placeholders = ",".join("?" * len(statuses))
                cur = self._conn().execute(
                    f"SELECT name FROM scans WHERE status IN ({placeholders}) "
                    f"AND scanned_at < ? ORDER BY scanned_at ASC",
                    (*statuses, cutoff),
                )
            else:
                placeholders = ",".join("?" * len(statuses))
                cur = self._conn().execute(
                    f"SELECT name FROM scans WHERE status IN ({placeholders}) ORDER BY scanned_at ASC",
                    statuses,
                )
            return [r["name"] for r in cur.fetchall()]
