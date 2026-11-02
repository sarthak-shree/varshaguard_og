"""Login with Google ("Sign in with Google") routes.

GET  /api/auth/config   -> the public Google client ID the login page needs
POST /api/auth/google   {credential}  -> checks Google's token and signs the person in
GET  /api/auth/me
POST /api/auth/logout
"""
import os
import secrets
import time
from contextlib import contextmanager

from flask import Blueprint, current_app, jsonify, request, session

from . import google_auth
from .store import Store, StoreUnavailable, is_production

bp = Blueprint("accounts", __name__, url_prefix="/api/auth")

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


def _safe_picture(url):
    """Only keep https photo links, since the page shows them in an <img>."""
    return url if isinstance(url, str) and url.startswith("https://") and len(url) <= 500 else None


# ---------- routes ----------
@bp.get("/config")
def config():
    client_id = google_auth.client_id()
    if not client_id or not current_app.config.get("SECRET_KEY"):
        return _error("Google sign-in is not configured on this server.", 503)
    return jsonify({"success": True, "google_client_id": client_id})


@bp.post("/google")
def google_login():
    if not current_app.config.get("SECRET_KEY") or not google_auth.client_id():
        current_app.logger.error("SECRET_KEY or GOOGLE_CLIENT_ID is not set; login is disabled")
        return _error("Google sign-in is not configured on this server.", 503)

    data = request.get_json(silent=True) or {}
    credential = data.get("credential")
    if not isinstance(credential, str) or not 20 <= len(credential) <= 4096:
        return _error("Missing Google sign-in token.")

    try:
        profile = google_auth.verify(credential)
    except google_auth.InvalidGoogleToken as exc:
        current_app.logger.warning("Google token rejected: %s", exc)
        return _error("Google sign-in could not be verified. Please try again.", 401)

    with _open_store() as store:
        account = store.sign_in(profile["sub"], profile["email"], profile["name"],
                                _safe_picture(profile["picture"]), int(time.time()))

    session.clear()
    session["uid"] = account["id"]
    session["name"] = account["name"]
    session["email"] = account["email"]
    session["picture"] = _safe_picture(account["picture"])
    session.permanent = True
    return jsonify({"success": True, "name": account["name"]})


@bp.get("/me")
def me():
    if "uid" not in session:
        return _error("Not logged in.", 401)
    return jsonify({
        "success": True,
        "name": session.get("name", ""),
        "email": session.get("email", ""),
        "picture": session.get("picture"),
    })


@bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"success": True})
