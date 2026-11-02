"""Login / signup routes. People sign in with a code sent on WhatsApp (no passwords).

POST /api/auth/otp/request   {purpose: "signup"|"login", phone, name?}
POST /api/auth/otp/verify    {phone, code}
GET  /api/auth/me
POST /api/auth/logout
"""
import hashlib
import hmac
import os
import re
import secrets
import time
from contextlib import contextmanager

from flask import Blueprint, current_app, jsonify, request, session

from . import whatsapp
from .store import Store, StoreUnavailable, is_production

bp = Blueprint("accounts", __name__, url_prefix="/api/auth")

OTP_LENGTH = 6
OTP_TTL_SECONDS = 5 * 60          # a code works for 5 minutes
RESEND_COOLDOWN_SECONDS = 30      # wait between codes for one number
MAX_VERIFY_ATTEMPTS = 5           # wrong guesses allowed per code
MAX_OTPS_PER_HOUR = 5             # codes per number per hour
SESSION_DAYS = 30


def init_accounts(app):
    """Configure sessions and register the auth routes on the Flask app."""
    secret = os.getenv("SECRET_KEY")
    if secret:
        app.config["SECRET_KEY"] = secret
    elif not app.config.get("SECRET_KEY") and not is_production():
        # Local development only: sessions reset whenever the server restarts.
        app.config["SECRET_KEY"] = secrets.token_hex(32)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = is_production()
    app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * SESSION_DAYS
    if "accounts" not in app.blueprints:
        app.register_blueprint(bp)


# ---------- helpers ----------
def _error(message, status=400, **extra):
    return jsonify({"success": False, "error": message, **extra}), status


@contextmanager
def _open_store():
    store = Store()
    try:
        yield store
    finally:
        store.close()


@bp.errorhandler(StoreUnavailable)
def _store_down(exc):
    current_app.logger.error("accounts store unavailable: %s", exc)
    return _error("Login is temporarily unavailable. Please try again later.", 503)


