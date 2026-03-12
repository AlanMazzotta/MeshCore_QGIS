"""
Meshtastic MQTT fetcher — extracts node positions from the Meshtastic public MQTT bridge
and writes them to a GeoJSON file using the same schema as the MeshCore fetcher.

Meshtastic MQTT JSON bridge topic format:
    msh/{region}/{channel}/json/!{nodeId}

Message types handled:
    nodeinfo  — node name, hardware, device role
    position  — latitude_i / longitude_i (integer * 1e-7), altitude
    telemetry — battery_level
"""

import json
import argparse
import threading
import time
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_BROKER = "mqtt.meshtastic.org"
DEFAULT_TOPIC = "msh/#"

# Meshtastic device role int -> human-readable string (from Meshtastic protobuf enum)
DEVICE_ROLES: Dict[int, str] = {
    0: "Client",
    1: "Client Mute",
    2: "Router",
    3: "Router Client",
    4: "Repeater",
    5: "Tracker",
    6: "Sensor",
    7: "TAK",
    8: "Client Hidden",
    9: "Lost and Found",
    10: "TAK Tracker",
}


def _merge_node(state: Dict[str, Any], sender: str, msg_type: str, payload: Dict[str, Any]) -> None:
    """Merge a single MQTT message payload into the shared node state dict."""
    if sender not in state:
        state[sender] = {"id": sender}

    node = state[sender]

    if msg_type == "nodeinfo":
        node["name"] = payload.get("longname") or payload.get("shortname") or sender
        role_int = payload.get("role")
        if role_int is not None:
            node["type"] = DEVICE_ROLES.get(int(role_int), f"role_{role_int}")

    elif msg_type == "position":
        lat_i = payload.get("latitude_i")
        lon_i = payload.get("longitude_i")
        if lat_i is not None and lon_i is not None:
            lat = lat_i * 1e-7
            lon = lon_i * 1e-7
            # Skip null-island
            if lat != 0.0 or lon != 0.0:
                node["latitude"] = lat
                node["longitude"] = lon
                node["altitude"] = float(payload.get("altitude", 0))
                node["timestamp"] = datetime.utcfromtimestamp(
                    payload.get("time", 0)
                ).isoformat() if payload.get("time") else datetime.utcnow().isoformat()

    elif msg_type == "telemetry":
        batt = payload.get("battery_level")
        if batt is not None:
            node["battery"] = float(batt)


def nodes_with_position(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return only nodes that have a known position."""
    return [n for n in state.values() if "latitude" in n and "longitude" in n]


def fetch_from_mqtt(
    broker: str = DEFAULT_BROKER,
    topics: Optional[List[str]] = None,
    timeout: int = 60,
    output_file: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Subscribe to Meshtastic MQTT bridge and collect node telemetry.

    Args:
        broker:      MQTT broker host (default: mqtt.meshtastic.org)
        topics:      Topics to subscribe to (default: ['msh/#'])
        timeout:     Seconds to listen before returning
        output_file: Optional path to write a live-updating GeoJSON file

    Returns:
        List of node dicts with at least latitude and longitude populated
    """
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        logger.error("paho-mqtt not installed. Run: pip install paho-mqtt")
        return []

    topics = topics or [DEFAULT_TOPIC]
    state: Dict[str, Any] = {}
    connected = threading.Event()

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            for topic in topics:
                client.subscribe(topic)
                logger.info(f"Subscribed to {topic}")
            connected.set()
        else:
            logger.error(f"MQTT connection failed (rc={rc})")

    def on_message(client, userdata, msg):
        # Only process JSON-encoded messages (topic contains /json/)
        if "/json/" not in msg.topic:
            return
        try:
            envelope = json.loads(msg.payload.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return

        sender = envelope.get("sender") or str(envelope.get("from", ""))
        msg_type = envelope.get("type", "")
        payload = envelope.get("payload", {})

        if not sender or not isinstance(payload, dict):
            return

        _merge_node(state, sender, msg_type, payload)

        if output_file:
            _write_geojson(nodes_with_position(state), output_file, broker)

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    logger.info(f"Connecting to Meshtastic MQTT broker at {broker}...")
    try:
        client.connect(broker, 1883, 60)
    except Exception as e:
        logger.error(f"Could not connect to {broker}: {e}")
        return []

    client.loop_start()
    if not connected.wait(timeout=10):
        logger.error("Timed out waiting for broker connection")
        client.loop_stop()
        return []

    logger.info(f"Listening for {timeout}s...")
    time.sleep(timeout)
    client.loop_stop()
    client.disconnect()

    nodes = nodes_with_position(state)
    logger.info(f"Collected {len(nodes)} nodes with position from Meshtastic MQTT")
    return nodes


def nodes_to_geojson(nodes: List[Dict[str, Any]], broker: str = DEFAULT_BROKER) -> Dict[str, Any]:
    """Convert node list to GeoJSON FeatureCollection using the shared project schema."""
    features = []
    for node in nodes:
        try:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        float(node["longitude"]),
                        float(node["latitude"]),
                        float(node.get("altitude", 0)),
                    ],
                },
                "properties": {
                    "id": node.get("id"),
                    "name": node.get("name"),
                    "type": node.get("type", "unknown"),
                    "rssi": node.get("rssi"),       # not provided by Meshtastic MQTT JSON
                    "snr": node.get("snr"),          # not provided by Meshtastic MQTT JSON
                    "battery": node.get("battery"),
                    "timestamp": node.get("timestamp") or datetime.utcnow().isoformat(),
                },
            })
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Skipping node {node.get('id')}: {e}")

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "service": "meshtastic",
            "generated": datetime.utcnow().isoformat(),
            "count": len(features),
            "broker": broker,
        },
    }


def _write_geojson(nodes: List[Dict[str, Any]], output_file: str, broker: str = DEFAULT_BROKER) -> None:
    geojson = nodes_to_geojson(nodes, broker)
    try:
        with open(output_file, "w") as f:
            json.dump(geojson, f, indent=2)
    except IOError as e:
        logger.error(f"Failed to write {output_file}: {e}")


def save_geojson(nodes: List[Dict[str, Any]], output_path: str, broker: str = DEFAULT_BROKER) -> bool:
    """Write nodes to a GeoJSON file."""
    geojson = nodes_to_geojson(nodes, broker)
    try:
        with open(output_path, "w") as f:
            json.dump(geojson, f, indent=2)
        logger.info(f"Saved {len(geojson['features'])} nodes to {output_path}")
        return True
    except IOError as e:
        logger.error(f"Failed to save {output_path}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Meshtastic node positions via MQTT and export to GeoJSON"
    )
    parser.add_argument(
        "--broker",
        default=DEFAULT_BROKER,
        help=f"MQTT broker address (default: {DEFAULT_BROKER})",
    )
    parser.add_argument(
        "--topics",
        nargs="+",
        default=[DEFAULT_TOPIC],
        help=f"MQTT topics (default: {DEFAULT_TOPIC})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Listen duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--output",
        default="data/meshtastic_nodes.geojson",
        help="Output GeoJSON file (default: data/meshtastic_nodes.geojson)",
    )

    args = parser.parse_args()
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    nodes = fetch_from_mqtt(
        broker=args.broker,
        topics=args.topics,
        timeout=args.timeout,
        output_file=args.output,
    )

    if nodes:
        save_geojson(nodes, args.output, broker=args.broker)
    else:
        logger.warning("No nodes with position data collected")


if __name__ == "__main__":
    main()
