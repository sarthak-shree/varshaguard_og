"""Checks the "Sign in with Google" token the browser sends us.

The browser gets a signed ID token from Google. We never trust it as-is: Google's
library checks the signature, expiry, issuer, and that the token was issued for
OUR client ID (so a token made for some other site is rejected).
"""
import os

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

_request = google_requests.Request()


class InvalidGoogleToken(ValueError):
    """The token is not a valid, current Google sign-in for this site."""


def client_id() -> str:
    return os.getenv("GOOGLE_CLIENT_ID", "").strip()


def verify(credential: str) -> dict:
    """Return {sub, email, name, picture} for a valid token, else raise InvalidGoogleToken."""
    cid = client_id()
    try:
        claims = id_token.verify_oauth2_token(credential, _request, cid)
    except Exception as exc:  # bad signature, expired, wrong audience, Google unreachable...
        raise InvalidGoogleToken(str(exc)) from exc

    if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise InvalidGoogleToken("wrong issuer")
    if not claims.get("sub") or not claims.get("email"):
        raise InvalidGoogleToken("token has no account id or email")
    if claims.get("email_verified") is not True:
        raise InvalidGoogleToken("Google has not verified this email address")

    email = claims["email"].strip().lower()
    name = (claims.get("name") or claims.get("given_name") or email.split("@")[0]).strip()
    return {
        "sub": claims["sub"],
        "email": email,
        "name": name[:80],
        "picture": claims.get("picture") or None,
    }
