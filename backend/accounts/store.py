"""Storage for accounts and one-time codes.

Production (Vercel) uses a hosted Postgres database, configured with the
DATABASE_URL (or POSTGRES_URL) environment variable. Vercel's filesystem is
temporary, so a local database file can NOT be used there.

For local development, when no database URL is set, a SQLite file is used so
the whole login flow can be tried without creating a database first.
"""
import os
import sqlite3
import threading
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# libpq rejects connection-string options it does not know. Hosted providers
# sometimes add their own (for example "supa=..."), so only known ones are kept.
_PG_URL_PARAMS = {"sslmode", "connect_timeout", "application_name", "sslrootcert"}

_schema_lock = threading.Lock()
_schema_ready = set()  # databases whose tables are already created in this process


class StoreUnavailable(RuntimeError):
    """The database is not configured or cannot be reached."""


def is_production() -> bool:
    return bool(os.getenv("VERCEL")) or os.getenv("APP_ENV", "").lower() == "production"


def database_url() -> str:
    return (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "").strip()


def clean_pg_url(url: str) -> str:
    parts = urlsplit(url)
    keep = [(k, v) for k, v in parse_qsl(parts.query) if k in _PG_URL_PARAMS]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(keep), ""))


def sqlite_path() -> str:
    return os.getenv("AUTH_SQLITE_PATH") or os.path.join(BASE_DIR, ".auth_dev.sqlite3")


_DDL = {
    "postgres": [
        """CREATE TABLE IF NOT EXISTS vg_users (
               id BIGSERIAL PRIMARY KEY,
               name TEXT NOT NULL,
               phone TEXT NOT NULL UNIQUE,
               created_at BIGINT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS vg_otps (
               id BIGSERIAL PRIMARY KEY,
               phone TEXT NOT NULL,
               purpose TEXT NOT NULL,
               name TEXT,
               code_hash TEXT NOT NULL,
               expires_at BIGINT NOT NULL,
               attempts INTEGER NOT NULL DEFAULT 0,
               used INTEGER NOT NULL DEFAULT 0,
               created_at BIGINT NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS idx_vg_otps_phone ON vg_otps (phone, created_at)",
    ],
    "sqlite": [
        """CREATE TABLE IF NOT EXISTS vg_users (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               name TEXT NOT NULL,
               phone TEXT NOT NULL UNIQUE,
               created_at INTEGER NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS vg_otps (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               phone TEXT NOT NULL,
               purpose TEXT NOT NULL,
               name TEXT,
               code_hash TEXT NOT NULL,
               expires_at INTEGER NOT NULL,
               attempts INTEGER NOT NULL DEFAULT 0,
               used INTEGER NOT NULL DEFAULT 0,
               created_at INTEGER NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS idx_vg_otps_phone ON vg_otps (phone, created_at)",
    ],
}


class Store:
    """One short-lived database connection (opened per request)."""

    def __init__(self):
        url = database_url()
        if url:
            try:
                import psycopg2
                import psycopg2.extras

                self.kind = "postgres"
                self._target = ("postgres", url)
                self.conn = psycopg2.connect(clean_pg_url(url), connect_timeout=5)
                self._cursor_args = {"cursor_factory": psycopg2.extras.RealDictCursor}
            except Exception as exc:  # missing driver, wrong URL, database down
                raise StoreUnavailable(f"Could not connect to the database: {exc}") from exc
        else:
            if is_production():
                raise StoreUnavailable("DATABASE_URL is not set")
            self.kind = "sqlite"
            self._target = ("sqlite", sqlite_path())
            self.conn = sqlite3.connect(sqlite_path(), timeout=10)
            self.conn.row_factory = sqlite3.Row
            self._cursor_args = {}
        self._ensure_schema()

    # ----- plumbing -----
    def _sql(self, sql):
        return sql.replace("?", "%s") if self.kind == "postgres" else sql

    def _ensure_schema(self):
        if self._target in _schema_ready:
            return
        with _schema_lock:
            if self._target in _schema_ready:
                return
            for attempt in range(2):
                try:
                    cur = self.conn.cursor(**self._cursor_args)
                    for statement in _DDL[self.kind]:
                        cur.execute(statement)
                    self.conn.commit()
                    break
                except Exception as exc:
                    # Two cold starts creating the tables at once can collide: retry once.
                    self.conn.rollback()
                    if attempt == 1:
                        raise StoreUnavailable(f"Could not prepare the database: {exc}") from exc
            _schema_ready.add(self._target)

    def _run(self, sql, params=()):
        cur = self.conn.cursor(**self._cursor_args)
        cur.execute(self._sql(sql), params)
        return cur

    def one(self, sql, params=()):
        row = self._run(sql, params).fetchone()
        return dict(row) if row is not None else None

    def execute(self, sql, params=()):
        return self._run(sql, params).rowcount

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

    # ----- users -----
    def user_by_phone(self, phone):
        return self.one("SELECT id, name, phone FROM vg_users WHERE phone = ?", (phone,))

    def create_user(self, name, phone, now):
        """Insert a user; if the number is already registered, return that user."""
        row = self.one(
            "INSERT INTO vg_users (name, phone, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT (phone) DO NOTHING RETURNING id, name, phone",
            (name, phone, now),
        )
        self.commit()
        return row or self.user_by_phone(phone)

    # ----- one-time codes -----
    def last_otp_time(self, phone):
        row = self.one(
            "SELECT created_at FROM vg_otps WHERE phone = ? ORDER BY created_at DESC LIMIT 1",
            (phone,),
        )
        return row["created_at"] if row else None

    def count_otps_since(self, phone, since):
        row = self.one(
            "SELECT COUNT(*) AS n FROM vg_otps WHERE phone = ? AND created_at > ?", (phone, since)
        )
        return int(row["n"])

    def replace_open_otp(self, phone, purpose, name, code_hash, expires_at, now):
        self.execute("UPDATE vg_otps SET used = 1 WHERE phone = ? AND used = 0", (phone,))
        self.execute(
            "INSERT INTO vg_otps (phone, purpose, name, code_hash, expires_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (phone, purpose, name, code_hash, expires_at, now),
        )
        self.commit()

    def close_open_otps(self, phone):
        self.execute("UPDATE vg_otps SET used = 1 WHERE phone = ? AND used = 0", (phone,))
        self.commit()

    def purge_old_otps(self, before):
        self.execute("DELETE FROM vg_otps WHERE created_at < ?", (before,))
        self.commit()

    def open_otp(self, phone):
        return self.one(
            "SELECT id, purpose, name, code_hash, expires_at, attempts FROM vg_otps "
            "WHERE phone = ? AND used = 0 ORDER BY created_at DESC LIMIT 1",
            (phone,),
        )

    def add_failed_attempt(self, otp_id):
        """Atomically count a wrong guess; returns the new total (None if already closed)."""
        row = self.one(
            "UPDATE vg_otps SET attempts = attempts + 1 WHERE id = ? AND used = 0 RETURNING attempts",
            (otp_id,),
        )
        self.commit()
        return row["attempts"] if row else None

    def consume_otp(self, otp_id):
        """Mark a code as used. True only for the single request that wins the race."""
        changed = self.execute("UPDATE vg_otps SET used = 1 WHERE id = ? AND used = 0", (otp_id,))
        self.commit()
        return changed == 1
