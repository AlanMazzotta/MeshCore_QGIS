"""
Export MeshCore node data to GeoJSON format.

Supports multiple data sources:
- MeshCore API (connected device via USB/BLE/TCP)
- MQTT bridge (gateway node telemetry)
- CSV/GeoJSON input files
"""

import json
import argparse
import threading
import time
from typing import List, Dict, Any
from pathlib import Path
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None


def export_from_api(port: str = None, host: str = None) -> List[Dict[str, Any]]:
    """
    Extract node data from connected MeshCore device.
    
    Args:
        port: Serial port for USB connection (e.g., 'COM3' on Windows)
        host: TCP/IP address for network connection (e.g., '192.168.1.100:4403')
    
    Returns:
        List of node dictionaries with location data
    """
    try:
        import meshcore
    except ImportError:
        print("ERROR: meshcore library not installed. Run: pip install meshcore")
        return []
    
    nodes = []
    
    # TODO: Implement MeshCore API connection logic
    print(f"Connecting to MeshCore device at {port or host}...")
    
    return nodes


def export_from_mqtt(broker: str, topics: List[str] = None, timeout: int = 30) -> List[Dict[str, Any]]:
    """
    Subscribe to MeshCore MQTT broker and collect position messages for a fixed duration.

    Args:
        broker: MQTT broker address (e.g., 'broker.meshcore.dev')
        topics: MQTT topics to subscribe to (defaults to ['meshcore/#'])
        timeout: Listen duration in seconds before disconnecting

    Returns:
        List of node dictionaries with telemetry data
    """
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print("ERROR: paho-mqtt library not installed. Run: pip install paho-mqtt")
        return []

    DEVICE_ROLES = {1: "Repeater", 2: "Companion", 3: "Room Server"}
    topics = topics or ["meshcore/#"]
    collected: Dict[str, Any] = {}
    connected = threading.Event()

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            for topic in topics:
                client.subscribe(topic)
            connected.set()
        else:
            print(f"ERROR: MQTT connection failed (code {rc})")

    def on_message(client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        lat = data.get("latitude")
        lon = data.get("longitude")
        if lat is None or lon is None:
            return
        lat, lon = float(lat), float(lon)
        if lat == 0.0 and lon == 0.0:
            return

        node_id = data.get("public_key") or data.get("id") or data.get("name")
        if not node_id:
            return

        role_int = data.get("device_role")
        node_type = DEVICE_ROLES.get(role_int) if role_int is not None else data.get("type", "unknown")

        collected[node_id] = {
            "id": node_id,
            "name": data.get("name"),
            "type": node_type,
            "latitude": lat,
            "longitude": lon,
            "altitude": float(data.get("altitude", 0)),
            "rssi": float(data["rssi"]) if data.get("rssi") is not None else None,
            "snr": float(data["snr"]) if data.get("snr") is not None else None,
            "battery": float(data["battery"]) if data.get("battery") is not None else None,
            "timestamp": datetime.utcnow().isoformat(),
        }

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Connecting to MQTT broker at {broker}...")
    try:
        client.connect(broker, 1883, 60)
    except Exception as e:
        print(f"ERROR: Could not connect to {broker}: {e}")
        return []

    client.loop_start()
    if not connected.wait(timeout=10):
        print("ERROR: Timed out waiting for broker connection")
        client.loop_stop()
        return []

    print(f"Listening for {timeout}s on {topics}...")
    time.sleep(timeout)
    client.loop_stop()
    client.disconnect()

    nodes = list(collected.values())
    print(f"Collected {len(nodes)} nodes from MQTT")
    return nodes


def fetch_from_map_api(api_url: str = "https://map.meshcore.dev/api/v1/nodes?binary=1&short=1") -> List[Dict[str, Any]]:
    """
    Fetch node positions from the MeshCore map API.

    The API returns MessagePack-encoded binary data with abbreviated field names:
        pk  public key (bytes)
        n   name
        t   device type (1=Client, 2=Repeater, 3=Room Server)
        lat latitude
        lon longitude
        la  last activity timestamp
        ud  last updated timestamp

    Args:
        api_url: MeshCore map API endpoint

    Returns:
        List of node dictionaries with telemetry data
    """
    if requests is None:
        print("ERROR: requests library not installed. Run: pip install requests")
        return []

    try:
        import msgpack
    except ImportError:
        print("ERROR: msgpack not installed. Run: pip install msgpack")
        return []

    DEVICE_ROLES = {1: "Client", 2: "Repeater", 3: "Room Server"}

    print(f"Fetching nodes from {api_url}...")
    try:
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"ERROR: Failed to fetch from {api_url}: {e}")
        return []

    try:
        raw = msgpack.unpackb(response.content, raw=False)
    except Exception as e:
        print(f"ERROR: Failed to decode response: {e}")
        return []

    if not isinstance(raw, list):
        print(f"ERROR: Unexpected response format: {type(raw)}")
        return []

    nodes = []
    for item in raw:
        lat = item.get("lat")
        lon = item.get("lon")
        if lat is None or lon is None:
            continue
        lat, lon = float(lat), float(lon)
        if lat == 0.0 and lon == 0.0:
            continue

        pk = item.get("pk", b"")
        node_id = pk.hex() if isinstance(pk, bytes) else str(pk)
        name = item.get("n") or node_id[:8]

        role_int = item.get("t")
        node_type = DEVICE_ROLES.get(role_int, f"type_{role_int}")

        ud = item.get("ud") or item.get("la")
        timestamp = ud.as_datetime().isoformat() if hasattr(ud, "as_datetime") else datetime.utcnow().isoformat()

        nodes.append({
            "id": node_id,
            "name": name,
            "type": node_type,
            "latitude": lat,
            "longitude": lon,
            "altitude": 0.0,
            "rssi": None,
            "snr": None,
            "battery": None,
            "timestamp": timestamp,
        })

    print(f"Fetched {len(nodes)} nodes from map API")
    return nodes


