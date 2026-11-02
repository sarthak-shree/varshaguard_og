"""Tests for the WhatsApp one-time-code login (backend/accounts).

They run against SQLite by default. To also run them against a real Postgres
database, set TEST_DATABASE_URL (only the vg_users and vg_otps tables are used,
and they are emptied at the start of every test).
"""
import os

import pytest
from flask import Flask

from backend.accounts import init_accounts, store, whatsapp

BACKENDS = ["sqlite"] + (["postgres"] if os.getenv("TEST_DATABASE_URL") else [])
PHONE = "9876543210"
E164 = "+919876543210"


class Env:
    def __init__(self, app, sent):
        self.app = app
        self.client = app.test_client()
        self.sent = sent  # (phone, code) for every message "sent on WhatsApp"

    def request(self, purpose="signup", phone=PHONE, name="Sarthak Kumar", client=None):
        body = {"purpose": purpose, "phone": phone}
        if purpose == "signup":
            body["name"] = name
        return (client or self.client).post("/api/auth/otp/request", json=body)

    def verify(self, code, phone=PHONE, client=None):
        return (client or self.client).post("/api/auth/otp/verify",
                                            json={"phone": phone, "code": code})

    @property
    def last_code(self):
        return self.sent[-1][1]

    def wrong_code(self):
        return "000000" if self.last_code != "000000" else "111111"

    def sql(self, statement, params=()):
        db = store.Store()
        try:
            db.execute(statement, params)
            db.commit()
        finally:
            db.close()

    def skip_cooldown(self):
        self.sql("UPDATE vg_otps SET created_at = created_at - 100")


