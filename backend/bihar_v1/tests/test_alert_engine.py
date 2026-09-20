import unittest
from dataclasses import replace

from backend.bihar_v1.schemas import RiskState
from backend.bihar_v1.services.alert_engine import build_alert


class AlertEngineTests(unittest.TestCase):
    def test_not_ready_is_inactive(self):
        alert = build_alert(RiskState(district="patna", risk_level="not_ready"))
        self.assertFalse(alert["active"])

    def test_low_risk_is_inactive(self):
        alert = build_alert(RiskState(district="patna", risk_level="low"))
        self.assertFalse(alert["active"])

    def test_moderate_and_high_are_active(self):
        for level in ("moderate", "high"):
            alert = build_alert(RiskState(district="patna", risk_level=level))
            self.assertTrue(alert["active"])
            self.assertEqual(alert["risk_level"], level)

    def test_invalid_risk_level_fails_closed(self):
        alert = build_alert(RiskState(district="patna", risk_level="critical"))
        self.assertFalse(alert["active"])
        self.assertEqual(alert["reason"], "invalid risk level")


if __name__ == "__main__":
    unittest.main()
