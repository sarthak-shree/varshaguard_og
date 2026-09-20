"""IMD ingestion boundary.

Keep provider-specific parsing here so prediction code never depends on raw API payloads.
"""
from typing import Any

import requests

from ..config import IMD_BASE_URL


def fetch_json(path: str, *, params: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    url = f"{IMD_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def current_weather(params: dict[str, Any] | None = None) -> Any:
    return fetch_json("current_wx", params=params)


def district_rainfall(params: dict[str, Any] | None = None) -> Any:
    return fetch_json("districtrainfall", params=params)


def district_nowcast(params: dict[str, Any] | None = None) -> Any:
    return fetch_json("districtnowcast", params=params)


def district_warning(params: dict[str, Any] | None = None) -> Any:
    return fetch_json("districtwarning", params=params)
