"""Unit tests for export_nodes module."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.export_nodes import fetch_from_map_api, nodes_to_geojson, save_geojson


# ---------------------------------------------------------------------------
# Shared GeoJSON schema validator
# ---------------------------------------------------------------------------

REQUIRED_PROPS = {"id", "name", "type", "rssi", "snr", "battery", "timestamp"}


def assert_valid_feature_collection(tc: unittest.TestCase, geojson: dict, min_count: int = 0):
    tc.assertEqual(geojson["type"], "FeatureCollection")
    tc.assertIn("features", geojson)
    tc.assertGreaterEqual(len(geojson["features"]), min_count)

    for feat in geojson["features"]:
        tc.assertEqual(feat["type"], "Feature")
        geom = feat["geometry"]
        tc.assertEqual(geom["type"], "Point")
        coords = geom["coordinates"]
        tc.assertEqual(len(coords), 3, "coordinates must be [lon, lat, alt]")
        tc.assertIsInstance(coords[0], float)
        tc.assertIsInstance(coords[1], float)
        tc.assertIsInstance(coords[2], float)

        props = feat["properties"]
        for key in REQUIRED_PROPS:
            tc.assertIn(key, props, f"property '{key}' missing from feature")


# ---------------------------------------------------------------------------
# nodes_to_geojson tests
# ---------------------------------------------------------------------------

class TestNodesToGeoJSON(unittest.TestCase):

    def _sample_nodes(self):
        return [
            {
                "id": "node_001",
                "name": "Repeater Alpha",
                "latitude": 45.5152,
                "longitude": -122.6784,
                "altitude": 150.0,
                "type": "Repeater",
                "rssi": -95.0,
                "snr": 5.0,
                "battery": 100.0,
                "timestamp": "2026-01-01T00:00:00",
            },
            {
                "id": "node_002",
                "name": "Client Beta",
                "latitude": 45.5200,
                "longitude": -122.6700,
                "altitude": 100.0,
                "type": "Client",
                "rssi": -110.0,
                "snr": None,
                "battery": None,
                "timestamp": "2026-01-01T00:01:00",
            },
        ]

    def test_feature_collection_structure(self):
        geojson = nodes_to_geojson(self._sample_nodes())
        assert_valid_feature_collection(self, geojson, min_count=2)

    def test_coordinate_order_is_lon_lat_alt(self):
        geojson = nodes_to_geojson(self._sample_nodes())
        coords = geojson["features"][0]["geometry"]["coordinates"]
        self.assertAlmostEqual(coords[0], -122.6784)
        self.assertAlmostEqual(coords[1], 45.5152)
        self.assertAlmostEqual(coords[2], 150.0)

    def test_null_optional_fields_allowed(self):
        geojson = nodes_to_geojson(self._sample_nodes())
        props = geojson["features"][1]["properties"]
        self.assertIsNone(props["snr"])
        self.assertIsNone(props["battery"])

    def test_metadata_count_matches_features(self):
        nodes = self._sample_nodes()
        geojson = nodes_to_geojson(nodes)
        self.assertEqual(geojson["metadata"]["count"], len(nodes))

    def test_empty_node_list(self):
        geojson = nodes_to_geojson([])
        self.assertEqual(geojson["features"], [])
        self.assertEqual(geojson["metadata"]["count"], 0)

    def test_invalid_coordinate_skipped(self):
        nodes = [
            {"id": "bad", "name": "Bad", "latitude": "not_a_float",
             "longitude": -122.0, "altitude": 0},
        ]
        geojson = nodes_to_geojson(nodes)
        self.assertEqual(len(geojson["features"]), 0)


# ---------------------------------------------------------------------------
# save_geojson tests
# ---------------------------------------------------------------------------

class TestSaveGeoJSON(unittest.TestCase):

    def test_creates_valid_json_file(self):
        with tempfile.NamedTemporaryFile(suffix=".geojson", delete=False) as tmp:
            path = tmp.name
        result = save_geojson([], path)
        self.assertTrue(result)
        with open(path) as f:
            loaded = json.load(f)
        self.assertEqual(loaded["type"], "FeatureCollection")

    def test_overwrites_existing_file(self):
        with tempfile.NamedTemporaryFile(suffix=".geojson", mode="w", delete=False) as tmp:
            tmp.write('{"old": "data"}')
            path = tmp.name
        save_geojson([], path)
        with open(path) as f:
            loaded = json.load(f)
        self.assertNotIn("old", loaded)


# ---------------------------------------------------------------------------
# fetch_from_map_api tests (msgpack responses mocked correctly)
# ---------------------------------------------------------------------------

class TestFetchFromMapAPI(unittest.TestCase):

    def _make_msgpack_response(self, nodes: list) -> MagicMock:
        import msgpack
        mock = MagicMock()
        mock.content = msgpack.packb(nodes, use_bin_type=True)
        mock.raise_for_status.return_value = None
        return mock

    def _pk(self, hex_str: str) -> bytes:
        return bytes.fromhex(hex_str)

    @patch("scripts.export_nodes.requests")
    def test_repeater_node_decoded(self, mock_requests):
        mock_requests.get.return_value = self._make_msgpack_response([
            {"pk": self._pk("aabbccdd" * 8), "n": "Node1", "t": 2,
             "lat": 45.5, "lon": -122.6},
        ])
        nodes = fetch_from_map_api()
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["type"], "Repeater")
        self.assertAlmostEqual(nodes[0]["latitude"], 45.5)

    @patch("scripts.export_nodes.requests")
    def test_client_node_type_label(self, mock_requests):
        mock_requests.get.return_value = self._make_msgpack_response([
            {"pk": self._pk("11223344" * 8), "n": "Client1", "t": 1,
             "lat": 45.6, "lon": -122.7},
        ])
        nodes = fetch_from_map_api()
        self.assertEqual(nodes[0]["type"], "Client")

    @patch("scripts.export_nodes.requests")
    def test_null_island_filtered(self, mock_requests):
        mock_requests.get.return_value = self._make_msgpack_response([
            {"pk": self._pk("00000000" * 8), "n": "Bad", "t": 2, "lat": 0.0, "lon": 0.0},
            {"pk": self._pk("deadbeef" * 8), "n": "Good", "t": 2, "lat": 45.0, "lon": -122.0},
        ])
        nodes = fetch_from_map_api()
        self.assertEqual(len(nodes), 1)
        self.assertAlmostEqual(nodes[0]["latitude"], 45.0)

    @patch("scripts.export_nodes.requests")
    def test_request_exception_returns_empty(self, mock_requests):
        mock_requests.get.side_effect = Exception("network error")
        nodes = fetch_from_map_api()
        self.assertEqual(nodes, [])

    @patch("scripts.export_nodes.requests")
    def test_missing_coords_skipped(self, mock_requests):
        mock_requests.get.return_value = self._make_msgpack_response([
            {"pk": self._pk("aabbccdd" * 8), "n": "NoCoords", "t": 2},
        ])
        nodes = fetch_from_map_api()
        self.assertEqual(nodes, [])


if __name__ == "__main__":
    unittest.main()
