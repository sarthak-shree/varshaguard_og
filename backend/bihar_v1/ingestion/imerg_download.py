"""Configurable NASA GPM IMERG CSV-export acquisition.

This connector downloads only an explicitly configured CSV export. It does not pretend
that raw IMERG HDF5/NetCDF granules are CSV, and it never fabricates a URL or credentials.
Set VARSHAGUARD_IMERG_CSV_URL to a provider-approved CSV export endpoint. Earthdata Basic
Auth is optional when that endpoint requires it. Raw data is written atomically only after
size and schema checks pass.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests

from .imerg import normalize_precipitation

MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class IMERGDownloadError(RuntimeError):
    """Raised when the configured IMERG export cannot be safely acquired."""


def _credentials():
    username = os.getenv("NASA_EARTHDATA_USERNAME", "").strip()
    password = os.getenv("NASA_EARTHDATA_PASSWORD", "")
    if bool(username) != bool(password):
        raise IMERGDownloadError("Both NASA_EARTHDATA_USERNAME and NASA_EARTHDATA_PASSWORD are required")
    return (username, password) if username and password else None


def download_csv_export(
    destination: str | Path,
    *,
    url: str | None = None,
    session=None,
    retries: int = 3,
    timeout: int = 30,
) -> dict:
    """Download, validate and atomically persist a normalized-column IMERG CSV export."""
    source_url = (url or os.getenv("VARSHAGUARD_IMERG_CSV_URL", "")).strip()
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise IMERGDownloadError("Set VARSHAGUARD_IMERG_CSV_URL to an approved HTTPS CSV export URL")
    if not 0 <= retries <= 5 or timeout <= 0:
        raise ValueError("retries must be 0..5 and timeout must be positive")

    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".part")
    client = session or requests
    last_error = None
    try:
        for attempt in range(retries + 1):
            try:
                response = client.get(
                    source_url,
                    headers={"Accept": "text/csv, application/octet-stream", "User-Agent": "VarshaGuard/1.0"},
                    auth=_credentials(),
                    timeout=timeout,
                )
                if response.status_code in RETRYABLE_STATUS and attempt < retries:
                    retry_after = response.headers.get("Retry-After", "")
                    try:
                        delay = min(8.0, max(0.0, float(retry_after)))
                    except ValueError:
                        delay = min(8.0, 0.5 * (2 ** attempt))
                    time.sleep(delay)
                    continue
                response.raise_for_status()
                payload = response.content
                if not payload or len(payload) > MAX_DOWNLOAD_BYTES:
                    raise IMERGDownloadError("IMERG export is empty or exceeds the 100 MiB safety limit")
                # Refuse login/error HTML saved under a .csv filename.
                content_type = response.headers.get("Content-Type", "").lower()
                prefix = payload[:256].lstrip().lower()
                if "text/html" in content_type or prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html"):
                    raise IMERGDownloadError("IMERG endpoint returned HTML, not a CSV export")
                try:
                    frame = pd.read_csv(__import__("io").BytesIO(payload))
                    records = normalize_precipitation(frame)
                except (ValueError, pd.errors.ParserError, UnicodeDecodeError) as exc:
                    raise IMERGDownloadError(f"IMERG CSV schema validation failed: {exc}") from exc
                if not records:
                    raise IMERGDownloadError("IMERG export contains no valid observation records")
                # Persist only after full parsing/validation; preserve the provider CSV bytes.
                temporary.write_bytes(payload)
                temporary.replace(target)
                return {
                    "status": "downloaded",
                    "source": "nasa_gpm_imerg",
                    "rows_validated": len(records),
                    "bytes": len(payload),
                    "path": str(target),
                    "sha256": __import__("hashlib").sha256(payload).hexdigest(),
                }
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= retries:
                    break
                time.sleep(min(8.0, 0.5 * (2 ** attempt)))
        raise IMERGDownloadError(f"IMERG download failed after {retries + 1} attempts") from last_error
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    import argparse
    import json
    parser = argparse.ArgumentParser(description="Download and validate a configured IMERG CSV export")
    parser.add_argument("--output", default="data/raw/imerg/imerg_export.csv")
    args = parser.parse_args()
    result = download_csv_export(args.output)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
