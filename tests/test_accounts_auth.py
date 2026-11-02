"""Tests for "Sign in with Google" (backend/accounts).

They run against SQLite by default. To also run them against a real Postgres
database, set TEST_DATABASE_URL (only the vg_accounts table is used, and it is
emptied at the start of every test).

Google's own token check is replaced by a stub, because a real token needs a
live Google sign-in. The last tests exercise the real verification wrapper with
the Google library call stubbed, to make sure every rejection rule is applied.
"""
import os

import pytest
from flask import Flask

from backend.accounts import google_auth, init_accounts, store

BACKENDS = ["sqlite"] + (["postgres"] if os.getenv("TEST_DATABASE_URL") else [])
CLIENT_ID = "123-test.apps.googleusercontent.com"
TOKEN = "t" * 40  # any string of plausible length: the stub decides what it means

SARTHAK = {"sub": "g-1001", "email": "sarthak@example.com", "name": "Sarthak Kumar",
           "picture": "https://lh3.googleusercontent.com/a/photo"}


class Env:
    def __init__(self, app):
        self.app = app
        self.client = app.test_client()
        self.profiles = {}  # token -> profile returned by the fake Google check

    def login(self, token=TOKEN, client=None):
        return (client or self.client).post("/api/auth/google", json={"credential": token})

    def accounts(self):
        db = store.Store()
        try:
            return [dict(r) for r in db._run("SELECT * FROM vg_accounts ORDER BY id").fetchall()]
        finally:
            db.close()


