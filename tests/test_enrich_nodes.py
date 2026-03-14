"""Unit tests for enrich_nodes pure-math functions.

These tests cover haversine_km, fspl_db, bearing_degrees, bearing_to_sector,
latlon_to_pixel, and pixel_area_km2 without requiring QGIS or GDAL.
"""

import math
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Stub out osgeo so the module imports without GDAL installed
sys.modules.setdefault("osgeo", MagicMock())
sys.modules.setdefault("osgeo.gdal", MagicMock())

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

# Patch gdal at import time so enrich_nodes loads cleanly
with patch.dict("sys.modules", {"osgeo": MagicMock(), "osgeo.gdal": MagicMock()}):
    from plugin.meshcore_viewshed.core.enrich_nodes import (
        bearing_degrees,
        bearing_to_sector,
        fspl_db,
        haversine_km,
        latlon_to_pixel,
        pixel_area_km2,
    )


class TestHaversineKm(unittest.TestCase):
    def test_same_point_is_zero(self):
        self.assertAlmostEqual(haversine_km(45.5, -122.7, 45.5, -122.7), 0.0, places=6)

    def test_known_distance_portland_seattle(self):
        # Portland, OR → Seattle, WA ≈ 233 km (straight-line haversine)
        d = haversine_km(45.5231, -122.6765, 47.6062, -122.3321)
        self.assertAlmostEqual(d, 233.0, delta=5.0)

    def test_one_degree_latitude(self):
        # On a spherical earth (R=6371 km), 1° latitude = 111.195 km
        d = haversine_km(0.0, 0.0, 1.0, 0.0)
        self.assertAlmostEqual(d, 111.2, delta=0.5)

    def test_symmetry(self):
        a = haversine_km(45.5, -122.7, 47.6, -122.3)
        b = haversine_km(47.6, -122.3, 45.5, -122.7)
        self.assertAlmostEqual(a, b, places=6)


class TestFsplDb(unittest.TestCase):
    def test_formula_at_1km_910mhz(self):
        # FSPL = 32.45 + 20*log10(910) + 20*log10(1) = 32.45 + 59.18 + 0 = 91.63
        expected = 32.45 + 20 * math.log10(910) + 20 * math.log10(1.0)
        self.assertAlmostEqual(fspl_db(1.0, 910), expected, places=5)

    def test_doubles_with_distance(self):
        # Doubling distance adds ~6 dB
        loss_1km = fspl_db(1.0, 910)
        loss_2km = fspl_db(2.0, 910)
        self.assertAlmostEqual(loss_2km - loss_1km, 6.021, delta=0.01)

    def test_increases_with_frequency(self):
        self.assertGreater(fspl_db(1.0, 2400), fspl_db(1.0, 910))


class TestBearingDegrees(unittest.TestCase):
    def test_north(self):
        # Due north: bearing should be 0
        b = bearing_degrees(0.0, 0.0, 1.0, 0.0)
        self.assertAlmostEqual(float(b), 0.0, delta=0.1)

    def test_south(self):
        b = bearing_degrees(1.0, 0.0, 0.0, 0.0)
        self.assertAlmostEqual(float(b), 180.0, delta=0.1)

    def test_east(self):
        b = bearing_degrees(0.0, 0.0, 0.0, 1.0)
        self.assertAlmostEqual(float(b), 90.0, delta=0.1)

    def test_west(self):
        b = bearing_degrees(0.0, 1.0, 0.0, 0.0)
        self.assertAlmostEqual(float(b), 270.0, delta=0.1)

    def test_vectorised_cardinals(self):
        from_lat, from_lon = 0.0, 0.0
        to_lats = np.array([1.0, 0.0, -1.0, 0.0])
        to_lons = np.array([0.0, 1.0,  0.0, -1.0])
        expected = np.array([0.0, 90.0, 180.0, 270.0])
        result = bearing_degrees(from_lat, from_lon, to_lats, to_lons)
        np.testing.assert_allclose(result, expected, atol=0.1)


class TestBearingToSector(unittest.TestCase):
    """bearing_to_sector maps 0-360° to sector indices 0..n_sectors-1."""

    def test_north_is_sector_0(self):
        arr = np.array([0.0])
        self.assertEqual(int(bearing_to_sector(arr, 8)[0]), 0)

    def test_east_is_sector_2(self):
        arr = np.array([90.0])
        self.assertEqual(int(bearing_to_sector(arr, 8)[0]), 2)

    def test_south_is_sector_4(self):
        arr = np.array([180.0])
        self.assertEqual(int(bearing_to_sector(arr, 8)[0]), 4)

    def test_west_is_sector_6(self):
        arr = np.array([270.0])
        self.assertEqual(int(bearing_to_sector(arr, 8)[0]), 6)

    def test_four_sectors(self):
        arr = np.array([0.0, 90.0, 180.0, 270.0])
        result = bearing_to_sector(arr, 4)
        np.testing.assert_array_equal(result, [0, 1, 2, 3])


class TestLatLonToPixel(unittest.TestCase):
    """latlon_to_pixel converts geo coords to (row, col) using a GeoTransform."""

    def _make_gt(self, origin_lon=-123.0, origin_lat=46.0, res=0.001):
        # GeoTransform: (x_min, px_width, 0, y_max, 0, -px_height)
        return (origin_lon, res, 0.0, origin_lat, 0.0, -res)

    def test_origin_is_row0_col0(self):
        gt = self._make_gt()
        row, col = latlon_to_pixel(gt, lat=46.0, lon=-123.0)
        self.assertEqual(row, 0)
        self.assertEqual(col, 0)

    def test_offset_pixel(self):
        # Use res=0.1 (exactly representable in float) to avoid truncation edge cases
        gt = self._make_gt(origin_lon=-10.0, origin_lat=10.0, res=0.1)
        # 5 pixels east, 3 pixels south
        row, col = latlon_to_pixel(gt, lat=10.0 - 3 * 0.1, lon=-10.0 + 5 * 0.1)
        self.assertEqual(col, 5)
        self.assertEqual(row, 3)


class TestPixelAreaKm2(unittest.TestCase):
    def test_at_equator(self):
        # At equator, ~30m pixel: gt[1]=gt[5]≈0.000277 degrees ≈ 30m
        gt = (0, 0.000277, 0, 0, 0, -0.000277)
        area = pixel_area_km2(gt, lat=0.0)
        # ~0.030 km × 0.030 km ≈ 0.0009 km²
        self.assertAlmostEqual(area, 0.0009, delta=0.0001)

    def test_shrinks_toward_pole(self):
        gt = (0, 0.000277, 0, 0, 0, -0.000277)
        area_equator = pixel_area_km2(gt, lat=0.0)
        area_60n = pixel_area_km2(gt, lat=60.0)
        # x-dimension shrinks by cos(60°) = 0.5
        self.assertAlmostEqual(area_60n, area_equator * 0.5, delta=0.00005)


if __name__ == "__main__":
    unittest.main()
