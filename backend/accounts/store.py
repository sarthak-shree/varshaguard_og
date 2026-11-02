"""Storage for signed-in accounts.

Production (Vercel) uses a hosted Postgres database, configured with the
DATABASE_URL (or POSTGRES_URL) environment variable. Vercel's filesystem is
temporary, so a local database file can NOT be used there.

For local development, when no database URL is set, a SQLite file is used so
the login can be tried without creating a database first.
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
        """CREATE TABLE IF NOT EXISTS vg_accounts (
               id BIGSERIAL PRIMARY KEY,
               google_sub TEXT NOT NULL UNIQUE,
               email TEXT NOT NULL,
               name TEXT NOT NULL,
               picture TEXT,
               created_at BIGINT NOT NULL,
               last_login_at BIGINT NOT NULL)""",
    ],
    "sqlite": [
        """CREATE TABLE IF NOT EXISTS vg_accounts (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               google_sub TEXT NOT NULL UNIQUE,
               email TEXT NOT NULL,
               name TEXT NOT NULL,
               picture TEXT,
               created_at INTEGER NOT NULL,
               last_login_at INTEGER NOT NULL)""",
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
                    # Two cold starts creating the table at once can collide: retry once.
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

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

    # ----- accounts -----
    def sign_in(self, google_sub, email, name, picture, now):
        """Create the account on first sign-in; refresh name, email and photo afterwards."""
        row = self.one(
            "INSERT INTO vg_accounts (google_sub, email, name, picture, created_at, last_login_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (google_sub) DO UPDATE SET email = excluded.email, name = excluded.name, "
            "picture = excluded.picture, last_login_at = excluded.last_login_at "
            "RETURNING id, name, email, picture",
            (google_sub, email, name, picture, now, now),
        )
        self.commit()
        return row