def load_csv(filepath: str) -> List[Dict[str, Any]]:
    """
    Load node data from CSV file.
    
    Expected columns: id, name, latitude, longitude, altitude, type
    """
    import csv
    
    nodes = []
    
    try:
        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            nodes = list(reader)
    except FileNotFoundError:
        print(f"ERROR: File not found: {filepath}")
    
    return nodes


def nodes_to_geojson(nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Convert node list to GeoJSON FeatureCollection.
    
    Args:
        nodes: List of node dictionaries with lat/lon data
    
    Returns:
        GeoJSON FeatureCollection
    """
    features = []
    
    for node in nodes:
        try:
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        float(node.get("longitude", 0)),
                        float(node.get("latitude", 0)),
                        float(node.get("altitude", 0)),
                    ],
                },
                "properties": {
                    "id": node.get("id"),
                    "name": node.get("name"),
                    "type": node.get("type", "unknown"),
                    "rssi": float(node["rssi"]) if node.get("rssi") is not None else None,
                    "snr": float(node["snr"]) if node.get("snr") is not None else None,
                    "battery": float(node["battery"]) if node.get("battery") is not None else None,
                    "timestamp": node.get("timestamp") or datetime.utcnow().isoformat(),
                },
            }
            features.append(feature)
        except (ValueError, TypeError) as e:
            print(f"WARNING: Skipping node {node.get('id')}: {e}")
    
    geojson = {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "generated": datetime.utcnow().isoformat(),
            "count": len(features)
        }
    }
    
    return geojson


def save_geojson(geojson, output_path: str) -> bool:
    """Save GeoJSON to file. Accepts a node list or a pre-built FeatureCollection dict."""
    if isinstance(geojson, list):
        geojson = nodes_to_geojson(geojson)
    try:
        with open(output_path, 'w') as f:
            json.dump(geojson, f, indent=2)
        print(f"✓ Saved {len(geojson['features'])} nodes to {output_path}")
        return True
    except IOError as e:
        print(f"ERROR: Failed to save {output_path}: {e}")
        return False


def main():
    """CLI interface for node export."""
    parser = argparse.ArgumentParser(
        description="Export MeshCore node data to GeoJSON"
    )
    parser.add_argument(
        "--source",
        choices=["api", "mqtt", "map_api", "csv"],
        default="mqtt",
        help="Data source (default: mqtt)"
    )
    parser.add_argument(
        "--output",
        default="nodes.geojson",
        help="Output GeoJSON file (default: nodes.geojson)"
    )
    parser.add_argument(
        "--port",
        help="Serial port for API connection (e.g., COM3)"
    )
    parser.add_argument(
        "--host",
        help="TCP host for API connection (e.g., 192.168.1.100:4403)"
    )
    parser.add_argument(
        "--broker",
        default="broker.meshcore.dev",
        help="MQTT broker address"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="MQTT listen duration in seconds (default: 30)"
    )
    parser.add_argument(
        "--api-url",
        default="https://map.meshcore.dev/api/v1/nodes?binary=1&short=1",
        help="MeshCore map REST API URL (used with --source map_api)"
    )
    parser.add_argument(
        "--csv",
        help="Input CSV file path"
    )

    args = parser.parse_args()

    nodes = []

    if args.source == "api":
        nodes = export_from_api(port=args.port, host=args.host)
    elif args.source == "mqtt":
        nodes = export_from_mqtt(broker=args.broker, timeout=args.timeout)
    elif args.source == "map_api":
        nodes = fetch_from_map_api(api_url=args.api_url)
    elif args.source == "csv":
        if not args.csv:
            parser.error("--csv required for CSV source")
        nodes = load_csv(args.csv)
    
    if nodes:
        geojson = nodes_to_geojson(nodes)
        save_geojson(geojson, args.output)
    else:
        print("WARNING: No nodes extracted")


if __name__ == "__main__":
    main()