@pytest.fixture(params=BACKENDS)
def env(request, tmp_path, monkeypatch):
    for name in ("VERCEL", "APP_ENV", "DATABASE_URL", "POSTGRES_URL", "SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)
    if request.param == "postgres":
        monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    else:
        monkeypatch.setenv("AUTH_SQLITE_PATH", str(tmp_path / "auth.sqlite3"))

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"
    init_accounts(app)
    e = Env(app)
    e.profiles[TOKEN] = dict(SARTHAK)

    def fake_verify(credential):
        if credential not in e.profiles:
            raise google_auth.InvalidGoogleToken("bad token")
        return dict(e.profiles[credential])

    monkeypatch.setattr(google_auth, "verify", fake_verify)

    db = store.Store()
    try:
        db.execute("DELETE FROM vg_accounts")
        db.commit()
    finally:
        db.close()
    return e


# ---------- signing in ----------
def test_first_sign_in_creates_account_and_session(env):
    assert env.client.get("/api/auth/me").status_code == 401
    r = env.login()
    assert r.status_code == 200 and r.json["name"] == "Sarthak Kumar"

    me = env.client.get("/api/auth/me").json
    assert me["name"] == "Sarthak Kumar" and me["email"] == "sarthak@example.com"
    assert me["picture"].startswith("https://")

    rows = env.accounts()
    assert len(rows) == 1 and rows[0]["google_sub"] == "g-1001"


def test_signing_in_again_reuses_the_account_and_refreshes_details(env):
    env.login()
    first = env.accounts()[0]
    env.profiles[TOKEN] = {**SARTHAK, "name": "Sarthak K", "email": "new@example.com"}
    env.login(client=env.app.test_client())
    rows = env.accounts()
    assert len(rows) == 1 and rows[0]["id"] == first["id"]
    assert rows[0]["name"] == "Sarthak K" and rows[0]["email"] == "new@example.com"
    assert rows[0]["created_at"] == first["created_at"]


def test_different_google_accounts_get_different_users(env):
    env.profiles["b" * 40] = {"sub": "g-2002", "email": "tanmay@example.com",
                              "name": "Tanmay", "picture": None}
    env.login()
    env.login("b" * 40, client=env.app.test_client())
    assert [r["google_sub"] for r in env.accounts()] == ["g-1001", "g-2002"]


def test_logout_ends_the_session(env):
    env.login()
    assert env.client.post("/api/auth/logout").status_code == 200
    assert env.client.get("/api/auth/me").status_code == 401


def test_new_sign_in_replaces_any_old_session(env):
    env.profiles["b" * 40] = {"sub": "g-2002", "email": "tanmay@example.com",
                              "name": "Tanmay", "picture": None}
    env.login()
    env.login("b" * 40)
    assert env.client.get("/api/auth/me").json["name"] == "Tanmay"


@pytest.mark.parametrize("picture", ["http://insecure.example/p.png", "javascript:alert(1)",
                                     "data:text/html;base64,AAAA", None])
def test_non_https_photo_is_dropped(env, picture):
    env.profiles[TOKEN] = {**SARTHAK, "picture": picture}
    env.login()
    assert env.client.get("/api/auth/me").json["picture"] is None


# ---------- rejected requests ----------
def test_invalid_token_is_rejected(env):
    r = env.login("x" * 40)
    assert r.status_code == 401
    assert env.accounts() == []
    assert env.client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize("body", [{}, {"credential": ""}, {"credential": "short"},
                                  {"credential": 12345}, {"credential": "x" * 5000}])
def test_missing_or_malformed_credential_is_rejected(env, body):
    r = env.client.post("/api/auth/google", json=body)
    assert r.status_code == 400
    assert env.accounts() == []


def test_non_json_body_is_rejected(env):
    r = env.client.post("/api/auth/google", data="credential=abc", content_type="text/plain")
    assert r.status_code == 400


# ---------- safe configuration ----------
def test_config_returns_public_client_id(env):
    r = env.client.get("/api/auth/config")
    assert r.status_code == 200 and r.json["google_client_id"] == CLIENT_ID


def test_login_disabled_without_client_id(env, monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID")
    assert env.client.get("/api/auth/config").status_code == 503
    assert env.login().status_code == 503
    assert env.accounts() == []


def test_login_disabled_without_secret_key(env):
    env.app.config["SECRET_KEY"] = None
    assert env.client.get("/api/auth/config").status_code == 503
    assert env.login().status_code == 503


def test_production_without_database_url_is_unavailable(env, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    r = env.login()
    assert r.status_code == 503 and "temporarily unavailable" in r.json["error"]
    assert env.client.get("/api/auth/me").status_code == 401  # no half-made session


def test_cookie_is_secure_in_production_only(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "s")
    monkeypatch.setenv("VERCEL", "1")
    prod = Flask(__name__)
    init_accounts(prod)
    assert prod.config["SESSION_COOKIE_SECURE"] is True
    assert prod.config["SESSION_COOKIE_HTTPONLY"] is True

    monkeypatch.delenv("VERCEL")
    dev = Flask(__name__)
    init_accounts(dev)
    assert dev.config["SESSION_COOKIE_SECURE"] is False


def test_production_without_secret_key_does_not_invent_one(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    app = Flask(__name__)
    init_accounts(app)
    assert not app.config.get("SECRET_KEY")


def test_responses_are_not_cached(env):
    assert "no-store" in env.client.get("/api/auth/me").headers["Cache-Control"]
    assert "no-store" in env.login().headers["Cache-Control"]


# ---------- the real token check (Google library call stubbed) ----------
@pytest.fixture
def real_verify(monkeypatch):
    """Use the real google_auth.verify with only Google's library call replaced."""
    monkeypatch.undo()
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)
    seen = {}

    def make(claims):
        def fake(token, request, audience):
            seen["audience"] = audience
            if isinstance(claims, Exception):
                raise claims
            return dict(claims)
        monkeypatch.setattr(google_auth.id_token, "verify_oauth2_token", fake)
        return seen
    return make


GOOD = {"iss": "https://accounts.google.com", "sub": "g-1", "email": "A@Example.com",
        "email_verified": True, "name": "A B", "picture": "https://x/p.png"}


def test_verify_accepts_good_token_and_checks_our_client_id(real_verify):
    seen = real_verify(GOOD)
    profile = google_auth.verify("tok")
    assert seen["audience"] == CLIENT_ID  # a token made for another site is rejected by Google's lib
    assert profile == {"sub": "g-1", "email": "a@example.com", "name": "A B",
                       "picture": "https://x/p.png"}


@pytest.mark.parametrize("claims", [
    {**GOOD, "email_verified": False},
    {**GOOD, "email_verified": "true"},          # must be the boolean True
    {**{k: v for k, v in GOOD.items() if k != "email_verified"}},
    {**GOOD, "iss": "https://evil.example"},
    {**GOOD, "sub": ""},
    {**{k: v for k, v in GOOD.items() if k != "email"}},
])
def test_verify_rejects_bad_claims(real_verify, claims):
    real_verify(claims)
    with pytest.raises(google_auth.InvalidGoogleToken):
        google_auth.verify("tok")


def test_verify_turns_library_errors_into_invalid_token(real_verify):
    real_verify(ValueError("Token expired"))
    with pytest.raises(google_auth.InvalidGoogleToken):
        google_auth.verify("tok")


def test_verify_falls_back_to_email_name_when_google_sends_none(real_verify):
    real_verify({k: v for k, v in GOOD.items() if k != "name"})
    assert google_auth.verify("tok")["name"] == "a"


# ---------- helpers ----------
def test_clean_pg_url_drops_unknown_options():
    url = "postgresql://u:p@host:5432/db?sslmode=require&supa=base-pooler.x&connect_timeout=5"
    assert store.clean_pg_url(url) == "postgresql://u:p@host:5432/db?sslmode=require&connect_timeout=5"


# ---------- protected VarshaGuard features ----------
@pytest.fixture
def production_client(monkeypatch, tmp_path):
    # The production app reads VERCEL during account/session configuration.
    # Use local SQLite and a deterministic secret for the route-level checks.
    for name in ("VERCEL", "APP_ENV", "DATABASE_URL", "POSTGRES_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SECRET_KEY", "route-test-secret")
    monkeypatch.setenv("AUTH_SQLITE_PATH", str(tmp_path / "route-auth.sqlite3"))
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)
    from backend.app import app as production_app
    production_app.config.update(TESTING=True, SECRET_KEY="route-test-secret")
    yield production_app.test_client()
    if "accounts" in production_app.blueprints:
        pass


def test_ai_and_prediction_details_require_sign_in(production_client):
    endpoints = [
        ("/api/assistant", "post", {"message": "hello", "context": {}}),
        ("/api/assistant/voice", "post", {}),
        ("/api/bihar-live/model/live", "get", None),
        ("/api/bihar-live/forecast/river-stage?district=patna", "get", None),
        ("/api/bihar-live/probability?district=patna&type=flood", "get", None),
        ("/api/bihar-live/model/evaluation", "get", None),
        ("/api/bihar-live/model/evaluation/synthetic-demo", "get", None),
    ]
    for path, method, payload in endpoints:
        response = production_client.post(path, json=payload) if method == "post" else production_client.get(path)
        assert response.status_code == 401, (path, response.status_code)
        assert response.json["success"] is False


def test_bihar_public_weather_endpoints_remain_public(production_client, monkeypatch):
    response = production_client.get("/api/bihar-live/health")
    assert response.status_code == 200

    # Source requests are external; stub only the provider for deterministic coverage.
    from backend.bihar_live import public_weather
    monkeypatch.setattr(public_weather, "get_rainfall_forecast", lambda district: {
        "success": True, "available": False, "district": district
    })
    assert production_client.get("/api/bihar-live/weather?district=patna").status_code != 401
    assert production_client.get("/api/bihar-live/forecast/rainfall?district=patna").status_code != 401
