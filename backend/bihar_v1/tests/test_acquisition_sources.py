import unittest

from backend.bihar_v1.acquisition_sources import (
    acquisition_source,
    list_acquisition_sources,
)


class AcquisitionSourceTests(unittest.TestCase):
    def test_catalog_does_not_claim_local_availability(self):
        sources = list_acquisition_sources()
        self.assertEqual(
            {item["name"] for item in sources},
            {
                "imerg_early",
                "imd_api",
                "cwc_floodwatch",
                "district_boundary_nwic",
                "sentinel1_copernicus",
                "srtm_1arcsec",
            },
        )
        boundary = acquisition_source("district_boundary_nwic")
        self.assertFalse(boundary.registration_required)
        self.assertEqual(boundary.local_contract_name, "district_boundaries")

    def test_unknown_source_rejected(self):
        with self.assertRaises(ValueError):
            acquisition_source("missing")


if __name__ == "__main__":
    unittest.main()
