"""Unit tests for export_nodes and meshtastic_fetcher modules."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Allow imports from scripts/ without installation
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.export_nodes import fetch_from_map_api, nodes_to_geojson, save_geojson
from scripts.meshtastic_fetcher import _merge_node, nodes_to_geojson as mt_nodes_to_geojson


# ---------------------------------------------------------------------------
# Shared GeoJSON schema validator
# ---------------------------------------------------------------------------

REQUIRED_PROPS = {"id", "name", "type", "rssi", "snr", "battery", "timestamp"}


def assert_valid_feature_collection(tc: unittest.TestCase, geojson: dict, min_count: int = 0):
    """Assert that a dict is a valid GeoJSON FeatureCollection with our schema."""
    tc.assertEqual(geojson["type"], "FeatureCollection")
    tc.assertIn("features", geojson)
    tc.assertGreaterEqual(len(geojson["features"]), min_count)

    for feat in geojson["features"]:
        tc.assertEqual(feat["type"], "Feature")
        geom = feat["geometry"]
        tc.assertEqual(geom["type"], "Point")
        coords = geom["coordinates"]
        tc.assertEqual(len(coords), 3, "coordinates must be [lon, lat, alt]")
        tc.assertIsInstance(coords[0], float)   # longitude
        tc.assertIsInstance(coords[1], float)   # latitude
        tc.assertIsInstance(coords[2], float)   # altitude

        props = feat["properties"]
        for key in REQUIRED_PROPS:
            tc.assertIn(key, props, f"property '{key}' missing from feature")


# ---------------------------------------------------------------------------
# export_nodes tests
# ---------------------------------------------------------------------------

class TestNodesToGeoJSON(unittest.TestCase):
    """Test nodes_to_geojson() from export_nodes."""

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
        feat = geojson["features"][0]
        coords = feat["geometry"]["coordinates"]
        self.assertAlmostEqual(coords[0], -122.6784)   # lon
        self.assertAlmostEqual(coords[1], 45.5152)     # lat
        self.assertAlmostEqual(coords[2], 150.0)       # alt

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


class TestSaveGeoJSON(unittest.TestCase):
    """Test save_geojson() from export_nodes."""

    def test_creates_valid_json_file(self):
        geojson = {"type": "FeatureCollection", "features": [], "metadata": {"count": 0}}
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


class TestFetchFromMapAPI(unittest.TestCase):
    """Test fetch_from_map_api() — network calls are mocked."""

    def _mock_response(self, data):
        mock = MagicMock()
        mock.json.return_value = data
        mock.raise_for_status.return_value = None
        return mock

    @patch("scripts.export_nodes.requests")
    def test_bare_list_response(self, mock_requests):
        mock_requests.get.return_value = self._mock_response([
            {"public_key": "key1", "name": "Node1", "device_role": 1,
             "latitude": 45.5, "longitude": -122.6, "altitude": 100},
        ])
        nodes = fetch_from_map_api()
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["type"], "Repeater")
        self.assertAlmostEqual(nodes[0]["latitude"], 45.5)

    @patch("scripts.export_nodes.requests")
    def test_wrapped_nodes_key_response(self, mock_requests):
        mock_requests.get.return_value = self._mock_response({
            "nodes": [
                {"public_key": "key2", "name": "Node2", "device_role": 2,
                 "latitude": 45.6, "longitude": -122.7},
            ]
        })
        nodes = fetch_from_map_api()
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["type"], "Companion")

    @patch("scripts.export_nodes.requests")
    def test_null_island_filtered(self, mock_requests):
        mock_requests.get.return_value = self._mock_response([
            {"public_key": "null_island", "name": "Bad", "latitude": 0.0, "longitude": 0.0},
            {"public_key": "good_node", "name": "Good", "latitude": 45.0, "longitude": -122.0},
        ])
        nodes = fetch_from_map_api()
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["id"], "good_node")

    @patch("scripts.export_nodes.requests")
    def test_request_exception_returns_empty(self, mock_requests):
        mock_requests.get.side_effect = Exception("network error")
        nodes = fetch_from_map_api()
        self.assertEqual(nodes, [])


# ---------------------------------------------------------------------------
# MeshCore MQTT message parsing (unit-level, no broker needed)
# ---------------------------------------------------------------------------

class TestMeshCoreMQTTHandling(unittest.TestCase):
    """Test mqtt_listener handle_message logic indirectly via MeshCoreMQTTListener."""

    def setUp(self):
        from scripts.mqtt_listener import MeshCoreMQTTListener
        self.listener = MeshCoreMQTTListener.__new__(MeshCoreMQTTListener)
        self.listener.broker = "test"
        self.listener.topics = ["meshcore/#"]
        self.listener.output_file = None
        self.listener.nodes = {}
        self.listener.client = None

    def test_valid_position_message(self):
        payload = json.dumps({
            "public_key": "abc123",
            "name": "Test Repeater",
            "device_role": 1,
            "latitude": 45.5,
            "longitude": -122.6,
            "altitude": 200.0,
        }).encode()
        self.listener.handle_message("meshcore/abc123/advert", payload)
        self.assertIn("abc123", self.listener.nodes)
        node = self.listener.nodes["abc123"]
        self.assertEqual(node["type"], "Repeater")
        self.assertAlmostEqual(node["latitude"], 45.5)

    def test_null_island_filtered(self):
        payload = json.dumps({
            "public_key": "nullkey",
            "name": "Null Island",
            "latitude": 0.0,
            "longitude": 0.0,
        }).encode()
        self.listener.handle_message("meshcore/nullkey/advert", payload)
        self.assertNotIn("nullkey", self.listener.nodes)

    def test_missing_coordinates_skipped(self):
        payload = json.dumps({"public_key": "nocoords", "name": "No Coords"}).encode()
        self.listener.handle_message("meshcore/nocoords/advert", payload)
        self.assertNotIn("nocoords", self.listener.nodes)

    def test_invalid_json_does_not_raise(self):
        self.listener.handle_message("meshcore/bad/advert", b"not valid json{{{")
        self.assertEqual(self.listener.nodes, {})


# ---------------------------------------------------------------------------
# Meshtastic fetcher tests
# ---------------------------------------------------------------------------

class TestMeshtasticMergeNode(unittest.TestCase):
    """Test _merge_node() state machine without a broker."""

    def test_nodeinfo_sets_name_and_type(self):
        state = {}
        _merge_node(state, "!deadbeef", "nodeinfo", {"longname": "My Node", "role": 4})
        self.assertEqual(state["!deadbeef"]["name"], "My Node")
        self.assertEqual(state["!deadbeef"]["type"], "Repeater")

    def test_position_decodes_integer_coords(self):
        state = {}
        _merge_node(state, "!deadbeef", "position", {
            "latitude_i": 455152000,
            "longitude_i": -1226784000,
            "altitude": 150,
        })
        node = state["!deadbeef"]
        self.assertAlmostEqual(node["latitude"], 45.5152, places=4)
        self.assertAlmostEqual(node["longitude"], -122.6784, places=4)
        self.assertEqual(node["altitude"], 150.0)

    def test_position_null_island_not_stored(self):
        state = {}
        _merge_node(state, "!nullnode", "position", {
            "latitude_i": 0,
            "longitude_i": 0,
        })
        self.assertNotIn("latitude", state.get("!nullnode", {}))

    def test_telemetry_sets_battery(self):
        state = {}
        _merge_node(state, "!aabbccdd", "telemetry", {"battery_level": 87})
        self.assertEqual(state["!aabbccdd"]["battery"], 87.0)

    def test_multiple_message_types_merged(self):
        state = {}
        _merge_node(state, "!11223344", "nodeinfo", {"longname": "Alpha", "role": 2})
        _merge_node(state, "!11223344", "position", {
            "latitude_i": 453000000, "longitude_i": -1224000000, "altitude": 50
        })
        _merge_node(state, "!11223344", "telemetry", {"battery_level": 95})
        node = state["!11223344"]
        self.assertEqual(node["name"], "Alpha")
        self.assertAlmostEqual(node["latitude"], 45.3, places=1)
        self.assertEqual(node["battery"], 95.0)

    def test_unknown_message_type_ignored(self):
        state = {}
        _merge_node(state, "!ffffffff", "traceroute", {"hops": [1, 2, 3]})
        self.assertEqual(state["!ffffffff"], {"id": "!ffffffff"})


class TestMeshtasticGeoJSON(unittest.TestCase):
    """Test mt_nodes_to_geojson() output schema consistency."""

    def _sample_nodes(self):
        return [
            {
                "id": "!deadbeef",
                "name": "Test Router",
                "type": "Router",
                "latitude": 45.52,
                "longitude": -122.68,
                "altitude": 200.0,
                "battery": 75.0,
            }
        ]

    def test_schema_matches_meshcore_schema(self):
        geojson = mt_nodes_to_geojson(self._sample_nodes())
        assert_valid_feature_collection(self, geojson, min_count=1)

    def test_coordinate_order(self):
        geojson = mt_nodes_to_geojson(self._sample_nodes())
        coords = geojson["features"][0]["geometry"]["coordinates"]
        self.assertAlmostEqual(coords[0], -122.68)
        self.assertAlmostEqual(coords[1], 45.52)
        self.assertAlmostEqual(coords[2], 200.0)

    def test_rssi_snr_null_when_not_available(self):
        """Meshtastic MQTT JSON does not include RSSI/SNR; fields must be null, not missing."""
        geojson = mt_nodes_to_geojson(self._sample_nodes())
        props = geojson["features"][0]["properties"]
        self.assertIn("rssi", props)
        self.assertIn("snr", props)
        self.assertIsNone(props["rssi"])
        self.assertIsNone(props["snr"])

    def test_service_metadata_field(self):
        geojson = mt_nodes_to_geojson(self._sample_nodes())
        self.assertEqual(geojson["metadata"]["service"], "meshtastic")


if __name__ == "__main__":
    unittest.main()
