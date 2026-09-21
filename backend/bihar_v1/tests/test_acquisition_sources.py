import unittest

from backend.bihar_v1.acquisition_sources import (
    acquisition_source,
    list_acquisition_sources,
)


class AcquisitionSourceTests(unittest.TestCase):
    def test_catalog_does_not_claim_local_availability(self):
        sources = list_acquisition_sources()
        self.assertEqual({item["name"] for item in sources}, {"imerg_early", "imd_api", "cwc_floodwatch", "sentinel1_copernicus", "srtm_1arcsec"})
        self.assertTrue(all(item["registration_required"] for item in sources))

    def test_unknown_source_rejected(self):
        with self.assertRaises(ValueError):
            acquisition_source("missing")


if __name__ == "__main__":
    unittest.main()
