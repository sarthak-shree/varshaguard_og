"""Authenticated, bounded IMD ingestion boundary.

The IMD API contract and credential format vary by access arrangement. This adapter
supports a configured bearer token (or custom API-key header), retries transient
failures, and validates JSON shape. It deliberately does not invent provider schemas.
"""
from __future__ import annotations

import os
import time
from typing import Any

import requests

from ..config import IMD_BASE_URL

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class IMDIngestionError(RuntimeError):
    """Raised when IMD data cannot be fetched or parsed safely."""


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    token = os.getenv("IMD_API_TOKEN", "").strip()
    api_key = os.getenv("IMD_API_KEY", "").strip()
    api_key_header = os.getenv("IMD_API_KEY_HEADER", "X-API-Key").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif api_key:
        if not api_key_header or api_key_header.lower() in {"host", "content-length"}:
            raise IMDIngestionError("IMD_API_KEY_HEADER is invalid")
        headers[api_key_header] = api_key
    return headers


def _validate_payload(payload: Any) -> Any:
    if not isinstance(payload, (dict, list)):
        raise IMDIngestionError("IMD returned an unexpected JSON root type")
    if isinstance(payload, dict) and payload.get("status") == "error":
        raise IMDIngestionError("IMD returned an error payload")
    return payload


def fetch_json(
    path: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: int = 20,
    retries: int | None = None,
    session: requests.Session | None = None,
) -> Any:
    """Fetch a JSON endpoint with bounded exponential retry and response checks."""
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    max_retries = int(os.getenv("IMD_MAX_RETRIES", "3")) if retries is None else retries
    if not 0 <= max_retries <= 5:
        raise ValueError("retries must be between 0 and 5")
    url = f"{IMD_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    client = session or requests
    for attempt in range(max_retries + 1):
        try:
            response = client.get(url, params=params, headers=_headers(), timeout=timeout)
            if response.status_code in RETRYABLE_STATUS and attempt < max_retries:
                retry_after = response.headers.get("Retry-After", "")
                try:
                    delay = min(8.0, max(0.0, float(retry_after)))
                except ValueError:
                    delay = min(8.0, 0.5 * (2 ** attempt))
                time.sleep(delay)
                continue
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError as exc:
                raise IMDIngestionError("IMD response was not valid JSON") from exc
            return _validate_payload(payload)
        except requests.RequestException as exc:
            if attempt >= max_retries:
                raise IMDIngestionError(f"IMD request failed after {attempt + 1} attempts") from exc
            time.sleep(min(8.0, 0.5 * (2 ** attempt)))
    raise IMDIngestionError("IMD request failed")


def current_weather(params: dict[str, Any] | None = None) -> Any:
    return fetch_json("current_wx", params=params)


def district_rainfall(params: dict[str, Any] | None = None) -> Any:
    return fetch_json("districtrainfall", params=params)


def district_nowcast(params: dict[str, Any] | None = None) -> Any:
    return fetch_json("districtnowcast", params=params)


def district_warning(params: dict[str, Any] | None = None) -> Any:
    return fetch_json("districtwarning", params=params)
