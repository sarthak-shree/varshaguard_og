from unittest.mock import Mock, patch

import pytest

from backend.bihar_v1.ingestion.imerg_download import IMERGDownloadError, download_csv_export


CSV = b"timestamp,latitude,longitude,rainfall_mm\n2026-10-01T00:00:00Z,25.6,85.1,2.4\n"


def _response(payload=CSV, status=200, content_type="text/csv"):
    response = Mock()
    response.status_code = status
    response.headers = {"Content-Type": content_type}
    response.content = payload
    response.raise_for_status.return_value = None
    return response


def test_downloads_valid_csv_and_persists_atomically(tmp_path):
    session = Mock()
    session.get.return_value = _response()
    target = tmp_path / "imerg.csv"
    result = download_csv_export(target, url="https://example.test/export.csv", session=session, retries=0)
    assert result["status"] == "downloaded"
    assert result["rows_validated"] == 1
    assert target.read_bytes() == CSV
    assert not (tmp_path / "imerg.csv.part").exists()


def test_refuses_http_endpoint_and_does_not_write_file(tmp_path):
    target = tmp_path / "imerg.csv"
    with pytest.raises(IMERGDownloadError, match="HTTPS"):
        download_csv_export(target, url="http://example.test/export.csv")
    assert not target.exists()


def test_refuses_html_login_page(tmp_path):
    session = Mock()
    session.get.return_value = _response(b"<html>login</html>", content_type="text/html")
    with pytest.raises(IMERGDownloadError, match="HTML"):
        download_csv_export(tmp_path / "imerg.csv", url="https://example.test/export.csv", session=session, retries=0)


def test_retries_transient_status(tmp_path):
    failed = _response(status=503)
    success = _response()
    session = Mock()
    session.get.side_effect = [failed, success]
    with patch("backend.bihar_v1.ingestion.imerg_download.time.sleep"):
        result = download_csv_export(tmp_path / "imerg.csv", url="https://example.test/export.csv", session=session, retries=1)
    assert result["rows_validated"] == 1
    assert session.get.call_count == 2


def test_rejects_schema_mismatch_without_overwriting_existing_file(tmp_path):
    target = tmp_path / "imerg.csv"
    target.write_text("known-good", encoding="utf-8")
    session = Mock()
    session.get.return_value = _response(b"lat,lon,rain\n25.6,85.1,2.4\n")
    with pytest.raises(IMERGDownloadError, match="schema validation"):
        download_csv_export(target, url="https://example.test/export.csv", session=session, retries=0)
    assert target.read_text(encoding="utf-8") == "known-good"


def test_earthdata_auth_is_passed_only_when_configured(tmp_path):
    session = Mock()
    session.get.return_value = _response()
    with patch.dict("os.environ", {"NASA_EARTHDATA_USERNAME": "user", "NASA_EARTHDATA_PASSWORD": "pass"}):
        download_csv_export(tmp_path / "imerg.csv", url="https://example.test/export.csv", session=session, retries=0)
    assert session.get.call_args.kwargs["auth"] == ("user", "pass")
