"""Username/password accounts with Twilio Verify WhatsApp OTP.

Required production configuration:
  DATABASE_URL (persistent PostgreSQL recommended)
  SECRET_KEY (long random secret)
  TWILIO_ACCOUNT_SID
  TWILIO_AUTH_TOKEN
  TWILIO_VERIFY_SERVICE_SID
"""
import os
import re
from datetime import datetime, timedelta, timezone
from functools import wraps

import requests
from flask import Blueprint, current_app, jsonify, request, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")
db = SQLAlchemy()
E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,24}$")


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(24), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(16), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class OTPChallenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(16), nullable=False, index=True)
    purpose = db.Column(db.String(16), nullable=False)
    username = db.Column(db.String(24), nullable=True)
    password_hash = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    consumed = db.Column(db.Boolean, nullable=False, default=False)


def init_auth(app):
    database_url = os.environ.get("DATABASE_URL", "").strip()
    secret_key = os.environ.get("SECRET_KEY", "").strip()
    if os.environ.get("VERCEL") and not database_url:
        raise RuntimeError("Set DATABASE_URL to persistent PostgreSQL before deploying authentication on Vercel.")
    if os.environ.get("VERCEL") and not secret_key:
        raise RuntimeError("Set a strong SECRET_KEY before deploying authentication on Vercel.")
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url or ("sqlite:////tmp/varshaguard_auth.sqlite3" if os.environ.get("VERCEL") else "sqlite:///varshaguard_auth.sqlite3")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = secret_key or "dev-only-change-this-secret"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "true").lower() == "true"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
    db.init_app(app)
    app.register_blueprint(auth_bp)
    with app.app_context():
        db.create_all()


def json_error(message, status=400):
    response = jsonify({"success": False, "error": message})
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    return response


def body():
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def valid_phone(phone):
    return isinstance(phone, str) and bool(E164_RE.fullmatch(phone.strip()))


def twilio_configured():
    return all(os.environ.get(key) for key in (
        "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_VERIFY_SERVICE_SID"
    ))


def twilio_verify(phone):
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    service = os.environ["TWILIO_VERIFY_SERVICE_SID"]
    response = requests.post(
        f"https://verify.twilio.com/v2/Services/{service}/Verifications",
        auth=(sid, os.environ["TWILIO_AUTH_TOKEN"]),
        data={"To": phone, "Channel": "whatsapp"},
        timeout=12,
    )
    if not response.ok:
        current_app.logger.warning("Twilio Verify start failed: HTTP %s", response.status_code)
        return False
    return True


def twilio_check(phone, code):
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    service = os.environ["TWILIO_VERIFY_SERVICE_SID"]
    try:
        response = requests.post(
            f"https://verify.twilio.com/v2/Services/{service}/VerificationCheck",
            auth=(sid, os.environ["TWILIO_AUTH_TOKEN"]),
            data={"To": phone, "Code": code},
            timeout=12,
        )
    except requests.RequestException:
        return False
    return response.ok and response.json().get("status") == "approved"


def send_challenge(phone, purpose, username=None, password_hash=None):
    if not twilio_configured():
        return json_error("WhatsApp OTP is not configured. Set the Twilio Verify environment variables.", 503)
    recent = OTPChallenge.query.filter_by(phone=phone, purpose=purpose).order_by(OTPChallenge.id.desc()).first()
    if recent and recent.created_at and (datetime.now(timezone.utc) - recent.created_at.replace(tzinfo=timezone.utc)).total_seconds() < 45:
        return json_error("Please wait 45 seconds before requesting another OTP.", 429)
    if not twilio_verify(phone):
        return json_error("Could not send WhatsApp OTP. Check the Twilio Verify service and WhatsApp sender.", 502)
    db.session.add(OTPChallenge(
        phone=phone, purpose=purpose, username=username, password_hash=password_hash,
        created_at=datetime.now(timezone.utc), consumed=False,
    ))
    db.session.commit()
    return jsonify({"success": True, "message": "WhatsApp OTP sent. It expires according to your Twilio Verify service settings."})


def latest_challenge(phone, purpose):
    challenge = OTPChallenge.query.filter_by(phone=phone, purpose=purpose, consumed=False).order_by(OTPChallenge.id.desc()).first()
    if not challenge or not challenge.created_at:
        return None
    created = challenge.created_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - created > timedelta(minutes=10):
        challenge.consumed = True
        db.session.commit()
        return None
    return challenge


