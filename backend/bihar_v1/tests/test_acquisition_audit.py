import tempfile
import unittest
from pathlib import Path

from backend.bihar_v1.acquisition_audit import audit_sources


class AcquisitionAuditTests(unittest.TestCase):
    def test_audit_exposes_blocked_contract_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.csv"
            path.write_text("Start Date,End Date,Bihar District\n", encoding="utf-8")
            report = audit_sources({"flood_events": path})

        self.assertEqual(report["data_acquisition_contract"]["status"], "blocked")
        self.assertEqual(
            report["data_acquisition_contract"]["sources"]["flood_events"]["status"],
            "ready",
        )
        self.assertEqual(
            report["raw_source_manifest"]["sources"]["flood_events"]["status"],
            "present",
        )
        self.assertIsNotNone(
            report["raw_source_manifest"]["sources"]["flood_events"]["sha256"]
        )
        self.assertEqual(report["raw_source_manifest_validation"]["status"], "valid")


if __name__ == "__main__":
    unittest.main()
