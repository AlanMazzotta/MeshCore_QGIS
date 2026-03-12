"""
Export MeshCore node data to GeoJSON format.

Data source: MeshCore public map API (https://map.meshcore.dev)
Returns MessagePack-encoded binary with all known repeater nodes globally.
Use filter_by_dem.py to trim to your DEM extent before running viewsheds.
"""

import json
import argparse
from typing import List, Dict, Any
from pathlib import Path
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None


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


def nodes_to_geojson(nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convert node list to GeoJSON FeatureCollection."""
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

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "generated": datetime.utcnow().isoformat(),
            "count": len(features)
        }
    }


def save_geojson(geojson, output_path: str) -> bool:
    """Save GeoJSON to file. Accepts a node list or a pre-built FeatureCollection dict."""
    if isinstance(geojson, list):
        geojson = nodes_to_geojson(geojson)
    try:
        with open(output_path, 'w') as f:
            json.dump(geojson, f, indent=2)
        print(f"Saved {len(geojson['features'])} nodes to {output_path}")
        return True
    except IOError as e:
        print(f"ERROR: Failed to save {output_path}: {e}")
        return False


def main():
    """CLI interface for node export."""
    parser = argparse.ArgumentParser(
        description="Fetch MeshCore nodes from the public map API and export to GeoJSON"
    )
    parser.add_argument(
        "--output",
        default="data/meshcore_nodes.geojson",
        help="Output GeoJSON file (default: data/meshcore_nodes.geojson)"
    )
    parser.add_argument(
        "--api-url",
        default="https://map.meshcore.dev/api/v1/nodes?binary=1&short=1",
        help="MeshCore map REST API URL"
    )

    args = parser.parse_args()
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    nodes = fetch_from_map_api(api_url=args.api_url)
    if nodes:
        save_geojson(nodes_to_geojson(nodes), args.output)
    else:
        print("WARNING: No nodes fetched")


if __name__ == "__main__":
    main()