@auth_bp.post("/signup/start")
def signup_start():
    data = body()
    username = str(data.get("username", "")).strip()
    password = data.get("password", "")
    phone = str(data.get("phone", "")).strip()
    if not USERNAME_RE.fullmatch(username):
        return json_error("Username must be 3–24 characters and use only letters, numbers, or underscores.")
    if not isinstance(password, str) or len(password) < 10 or len(password) > 128:
        return json_error("Password must be 10–128 characters.")
    if not valid_phone(phone):
        return json_error("Enter your WhatsApp number in international format, e.g. +919876543210.")
    if User.query.filter(func.lower(User.username) == username.lower()).first():
        return json_error("That username is already taken.", 409)
    if User.query.filter_by(phone=phone).first():
        return json_error("That phone number already has an account. Log in or reset your password.", 409)
    return send_challenge(phone, "signup", username.lower(), generate_password_hash(password))


@auth_bp.post("/signup/verify")
def signup_verify():
    data = body()
    phone = str(data.get("phone", "")).strip()
    code = str(data.get("code", "")).strip()
    if not valid_phone(phone) or not re.fullmatch(r"\d{4,10}", code):
        return json_error("Enter the phone number and OTP code.")
    challenge = latest_challenge(phone, "signup")
    if not challenge:
        return json_error("Your sign-up OTP expired. Request a new one.", 410)
    if not twilio_check(phone, code):
        return json_error("OTP is invalid or expired.", 401)
    if User.query.filter(func.lower(User.username) == challenge.username.lower()).first() or User.query.filter_by(phone=phone).first():
        challenge.consumed = True
        db.session.commit()
        return json_error("Username or phone number is already registered. Please log in.", 409)
    user = User(username=challenge.username, phone=phone, password_hash=challenge.password_hash)
    challenge.consumed = True
    db.session.add(user)
    db.session.commit()
    session.clear()
    session["user_id"] = user.id
    session.permanent = True
    return jsonify({"success": True, "username": user.username})


@auth_bp.post("/login")
def login():
    data = body()
    username = str(data.get("username", "")).strip()
    password = data.get("password", "")
    if not username or not isinstance(password, str):
        return json_error("Enter your username and password.")
    user = User.query.filter(func.lower(User.username) == username.lower()).first()
    if not user or not check_password_hash(user.password_hash, password):
        return json_error("Incorrect username or password.", 401)
    session.clear()
    session["user_id"] = user.id
    session.permanent = True
    return jsonify({"success": True, "username": user.username})


@auth_bp.post("/forgot/start")
def forgot_start():
    data = body()
    phone = str(data.get("phone", "")).strip()
    if not valid_phone(phone):
        return json_error("Enter the WhatsApp number linked to your account.")
    user = User.query.filter_by(phone=phone).first()
    if not user:
        # Avoid confirming whether a phone number is registered.
        return jsonify({"success": True, "message": "If the number is registered, a WhatsApp OTP will be sent."})
    return send_challenge(phone, "reset", user.username)


@auth_bp.post("/forgot/verify")
def forgot_verify():
    data = body()
    phone = str(data.get("phone", "")).strip()
    code = str(data.get("code", "")).strip()
    password = data.get("new_password", "")
    if not valid_phone(phone) or not re.fullmatch(r"\d{4,10}", code):
        return json_error("Enter the phone number and OTP code.")
    if not isinstance(password, str) or len(password) < 10 or len(password) > 128:
        return json_error("New password must be 10–128 characters.")
    challenge = latest_challenge(phone, "reset")
    if not challenge:
        return json_error("Your reset OTP expired. Request a new one.", 410)
    if not twilio_check(phone, code):
        return json_error("OTP is invalid or expired.", 401)
    user = User.query.filter_by(phone=phone).first()
    if not user:
        challenge.consumed = True
        db.session.commit()
        return json_error("Could not reset password. Start again.", 400)
    user.password_hash = generate_password_hash(password)
    challenge.consumed = True
    db.session.commit()
    session.clear()
    session["user_id"] = user.id
    session.permanent = True
    return jsonify({"success": True, "username": user.username})


@auth_bp.get("/me")
def me():
    user_id = session.get("user_id")
    if not user_id:
        return json_error("Not signed in.", 401)
    user = db.session.get(User, user_id)
    if not user:
        session.clear()
        return json_error("Not signed in.", 401)
    return jsonify({"success": True, "username": user.username})


@auth_bp.post("/logout")
def logout():
    session.clear()
    response = jsonify({"success": True})
    response.headers["Cache-Control"] = "no-store"
    return response
