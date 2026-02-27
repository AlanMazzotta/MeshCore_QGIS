"""
Export MeshCore node data to GeoJSON format.

Supports multiple data sources:
- MeshCore API (connected device via USB/BLE/TCP)
- MQTT bridge (gateway node telemetry)
- CSV/GeoJSON input files
"""

import json
import argparse
from typing import List, Dict, Any
from pathlib import Path
from datetime import datetime


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


def export_from_mqtt(broker: str, topics: List[str] = None, timeout: int = 10) -> List[Dict[str, Any]]:
    """
    Subscribe to MeshCore MQTT broker and extract position messages.
    
    Args:
        broker: MQTT broker address (e.g., 'broker.meshcore.dev')
        topics: MQTT topics to subscribe to (defaults to all position topics)
        timeout: Listen duration in seconds
    
    Returns:
        List of node dictionaries with telemetry data
    """
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print("ERROR: paho-mqtt library not installed. Run: pip install paho-mqtt")
        return []
    
    nodes = []
    
    # TODO: Implement MQTT listener logic
    print(f"Connecting to MQTT broker at {broker}...")
    
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
                        float(node.get("latitude", 0))
                    ]
                },
                "properties": {
                    "id": node.get("id"),
                    "name": node.get("name"),
                    "type": node.get("type", "unknown"),
                    "altitude": float(node.get("altitude", 0)) if node.get("altitude") else None,
                    "rssi": float(node.get("rssi")) if node.get("rssi") else None,
                    "snr": float(node.get("snr")) if node.get("snr") else None,
                    "battery": float(node.get("battery")) if node.get("battery") else None,
                    "uptime": node.get("uptime"),
                }
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


def save_geojson(geojson: Dict[str, Any], output_path: str) -> bool:
    """Save GeoJSON to file."""
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
        choices=["api", "mqtt", "csv"],
        default="api",
        help="Data source (default: api)"
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
        "--csv",
        help="Input CSV file path"
    )
    
    args = parser.parse_args()
    
    nodes = []
    
    if args.source == "api":
        nodes = export_from_api(port=args.port, host=args.host)
    elif args.source == "mqtt":
        nodes = export_from_mqtt(broker=args.broker)
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