@pytest.fixture(params=BACKENDS)
def env(request, tmp_path, monkeypatch):
    for name in ("VERCEL", "APP_ENV", "WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID",
                 "DATABASE_URL", "POSTGRES_URL", "SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    if request.param == "postgres":
        monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    else:
        monkeypatch.setenv("AUTH_SQLITE_PATH", str(tmp_path / "auth.sqlite3"))

    sent = []
    monkeypatch.setattr(whatsapp, "send_otp", lambda phone, code: sent.append((phone, code)))

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"
    init_accounts(app)

    e = Env(app, sent)
    e.sql("DELETE FROM vg_otps")
    e.sql("DELETE FROM vg_users")
    return e


# ---------- signup and login ----------
def test_signup_then_logout_then_login(env):
    r = env.request("signup")
    assert r.status_code == 200 and r.json["phone"] == E164 and r.json["dev_mode"] is True
    assert env.sent == [(E164, env.last_code)] and len(env.last_code) == 6

    assert env.client.get("/api/auth/me").status_code == 401  # not logged in until verified
    r = env.verify(env.last_code)
    assert r.status_code == 200 and r.json["name"] == "Sarthak Kumar"

    me = env.client.get("/api/auth/me").json
    assert me["name"] == "Sarthak Kumar" and me["phone"].endswith("43210")
    assert "9876543210" not in me["phone"]  # the number is masked

    assert env.client.post("/api/auth/logout").status_code == 200
    assert env.client.get("/api/auth/me").status_code == 401

    env.skip_cooldown()
    assert env.request("login").status_code == 200
    assert env.verify(env.last_code).status_code == 200
    assert env.client.get("/api/auth/me").json["name"] == "Sarthak Kumar"


def test_signup_number_formats_all_map_to_one_number(env):
    for raw in ("98765 43210", "+91 98765-43210", "919876543210"):
        env.sent.clear()
        env.sql("DELETE FROM vg_otps")
        assert env.request("signup", phone=raw).json["phone"] == E164


def test_login_unknown_number_suggests_signup(env):
    r = env.request("login")
    assert r.status_code == 404 and r.json["switch_to"] == "signup"
    assert env.sent == []


def test_signup_existing_number_suggests_login(env):
    env.request("signup")
    env.verify(env.last_code)
    env.skip_cooldown()
    r = env.request("signup")
    assert r.status_code == 409 and r.json["switch_to"] == "login"


@pytest.mark.parametrize("phone", ["12345", "5876543210", "", "abcdefghij"])
def test_invalid_phone_rejected(env, phone):
    assert env.request("login", phone=phone).status_code == 400
    assert env.sent == []


def test_signup_needs_a_name(env):
    assert env.request("signup", name=" ").status_code == 400
    assert env.request("signup", name="A").status_code == 400


# ---------- code rules ----------
def test_wrong_code_counts_down_then_locks(env):
    env.request("signup")
    good = env.last_code
    messages = [env.verify(env.wrong_code()).json["error"] for _ in range(4)]
    assert messages[0].startswith("Wrong code. 4 attempts")
    assert messages[3].startswith("Wrong code. 1 attempt left")
    locked = env.verify(env.wrong_code())
    assert locked.status_code == 429 and locked.json["expired"] is True
    assert env.verify(good).status_code == 400  # even the right code is dead now


def test_code_works_only_once(env):
    env.request("signup")
    code = env.last_code
    assert env.verify(code).status_code == 200
    again = env.app.test_client()
    assert env.verify(code, client=again).status_code == 400
    assert again.get("/api/auth/me").status_code == 401


def test_expired_code_rejected(env):
    env.request("signup")
    env.sql("UPDATE vg_otps SET expires_at = 1")
    r = env.verify(env.last_code)
    assert r.status_code == 400 and r.json["expired"] is True
    assert env.client.get("/api/auth/me").status_code == 401


def test_new_code_replaces_the_old_one(env):
    env.request("signup")
    first = env.last_code
    env.skip_cooldown()
    env.request("signup")
    second = env.last_code
    if first != second:  # (a 1-in-a-million repeat would make this check meaningless)
        assert env.verify(first).status_code == 400
    assert env.verify(second).status_code == 200


def test_resend_cooldown_and_hourly_limit(env):
    assert env.request("signup").status_code == 200
    r = env.request("signup")
    assert r.status_code == 429 and 0 < r.json["retry_after"] <= 30
    assert len(env.sent) == 1

    for _ in range(4):  # four more codes within the hour is allowed (5 total)...
        env.skip_cooldown()
        assert env.request("signup").status_code == 200
    env.skip_cooldown()
    r = env.request("signup")  # ...the sixth is not
    assert r.status_code == 429 and "hour" in r.json["error"]


def test_code_is_stored_hashed(env):
    env.request("signup")
    db = store.Store()
    try:
        row = db.one("SELECT code_hash FROM vg_otps")
    finally:
        db.close()
    assert env.last_code not in row["code_hash"] and len(row["code_hash"]) == 64


def test_failed_whatsapp_send_returns_502_and_cancels_code(env, monkeypatch):
    def boom(phone, code):
        raise RuntimeError("down")

    monkeypatch.setattr(whatsapp, "send_otp", boom)
    r = env.request("signup")
    assert r.status_code == 502
    assert env.verify("123456").status_code == 400  # nothing to verify against


# ---------- safe configuration ----------
def test_login_disabled_without_secret_key(env):
    env.app.config["SECRET_KEY"] = None
    r = env.request("signup")
    assert r.status_code == 503
    assert env.sent == []


def test_production_without_whatsapp_never_prints_codes(env, monkeypatch, capsys):
    monkeypatch.undo()  # drop the fake sender: use the real one
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/x")
    r = env.request("signup")
    assert r.status_code == 503
    assert "WhatsApp login code" not in capsys.readouterr().out


def test_production_without_database_url_is_unavailable(env, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("WHATSAPP_TOKEN", "t")
    monkeypatch.setenv("WHATSAPP_PHONE_ID", "1")
    r = env.request("signup")
    assert r.status_code == 503 and "temporarily unavailable" in r.json["error"]


def test_responses_are_not_cached(env):
    assert "no-store" in env.client.get("/api/auth/me").headers["Cache-Control"]


# ---------- helpers ----------
def test_clean_pg_url_drops_unknown_options():
    url = "postgresql://u:p@host:5432/db?sslmode=require&supa=base-pooler.x&connect_timeout=5"
    assert store.clean_pg_url(url) == "postgresql://u:p@host:5432/db?sslmode=require&connect_timeout=5"


def test_whatsapp_template_payload(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TOKEN", "tok")
    monkeypatch.setenv("WHATSAPP_PHONE_ID", "12345")
    captured = {}

    class Resp:
        status_code = 200
        text = "{}"

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, json=json)
        return Resp()

    monkeypatch.setattr(whatsapp.requests, "post", fake_post)
    whatsapp.send_otp(E164, "654321")
    assert captured["url"].endswith("/12345/messages")
    assert captured["headers"]["Authorization"] == "Bearer tok"
    assert captured["json"]["to"] == "919876543210"
    components = captured["json"]["template"]["components"]
    assert components[0]["parameters"][0]["text"] == "654321"
    assert components[1]["parameters"][0]["text"] == "654321"
