"""Sends the one-time code over WhatsApp (Meta WhatsApp Cloud API).

Without WHATSAPP_TOKEN / WHATSAPP_PHONE_ID the app runs in DEV MODE and prints
the code in the server terminal instead of sending it. Dev mode is never used
in production (Vercel): a missing configuration makes login unavailable
rather than writing codes into server logs.
"""
import os

import requests

from .store import is_production

API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v20.0")


def is_configured() -> bool:
    return bool(os.getenv("WHATSAPP_TOKEN") and os.getenv("WHATSAPP_PHONE_ID"))


def is_dev_mode() -> bool:
    return not is_configured() and not is_production()


def can_send() -> bool:
    return is_configured() or is_dev_mode()


def send_otp(phone_e164: str, code: str) -> None:
    """phone_e164 looks like +919876543210. Raises RuntimeError if sending fails."""
    if not is_configured():
        if is_production():
            raise RuntimeError("WhatsApp is not configured")
        print(f"\n[DEV MODE] WhatsApp login code for {phone_e164}: {code}\n", flush=True)
        return

    token = os.environ["WHATSAPP_TOKEN"]
    phone_id = os.environ["WHATSAPP_PHONE_ID"]
    template = os.getenv("WHATSAPP_TEMPLATE", "varshaguard_otp")
    language = os.getenv("WHATSAPP_TEMPLATE_LANG", "en")

    # An Authentication template carries the code in its body and in its
    # "copy code" button, so the code is passed twice.
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_e164.lstrip("+"),
        "type": "template",
        "template": {
            "name": template,
            "language": {"code": language},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": code}]},
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [{"type": "text", "text": code}],
                },
            ],
        },
    }
    try:
        response = requests.post(
            f"https://graph.facebook.com/{API_VERSION}/{phone_id}/messages",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=10,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"WhatsApp request failed: {exc}") from exc

    if response.status_code >= 400:
        raise RuntimeError(f"WhatsApp API error {response.status_code}: {response.text[:300]}")
