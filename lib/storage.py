"""Storage layer.

Two interchangeable backends behind one interface:

* **SQLite**   - zero setup, used automatically. Perfect on a laptop, a VM or any
  host with a real disk. On Streamlit Community Cloud the container's disk is
  wiped whenever the app sleeps, reboots or is redeployed, so this backend is
  for trying the app out, not for the real field log.
* **Supabase** - free hosted Postgres. Used automatically as soon as
  `SUPABASE_URL` and `SUPABASE_KEY` are present in secrets. This is the one to
  use for the deployed app; see README for the three-line table setup.

Both store exactly the same shapes:

    entries  (date, agent)        -> the day's record, as JSON
    photos   (date, agent, which) -> one base64 data URL  (which: start|end|fuel)
    config   (key)                -> agentpins / resetrequests, as JSON
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config as C

PHOTO_KINDS = ("start", "end", "fuel")


# =============================================================== SQLite =====
class SqliteStore:
    name = "SQLite"
    persistent_on_cloud = False

    def __init__(self, path: Optional[str] = None):
        self.path = Path(path or C._secret("SQLITE_PATH", "data/reports.db"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    date TEXT NOT NULL, agent TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY (date, agent));
                CREATE TABLE IF NOT EXISTS photos (
                    date TEXT NOT NULL, agent TEXT NOT NULL, which TEXT NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY (date, agent, which));
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY, payload TEXT NOT NULL);
                """
            )
            self._db.commit()

    # -- entries ------------------------------------------------------------
    def get_entry(self, date: str, agent: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._db.execute(
                "SELECT payload FROM entries WHERE date=? AND agent=?", (date, agent)
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def put_entry(self, entry: Dict[str, Any]) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO entries (date, agent, payload) VALUES (?,?,?) "
                "ON CONFLICT(date, agent) DO UPDATE SET payload=excluded.payload",
                (entry["date"], entry["agent"], json.dumps(entry)),
            )
            self._db.commit()

    def list_entries(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT payload FROM entries").fetchall()
        return [json.loads(r["payload"]) for r in rows]

    # -- photos -------------------------------------------------------------
    def get_photo(self, date: str, agent: str, which: str) -> Optional[str]:
        with self._lock:
            row = self._db.execute(
                "SELECT payload FROM photos WHERE date=? AND agent=? AND which=?",
                (date, agent, which),
            ).fetchone()
        return row["payload"] if row else None

    def put_photo(self, date: str, agent: str, which: str, data: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO photos (date, agent, which, payload) VALUES (?,?,?,?) "
                "ON CONFLICT(date, agent, which) DO UPDATE SET payload=excluded.payload",
                (date, agent, which, data),
            )
            self._db.commit()

    # -- config -------------------------------------------------------------
    def get_config(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._db.execute("SELECT payload FROM config WHERE key=?", (key,)).fetchone()
        return json.loads(row["payload"]) if row else default

    def set_config(self, key: str, value: Any) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO config (key, payload) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET payload=excluded.payload",
                (key, json.dumps(value)),
            )
            self._db.commit()

    # -- retention ----------------------------------------------------------
    def purge_before(self, cutoff: str) -> int:
        with self._lock:
            n = self._db.execute("DELETE FROM entries WHERE date < ?", (cutoff,)).rowcount
            self._db.execute("DELETE FROM photos WHERE date < ?", (cutoff,))
            self._db.commit()
        return max(0, n or 0)


# ============================================================= Postgres =====
class PostgresStore:
    """Any Postgres, addressed by one connection string.

    This is the easiest way to give the app a database that survives a restart:
    create a free Postgres (Neon, Supabase, Railway - all give you a URL), paste
    it in as DATABASE_URL, done. The three tables are created automatically on
    first connect, so there is no SQL to run by hand.
    """

    name = "Postgres"
    persistent_on_cloud = True

    SCHEMA = """
        CREATE TABLE IF NOT EXISTS entries (
            date  TEXT  NOT NULL,
            agent TEXT  NOT NULL,
            payload JSONB NOT NULL,
            PRIMARY KEY (date, agent));
        CREATE TABLE IF NOT EXISTS photos (
            date  TEXT NOT NULL,
            agent TEXT NOT NULL,
            which TEXT NOT NULL,
            payload TEXT NOT NULL,
            PRIMARY KEY (date, agent, which));
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            payload JSONB NOT NULL);
    """

    def __init__(self, dsn: str):
        import psycopg2  # noqa: F401  (fail fast if the driver is missing)

        self.dsn = dsn
        self._lock = threading.Lock()
        self._conn = None
        self._connect()
        self._run(self.SCHEMA)

    def _connect(self) -> None:
        import psycopg2

        self._conn = psycopg2.connect(self.dsn, connect_timeout=15)
        self._conn.autocommit = True

    def _run(self, sql: str, args=(), fetch: Optional[str] = None):
        """Execute, reconnecting once if the pooled connection went stale.

        Hosted Postgres drops idle connections, and a Streamlit app sits idle
        for long stretches, so the first statement after a quiet spell can fail
        on a socket that is already gone.
        """
        with self._lock:
            for attempt in (1, 2):
                try:
                    with self._conn.cursor() as cur:
                        cur.execute(sql, args)
                        if fetch == "one":
                            return cur.fetchone()
                        if fetch == "all":
                            return cur.fetchall()
                        return cur.rowcount
                except Exception:
                    if attempt == 2:
                        raise
                    try:
                        self._conn.close()
                    except Exception:
                        pass
                    self._connect()

    @staticmethod
    def _json(value):
        from psycopg2.extras import Json

        return Json(value)

    # -- entries ------------------------------------------------------------
    def get_entry(self, date: str, agent: str) -> Optional[Dict[str, Any]]:
        row = self._run("SELECT payload FROM entries WHERE date=%s AND agent=%s",
                        (date, agent), fetch="one")
        return row[0] if row else None

    def put_entry(self, entry: Dict[str, Any]) -> None:
        self._run(
            "INSERT INTO entries (date, agent, payload) VALUES (%s,%s,%s) "
            "ON CONFLICT (date, agent) DO UPDATE SET payload = EXCLUDED.payload",
            (entry["date"], entry["agent"], self._json(entry)))

    def list_entries(self) -> List[Dict[str, Any]]:
        rows = self._run("SELECT payload FROM entries", fetch="all") or []
        return [r[0] for r in rows if r[0]]

    # -- photos -------------------------------------------------------------
    def get_photo(self, date: str, agent: str, which: str) -> Optional[str]:
        row = self._run(
            "SELECT payload FROM photos WHERE date=%s AND agent=%s AND which=%s",
            (date, agent, which), fetch="one")
        return row[0] if row else None

    def put_photo(self, date: str, agent: str, which: str, data: str) -> None:
        self._run(
            "INSERT INTO photos (date, agent, which, payload) VALUES (%s,%s,%s,%s) "
            "ON CONFLICT (date, agent, which) DO UPDATE SET payload = EXCLUDED.payload",
            (date, agent, which, data))

    # -- config -------------------------------------------------------------
    def get_config(self, key: str, default: Any = None) -> Any:
        row = self._run("SELECT payload FROM config WHERE key=%s", (key,), fetch="one")
        return row[0] if row else default

    def set_config(self, key: str, value: Any) -> None:
        self._run(
            "INSERT INTO config (key, payload) VALUES (%s,%s) "
            "ON CONFLICT (key) DO UPDATE SET payload = EXCLUDED.payload",
            (key, self._json(value)))

    # -- retention ----------------------------------------------------------
    def purge_before(self, cutoff: str) -> int:
        n = self._run("DELETE FROM entries WHERE date < %s", (cutoff,))
        self._run("DELETE FROM photos WHERE date < %s", (cutoff,))
        return max(0, n or 0)


# ============================================================= Supabase =====
class SupabaseStore:
    """Talks to Supabase's PostgREST endpoint with plain HTTP - no extra
    dependency beyond `requests`, which Streamlit already ships."""

    name = "Supabase"
    persistent_on_cloud = True

    def __init__(self, url: str, key: str):
        import requests  # noqa: F401  (fail fast if unavailable)

        self.base = url.rstrip("/") + "/rest/v1"
        self.headers = {
            "apikey": key,
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        }

    def _get(self, table: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
        import requests

        r = requests.get(
            self.base + "/" + table, headers=self.headers, params=params, timeout=20
        )
        r.raise_for_status()
        return r.json() or []

    def _upsert(self, table: str, row: Dict[str, Any]) -> None:
        import requests

        h = dict(self.headers)
        h["Prefer"] = "resolution=merge-duplicates,return=minimal"
        r = requests.post(self.base + "/" + table, headers=h, json=[row], timeout=20)
        r.raise_for_status()

    def _delete(self, table: str, params: Dict[str, str]) -> int:
        import requests

        h = dict(self.headers)
        h["Prefer"] = "return=representation"
        r = requests.delete(self.base + "/" + table, headers=h, params=params, timeout=30)
        r.raise_for_status()
        try:
            return len(r.json() or [])
        except Exception:
            return 0

    # -- entries ------------------------------------------------------------
    def get_entry(self, date: str, agent: str) -> Optional[Dict[str, Any]]:
        rows = self._get(
            "entries", {"select": "payload", "date": "eq." + date, "agent": "eq." + agent}
        )
        return rows[0]["payload"] if rows else None

    def put_entry(self, entry: Dict[str, Any]) -> None:
        self._upsert("entries", {"date": entry["date"], "agent": entry["agent"], "payload": entry})

    def list_entries(self) -> List[Dict[str, Any]]:
        rows = self._get("entries", {"select": "payload", "limit": "5000"})
        return [r["payload"] for r in rows if r.get("payload")]

    # -- photos -------------------------------------------------------------
    def get_photo(self, date: str, agent: str, which: str) -> Optional[str]:
        rows = self._get(
            "photos",
            {
                "select": "payload",
                "date": "eq." + date,
                "agent": "eq." + agent,
                "which": "eq." + which,
            },
        )
        return rows[0]["payload"] if rows else None

    def put_photo(self, date: str, agent: str, which: str, data: str) -> None:
        self._upsert("photos", {"date": date, "agent": agent, "which": which, "payload": data})

    # -- config -------------------------------------------------------------
    def get_config(self, key: str, default: Any = None) -> Any:
        rows = self._get("config", {"select": "payload", "key": "eq." + key})
        return rows[0]["payload"] if rows else default

    def set_config(self, key: str, value: Any) -> None:
        self._upsert("config", {"key": key, "payload": value})

    # -- retention ----------------------------------------------------------
    def purge_before(self, cutoff: str) -> int:
        n = self._delete("entries", {"date": "lt." + cutoff})
        self._delete("photos", {"date": "lt." + cutoff})
        return n


# ================================================================ factory ===
def build_store():
    """Pick a backend: DATABASE_URL, then Supabase, then a local SQLite file.

    Falling back rather than failing is deliberate - a typo in a connection
    string should not lock the whole team out of filing their day. The admin
    dashboard says loudly which backend is actually in use.
    """
    dsn = C._secret("DATABASE_URL")
    if dsn:
        try:
            return PostgresStore(str(dsn))
        except Exception as exc:
            print("Postgres unavailable, trying the next backend:", exc)

    url = C._secret("SUPABASE_URL")
    key = C._secret("SUPABASE_KEY")
    if url and key:
        try:
            return SupabaseStore(str(url), str(key))
        except Exception as exc:  # bad URL, no requests, network down at boot
            print("Supabase unavailable, falling back to SQLite:", exc)

    return SqliteStore()


def get_store():
    """Cached singleton. Falls back to a plain instance outside Streamlit."""
    try:
        import streamlit as st

        return st.cache_resource(build_store)()
    except Exception:
        return build_store()
