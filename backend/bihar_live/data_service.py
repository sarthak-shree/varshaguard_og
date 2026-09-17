"""Live Bihar river-station data service.

Bihar Live must never read the dated ML/training CSV. It fetches current
river observations from Bihar's flood-monitoring web feed at request time.
Source timestamps are retained in the backend response for audit/debugging
but are intentionally not shown in the public station table.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

import requests


# These feeds publish Bihar river/CWC station observations independently of
# India-WRIS. The first is the Bihar Flood Management Information System real-
# time alert page; the second is the Bihar WRD CWC-station table as a fallback.
LIVE_SOURCE_URLS = (
    "https://beams.fmiscwrdbihar.gov.in/Alerttotalinfo/realtimetotal.aspx",
    "https://irrigation.befiqr.in/state/table/cwc-stations",
)
REQUEST_TIMEOUT_SECONDS = 12


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _number(value: Any) -> float | None:
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


class _TableParser(HTMLParser):
    """Small dependency-free HTML table parser for the Bihar government feed."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append(_clean("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
            self._cell = None


def _parse_html_rows(html: str) -> list[dict[str, str]]:
    parser = _TableParser()
    parser.feed(html)

    rows = [row for row in parser.rows if len(row) >= 8]
    if not rows:
        return []

    header_index = None
    for index, row in enumerate(rows):
        joined = " ".join(row).lower()
        if "station name" in joined and "current" in joined and "water level" in joined:
            header_index = index
            break
        if "station" in joined and "current level" in joined and "danger" in joined:
            header_index = index
            break

    if header_index is None:
        return []

    headers = rows[header_index]
    result: list[dict[str, str]] = []
    for row in rows[header_index + 1 :]:
        if len(row) < len(headers):
            continue
        result.append({headers[i]: row[i] for i in range(len(headers))})
    return result


def _find_value(row: dict[str, str], *needles: str) -> str | None:
    normalized = {key.lower(): value for key, value in row.items()}
    for needle in needles:
        for key, value in normalized.items():
            if needle in key and value not in (None, ""):
                return value
    return None


def _normalize_beams_row(row: dict[str, str]) -> dict | None:
    station = _find_value(row, "station name")
    river = _find_value(row, "river")
    district = _find_value(row, "district")
    level = _number(_find_value(row, "current observed water level", "current level"))
    previous = _number(_find_value(row, "1 hr before", "yesterday level"))
    warning = _number(_find_value(row, "warning level"))
    danger = _number(_find_value(row, "danger level"))
    hfl = _number(_find_value(row, "hfl"))
    observed = _find_value(row, "current observed date", "date & time")
    trend = _find_value(row, "trend")

    if not station or level is None:
        return None

    return {
        "station": station,
        "river": river or "",
        "district": district or "",
        "water_level_m": level,
        "warning_level_m": warning,
        "danger_level_m": danger,
        "hfl_m": hfl,
        "water_level_1h_before_m": previous,
        "rise_1h_m": round(level - previous, 4) if previous is not None else None,
        "trend": trend or "",
        "observed": observed,
    }


def _normalize_wrd_row(row: dict[str, str]) -> dict | None:
    station = _find_value(row, "station name", "site")
    river = _find_value(row, "river")
    district = _find_value(row, "district / block", "district")
    level = _number(_find_value(row, "current level", "current observed water level"))
    previous = _number(_find_value(row, "yesterday level", "yesterday observed water level"))
    danger = _number(_find_value(row, "dl"))
    hfl = _number(_find_value(row, "hfl"))
    observed = _find_value(row, "date & time")
    trend = _find_value(row, "trend")

    if not station or level is None:
        return None

    return {
        "station": station,
        "river": river or "",
        "district": district or "",
        "water_level_m": level,
        "warning_level_m": None,
        "danger_level_m": danger,
        "hfl_m": hfl,
        "water_level_1h_before_m": previous,
        "rise_1h_m": round(level - previous, 4) if previous is not None else None,
        "trend": trend or "",
        "observed": observed,
    }


def _fetch_source(url: str) -> list[dict]:
    response = requests.get(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "VARSHAGUARD/1.0",
            "Cache-Control": "no-cache, no-store",
            "Pragma": "no-cache",
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    rows = _parse_html_rows(response.text)
    if not rows:
        raise ValueError("No recognizable Bihar station table found")

    if "station name" in " ".join(rows[0]).lower():
        normalized = [_normalize_beams_row(row) for row in rows]
    else:
        normalized = [_normalize_wrd_row(row) for row in rows]

    stations = [item for item in normalized if item]
    if not stations:
        raise ValueError("Live source returned no usable Bihar station rows")
    return stations


def fetch_live_data() -> dict:
    """Fetch current Bihar station observations at request time.

    No repository CSV/fixture is used here. If all live sources fail, raise an
    error rather than silently serving stale data.
    """
    errors: list[str] = []

    for url in LIVE_SOURCE_URLS:
        try:
            stations = _fetch_source(url)
            seen: set[str] = set()
            unique = []
            for station in stations:
                key = station["station"].strip().lower()
                if key not in seen:
                    seen.add(key)
                    unique.append(station)

            unique.sort(key=lambda row: row["station"].lower())
            return {
                "success": True,
                "source": "Bihar FMIS / WRD live river observations",
                "source_url": url,
                "fetched_at": _utc_now(),
                "stations": unique,
            }
        except Exception as error:
            errors.append(f"{url}: {error}")

    raise RuntimeError("Live Bihar station feed unavailable; " + " | ".join(errors))
