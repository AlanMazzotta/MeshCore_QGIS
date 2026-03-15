# Future Planning: Live Signal Ingest & SNR Heatmap

## Overview

A signal quality heatmap layer (Inferno color ramp, SNR primary / RSSI attribute) was researched but deferred. This doc captures the options for future implementation.

## Relevant Community Tools

| Repo | Purpose |
|------|---------|
| [meshcore-decoder](https://github.com/michaelhart/meshcore-decoder) | TypeScript npm lib — decodes raw hex packets, AES decrypt, Ed25519 auth |
| [meshcore-mqtt-broker](https://github.com/michaelhart/meshcore-mqtt-broker) | Self-hostable WebSocket MQTT broker with key-based auth |
| [meshcoretomqtt](https://github.com/Cisien/meshcoretomqtt) | Python bridge: fixed repeaters/room servers → MQTT (systemd managed) |
| [meshcore-packet-capture](https://github.com/agessaman/meshcore-packet-capture) | Python bridge: Companion radios → MQTT (BLE/serial/TCP) |

## Option A: MQTT Broker Subscription (letsmesh.net)

**What it gives:** Inter-node link SNR/RSSI from fixed Observer nodes already connected to the community broker.

**Data path:**
1. Subscribe to `meshcore/+/+/packets` (wildcard) on `wss://letsmesh.net`
2. Decode ADVERT packets (type 4) via `meshcore` Python package → node `lat`/`lon`
3. Collect NEIGHBOURS_RESPONSE → per-neighbor SNR/RSSI at each node position
4. IDW interpolation → `meshcore_snr_heatmap.tif`

**Dependencies:** `pip install paho-mqtt meshcore`

**Packet JSON schema:**
```json
{
  "origin_id":   "device_public_key",
  "timestamp":   "2024-01-01T12:00:00.000000",
  "packet_type": "4",
  "SNR":         "12.5",
  "RSSI":        "-65",
  "hash":        "A1B2C3D4E5F67890",
  "raw":         "F5930103..."
}
```

**Authentication:**
- Subscribers need a simple `username:password` pair (no Ed25519 required)
- Roles: `LIMITED` (SNR/RSSI stripped — not useful), `FULL_ACCESS` (all public data — what we need)
- Credentials must be provisioned by the letsmesh.net operator (Michael Hart)
- Signing up as an Observer gives a relationship to request FULL_ACCESS subscriber credentials
- Plugin should be built with configurable host/port/user/pass via QgsSettings

**Limitation:** Only data points AT fixed node locations (~5–15 points for Portland).
IDW from sparse fixed points produces a smooth but low-information surface — not ground truth.

**Trigger to build:** When MQTT credentials are obtained.

---

## Option B: MeshMapper CSV Import (Wardriving)

**What it gives:** GPS-tagged SNR/RSSI observations from a mobile observer — the highest-quality heatmap input.

**Data path:**
1. Wardrive with MeshMapper app (iOS/Android)
2. Export CSV from [pnw.meshmapper.net](https://pnw.meshmapper.net)
3. Plugin loads CSV → filters past 30 days → IDW interpolation → `meshcore_snr_heatmap.tif`

**CSV format:**
```
Latitude, Longitude, Time (Unix timestamp), Status (int), [Coverage Radius], [Repeater], [RSSI], [SNR]
```

**Status codes:** 0=DROP, 1=BIDIR, 2=TX, 3=DEAD, 5=RX, 6=DISC

**Advantage:** No credentials required. Hundreds of spatially distributed observations = meaningful heatmap.

**Trigger to build:** When wardriving data is available.

---

## Recommended Implementation Order

1. **Option B first** — simpler, no credential dependency, produces better data
2. **Option A second** — after obtaining letsmesh.net FULL_ACCESS subscriber credentials

## Heatmap Design (agreed)

- **Primary metric:** SNR (dB)
- **Secondary attribute:** RSSI stored per sample point
- **Aggregation:** Best SNR per grid cell (30-day window)
- **Interpolation:** IDW, 100m resolution default (configurable)
- **Extent:** Canvas extent (consistent with DEM/viewshed pipeline)
- **Color ramp:** Inferno (dark = weak, bright = strong)
- **Output:** `meshcore_snr_heatmap.tif`
- **Symbology function:** `apply_snr_heatmap_symbology()` in `symbology.py`