@bp.after_request
def _no_store(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


def normalize_phone(raw):
    """Return a number like +919876543210, or None when it does not look valid."""
    raw = (raw or "").strip()
    digits = re.sub(r"\D", "", raw)
    if not raw.startswith("+"):
        if len(digits) == 10:
            digits = "91" + digits
        elif not (len(digits) == 12 and digits.startswith("91")):
            return None
    if not 10 <= len(digits) <= 15:
        return None
    if digits.startswith("91") and not re.fullmatch(r"91[6-9]\d{9}", digits):
        return None  # Indian mobile numbers start with 6, 7, 8 or 9
    return "+" + digits


def clean_name(raw):
    name = re.sub(r"[\x00-\x1f\x7f]", "", str(raw or ""))
    name = re.sub(r"\s+", " ", name).strip()
    return name if 2 <= len(name) <= 60 else None


def _secret_key():
    return current_app.config.get("SECRET_KEY")


def _hash_code(phone, code):
    key = _secret_key().encode()
    return hmac.new(key, f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def _mask_phone(phone):
    return f"{phone[:3]} {'•' * 5} {phone[-5:]}" if phone.startswith("+91") else phone


def _guard_setup():
    """Fail closed when the server is not configured safely."""
    if not _secret_key():
        current_app.logger.error("SECRET_KEY is not set; login is disabled")
        return _error("Login is not configured on this server.", 503)
    if not whatsapp.can_send():
        current_app.logger.error("WhatsApp credentials are not set; login is disabled")
        return _error("WhatsApp login is not configured on this server.", 503)
    return None


# ---------- routes ----------
@bp.post("/otp/request")
def request_otp():
    problem = _guard_setup()
    if problem:
        return problem

    data = request.get_json(silent=True) or {}
    purpose = data.get("purpose")
    if purpose not in ("signup", "login"):
        return _error("Invalid request.")

    phone = normalize_phone(data.get("phone"))
    if not phone:
        return _error("Enter a valid 10-digit mobile number.")

    name = None
    if purpose == "signup":
        name = clean_name(data.get("name"))
        if not name:
            return _error("Enter your name (2 to 60 characters).")

    now = int(time.time())
    with _open_store() as store:
        exists = store.user_by_phone(phone) is not None
        if purpose == "signup" and exists:
            return _error("This number is already registered. Please log in instead.", 409,
                          switch_to="login")
        if purpose == "login" and not exists:
            return _error("No account found for this number. Please sign up first.", 404,
                          switch_to="signup")

        store.purge_old_otps(now - 86400)

        last = store.last_otp_time(phone)
        if last is not None and now - last < RESEND_COOLDOWN_SECONDS:
            wait = RESEND_COOLDOWN_SECONDS - (now - last)
            return _error(f"Please wait {wait}s before requesting another code.", 429,
                          retry_after=wait)
        if store.count_otps_since(phone, now - 3600) >= MAX_OTPS_PER_HOUR:
            return _error("Too many codes requested. Try again in an hour.", 429)

        code = "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))
        store.replace_open_otp(phone, purpose, name, _hash_code(phone, code),
                               now + OTP_TTL_SECONDS, now)
        try:
            whatsapp.send_otp(phone, code)
        except RuntimeError as exc:
            current_app.logger.error("WhatsApp send failed: %s", exc)
            store.close_open_otps(phone)
            return _error("Could not send the WhatsApp message. Please try again.", 502)

    return jsonify({
        "success": True,
        "phone": phone,
        "expires_in": OTP_TTL_SECONDS,
        "resend_in": RESEND_COOLDOWN_SECONDS,
        "dev_mode": whatsapp.is_dev_mode(),
    })


@bp.post("/otp/verify")
def verify_otp():
    problem = _guard_setup()
    if problem:
        return problem

    data = request.get_json(silent=True) or {}
    phone = normalize_phone(data.get("phone"))
    code = re.sub(r"\D", "", str(data.get("code") or ""))
    if not phone or len(code) != OTP_LENGTH:
        return _error(f"Enter the {OTP_LENGTH}-digit code.")

    now = int(time.time())
    with _open_store() as store:
        row = store.open_otp(phone)
        if not row:
            return _error("No active code. Please request a new one.", expired=True)
        if now > row["expires_at"]:
            store.consume_otp(row["id"])
            return _error("This code has expired. Please request a new one.", expired=True)
        if row["attempts"] >= MAX_VERIFY_ATTEMPTS:
            store.consume_otp(row["id"])
            return _error("Too many wrong attempts. Please request a new code.", 429, expired=True)

        if not hmac.compare_digest(row["code_hash"], _hash_code(phone, code)):
            attempts = store.add_failed_attempt(row["id"])
            if attempts is None:
                return _error("No active code. Please request a new one.", expired=True)
            left = MAX_VERIFY_ATTEMPTS - attempts
            if left <= 0:
                store.consume_otp(row["id"])
                return _error("Too many wrong attempts. Please request a new code.", 429,
                              expired=True)
            return _error(f"Wrong code. {left} attempt{'s' if left != 1 else ''} left.")

        # Right code. Only one request can use it.
        if not store.consume_otp(row["id"]):
            return _error("This code was already used. Please request a new one.", expired=True)

        if row["purpose"] == "signup":
            user = store.create_user(row["name"], phone, now)
        else:
            user = store.user_by_phone(phone)
        if not user:
            return _error("No account found. Please sign up first.", 404, switch_to="signup")

    session.clear()
    session["uid"] = user["id"]
    session["name"] = user["name"]
    session["phone"] = user["phone"]
    session.permanent = True
    return jsonify({"success": True, "name": user["name"]})


@bp.get("/me")
def me():
    if "uid" not in session:
        return _error("Not logged in.", 401)
    return jsonify({
        "success": True,
        "name": session.get("name", ""),
        "phone": _mask_phone(session.get("phone", "")),
    })


@bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"success": True})
