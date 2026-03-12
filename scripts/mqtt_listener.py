"""
Background MQTT listener for MeshCore telemetry streaming.

Subscribes to position and telemetry messages from MeshCore gateway nodes,
filters by node type, and exports to GeoJSON or InfluxDB.
"""

import json
import argparse
from typing import Optional, Callable
from datetime import datetime
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MeshCoreMQTTListener:
    """Listen to MeshCore MQTT telemetry stream."""
    
    # MeshCore device_role int -> human-readable type string
    DEVICE_ROLES = {1: "Repeater", 2: "Companion", 3: "Room Server"}

    def __init__(self, broker: str, topics: list = None, output_file: str = None):
        """
        Initialize MQTT listener.

        Args:
            broker: MQTT broker address
            topics: List of topics to subscribe (defaults to all MeshCore topics)
            output_file: Optional GeoJSON output file for streaming updates
        """
        self.broker = broker
        self.topics = topics or ["meshcore/#"]
        self.output_file = output_file
        self.nodes = {}
        self.client = None
    
    def connect(self) -> bool:
        """
        Connect to MQTT broker.
        
        Returns:
            True if connection successful
        """
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.error("paho-mqtt not installed. Run: pip install paho-mqtt")
            return False
        
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                logger.info(f"Connected to broker {self.broker}")
                for topic in self.topics:
                    client.subscribe(topic)
                    logger.info(f"Subscribed to {topic}")
            else:
                logger.error(f"Connection failed with code {rc}")
        
        def on_message(client, userdata, msg):
            self.handle_message(msg.topic, msg.payload)
        
        self.client = mqtt.Client()
        self.client.on_connect = on_connect
        self.client.on_message = on_message
        
        try:
            self.client.connect(self.broker, 1883, 60)
            return True
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False
    
    def handle_message(self, topic: str, payload: bytes):
        """
        Process incoming MQTT message.
        
        Args:
            topic: MQTT topic
            payload: Message payload (JSON)
        """
        try:
            data = json.loads(payload.decode())

            lat = data.get("latitude")
            lon = data.get("longitude")

            # Skip nodes without position or at the null island (0, 0)
            if lat is None or lon is None:
                return
            lat, lon = float(lat), float(lon)
            if lat == 0.0 and lon == 0.0:
                return

            # Use public_key as the stable unique identifier when available
            node_id = data.get("public_key") or data.get("id") or data.get("name")
            if not node_id:
                return

            role_int = data.get("device_role")
            node_type = self.DEVICE_ROLES.get(role_int) if role_int is not None else data.get("type", "unknown")

            self.nodes[node_id] = {
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
            logger.debug(f"Updated node {node_id}")

            if self.output_file:
                self.write_geojson()
        
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON from {topic}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def write_geojson(self):
        """Write current node state to GeoJSON file."""
        features = []
        for node in self.nodes.values():
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [node["longitude"], node["latitude"], node["altitude"]],
                },
                "properties": {k: v for k, v in node.items() if k not in ["latitude", "longitude", "altitude"]},
            }
            features.append(feature)
        
        geojson = {
            "type": "FeatureCollection",
            "features": features,
            "metadata": {
                "generated": datetime.utcnow().isoformat(),
                "count": len(features),
                "broker": self.broker
            }
        }
        
        try:
            with open(self.output_file, 'w') as f:
                json.dump(geojson, f, indent=2)
        except IOError as e:
            logger.error(f"Failed to write {self.output_file}: {e}")
    
    def start(self):
        """Start listening to MQTT stream."""
        if not self.connect():
            return False
        
        logger.info(f"Listening for telemetry. Output: {self.output_file or 'console'}")
        try:
            self.client.loop_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.client.disconnect()
        
        return True


def main():
    """CLI interface for MQTT listener."""
    parser = argparse.ArgumentParser(
        description="Listen to MeshCore MQTT telemetry stream"
    )
    parser.add_argument(
        "--broker",
        default="broker.meshcore.dev",
        help="MQTT broker address (default: broker.meshcore.dev)"
    )
    parser.add_argument(
        "--output",
        help="Output GeoJSON file for streaming updates"
    )
    parser.add_argument(
        "--topics",
        nargs="+",
        default=["meshcore/#"],
        help="MQTT topics to subscribe (default: meshcore/#)"
    )
    
    args = parser.parse_args()
    
    listener = MeshCoreMQTTListener(args.broker, topics=args.topics, output_file=args.output)
    listener.start()


if __name__ == "__main__":
    main()
