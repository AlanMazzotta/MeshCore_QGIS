# MeshCore Viewshed: QGIS Plugin

A self-contained QGIS plugin for terrain-aware coverage analysis of [MeshCore](https://meshcore.co.uk) repeater networks. Pulls live node data from the public MeshCore map API, downloads a digital elevation model, computes per-node viewsheds, produces coverage rasters and an enriched node dataset, and -- with a local Observer node running -- generates an observed RF signal quality heatmap. All from a single dock panel inside QGIS.

**[Live example: Portland MeshCore Network](https://alanmazzotta.github.io/MeshCore_QGIS/)**

---

## Prerequisites

- **QGIS 3.34 or later**
- **Python packages:** install once via the OSGeo4W Shell (Windows) or a terminal:
  ```
  pip install msgpack geojson requests
  ```
- **OpenTopography API key:** free account at [opentopography.org](https://opentopography.org). Used to download the Copernicus GLO-30 DEM.
- **Signal Quality heatmap only:** a MeshCore Observer node running the [meshcore-packet-capture](https://github.com/agessaman/meshcore-packet-capture) Docker container with `--output` logging enabled (see Signal Quality section).

---

## Installation

1. Copy `plugin/meshcore_viewshed/` to your QGIS plugins directory:
   - **Windows:** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
   - **Linux / macOS:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
2. **Plugins -> Manage and Install Plugins -> Installed -> MeshCore Viewshed -> Enable**
3. The dock panel opens on the right side of the QGIS window.

---

## Before You Start

**Save your QGIS project first.** All outputs are written to the project home directory alongside the `.qgz` file. The plugin will not run without an open, saved project.

---

## The 5-Step Geometric Pipeline

Each button launches a background task. Progress and errors appear in the log panel at the bottom of the dock.

### 1. Fetch Nodes
Pulls the global MeshCore node registry from `map.meshcore.dev`, decodes the MessagePack payload, and saves `data/meshcore_nodes_all.geojson` to the project directory.

### 2. Download DEM
**Set your canvas extent before clicking.** Zoom and pan the map window to frame your study area; the plugin uses exactly what is visible at the moment you click as the download bounding box.

Downloads a Copernicus GLO-30 DEM tile (30 m resolution) from OpenTopography. Saves `data/dem.tif`, then spatially filters the node list to repeaters within the DEM extent, producing `data/meshcore_nodes.geojson`.

> **Tip:** load a basemap first (QuickMapServices or an XYZ tile layer) so you can visually confirm your canvas covers the right area before downloading. A typical metro-area DEM downloads in under a minute.

### 3. Run Viewshed
Computes a geometric line-of-sight viewshed for every repeater node using `gdal_viewshed` (observer height: 2 m above terrain). Individual TIFs are saved to `viewsheds/meshcore/` keyed by node hash; existing TIFs are skipped on re-runs. After all nodes are processed, they are summed via NumPy to produce `viewsheds/meshcore/cumulative_viewshed.tif`, where each pixel value is the count of repeaters with unobstructed line-of-sight to that location. Loads automatically with an amber heat ramp.

### 4. Directional Raster
Classifies each visible pixel by the compass bearing from its nearest repeater into eight 45-degree sectors (N, NE, E, SE, S, SW, W, NW). Saves `viewsheds/meshcore/directional_viewshed.tif`. Useful for identifying azimuths that are structurally underserved by the current deployment.

### 5. Enrich Nodes
Samples the viewshed outputs at each repeater location and appends four derived attributes to produce `data/meshcore_nodes_plus.geojson`:

| Attribute | Description |
|---|---|
| `peer_count` | Cumulative viewshed value at the node: how many other repeaters have line-of-sight to it |
| `viewshed_pixels` | Total visible pixel count from the node's individual TIF |
| `coverage_km2` | Pixel count converted to approximate km² at the node's latitude |
| `dominant_dir` | Modal compass sector of bearings from the node to all its visible pixels |

The enriched layer loads with antenna icon markers and proportional reach circles. Nodes are classified by `coverage_km2` (threshold: 100 km²) crossed with `peer_count` (threshold: 3 peers):

| Class | Colour | Criteria | Meaning |
|---|---|---|---|
| **Critical** | Red | coverage >= 100 km², peers < 3 | High reach, no redundant paths -- single point of failure |
| **Backbone** | Blue | coverage >= 100 km², peers >= 3 | High reach, well connected -- structural core |
| **Redundant** | Green | coverage < 100 km², peers >= 3 | Locally over-served, limited unique coverage |
| **Marginal** | Grey | coverage < 100 km², peers < 3 | Peripheral, limited reach and connectivity |
| **No TIF** | Light grey | coverage = 0 | Viewshed not computed |

The peer count threshold of 3 is chosen because a node with 3 or more line-of-sight peers has genuine redundant routing paths -- the fundamental property of a mesh network. Nodes with fewer peers are effectively leaf nodes or spurs regardless of how much terrain they cover; their failure removes coverage with no alternate path.

Node name labels are displayed in 7 pt white text with a black halo.

---

## Signal Quality Heatmap (POC)

The geometric pipeline above answers *where* the network reaches based on terrain. The Signal Quality feature answers *how well* it reaches based on observed RF measurements from a live Observer node. Overlaying the two surfaces reveals where geometric line-of-sight and actual radio performance agree -- and where they diverge.

### RF primer for GIS users

Radio signal quality is reported using two metrics: **SNR** and **RSSI**. Both are expressed in decibels (dB), a logarithmic unit. Because the scale is logarithmic, a 3 dB increase represents roughly double the signal power; a 10 dB increase is a ten-fold increase. This matters for interpretation: a heatmap that shifts from -5 dB to +10 dB across a valley floor represents a 30-fold change in signal power, not a 15-point linear change.

**SNR (Signal-to-Noise Ratio)** measures how much stronger the received signal is than the background radio noise floor at the receiver. Higher is better. SNR is the more useful metric for link quality because it is normalised against local interference conditions:

| SNR | Link quality |
|---|---|
| > 10 dB | Excellent -- reliable, high-throughput |
| 5-10 dB | Good -- stable under normal conditions |
| 0-5 dB | Marginal -- possible packet loss |
| < 0 dB | Very weak -- frequent loss; signal is below noise floor |

**RSSI (Received Signal Strength Indicator)** is the raw received power in dBm (decibels relative to 1 milliwatt). It is always negative; less negative is stronger (-70 dBm is far stronger than -120 dBm). RSSI alone does not tell you whether a link is usable because a strong signal in a high-noise environment can still produce a poor SNR. Think of SNR as the GIS equivalent of a classification accuracy metric and RSSI as the raw count underneath it.

**Advert packets** are periodic beacons broadcast by every MeshCore node on a fixed schedule. Each advert contains the transmitter's 32-byte public key (its unique identifier on the network), GPS coordinates if available, a name, and capability flags. Because each advert is self-identifying, the Observer can attribute every received SNR measurement directly to a specific named node at a known geographic location -- no additional network interrogation needed. This is the property that makes spatial mapping possible: each advert is effectively a georeferenced RF observation.

The plugin filters to advert packets only for exactly this reason. Other packet types (text messages, ACKs, relay forwards) carry SNR data but do not reliably expose the original transmitter's identity without full payload decoding.

**Inverse-distance weighting (IDW)** is the same spatial interpolation method available in QGIS's own interpolation tools. Each observation point (node location + best observed SNR) influences surrounding grid cells in proportion to `1/distance²`. Closer nodes dominate; distant ones contribute proportionally less. The resulting raster should be read as a relative surface of "how well can the mesh be heard from the Observer's location given current network activity" -- not an absolute propagation model. The IDW surface will be smooth regardless of terrain; it does not model diffraction, reflection, or obstruction. That is precisely why comparing it against the viewshed layer is analytically useful.

### Observer setup

An Observer is any MeshCore node that logs every packet it hears to disk and/or to a community MQTT broker. The setup used for PDX coverage analysis:

- **Hardware:** Heltec V3 (ESP32-S3), MeshCore companion firmware, TCP connection on port 5000
- **Brokers:** `mqtt-us-v1.letsmesh.net`, `mqtt-eu-v1.letsmesh.net`, `mqtt-v1.cascadiamesh.org` (all port 443, WebSockets, TLS)
- **Local log:** `--output /path/to/packets.ndjson` passed to `packet_capture.py`

**Docker (easiest path):** ensure your `docker-compose.yml` includes:
```yaml
command: python packet_capture.py --output /app/data/packets.ndjson
```

Then restart the container to pick up the change:
```
docker compose down
docker compose up -d
```

> `docker compose restart` alone does not re-read a `command:` change in the compose file -- `down` then `up` is required. On Windows PowerShell, run these as separate commands.

**Always-on deployment:** for permanent Observer setups, `packet_capture.py` can be run directly on a Raspberry Pi or a modern OpenWrt-capable router, managed as a system service. Add `--output /path/to/packets.ndjson` to the service's command line and the plugin will read from it the same way.

### Generating the heatmap

1. Confirm `packet_capture.py` is running and the packets file is growing on disk.
2. Wait for at least one advert cycle (~11 minutes with the default PDX Observer config) so the log contains packets from multiple nodes.
3. Complete pipeline Steps 1 and 5 (Fetch Nodes + Enrich Nodes) so `meshcore_nodes_plus.geojson` exists.
4. In the **Signal Quality (POC)** section of the dock, paste the full path to your `packets.ndjson` file.
5. Click **Generate SNR Heatmap**.

The log panel reports: packets read -> valid ADVERT packets -> matched known nodes -> grid dimensions -> output path. A minimum of 2 matched node observations is required to interpolate.

Output: `data/meshcore_snr_heatmap.tif`, EPSG:4326, ~200 m resolution. Loads automatically with an Inferno colour ramp: dark purple = weak signal, bright yellow = strong signal, 60% opacity. The layer name shows the quality tier and dB range of the observation window.

### Interpreting the two layers together

| Viewshed | SNR heatmap | Interpretation |
|---|---|---|
| High coverage | High SNR | Core of the network -- terrain and observed RF agree |
| High coverage | Low SNR | Line-of-sight exists but signal is weak; possible path loss, antenna mismatch, or interference |
| Low coverage | Adequate SNR | Terrain shadow, but diffraction or reflection is maintaining a link; the geometric model is pessimistic here |
| Low coverage | Low / absent SNR | True gap -- both geometry and measurement agree |

---

## Why Terrain-Aware Analysis Matters

Standard MeshCore firmware telemetry (RSSI, SNR, peer lists) describes what signals are being received at a node; it cannot tell you where the network reaches geographically or which terrain features are creating coverage shadows. A geometric viewshed model answers three questions firmware cannot:

1. **Where does the network actually reach, and where are the gaps?**
2. **Which directions are over- or under-served?**
3. **Which individual nodes are structural single points of failure?**

This is a geometric model, not an RF model. It does not account for Fresnel zone clearance, antenna directionality and gain, building or vegetation obstruction, or link budget. In hilly terrain, terrain blockage is typically the dominant coverage constraint, and geometric viewshed modelling captures that first-order effect well. The Signal Quality heatmap adds the observed RF dimension that the geometric model cannot provide.

---

## Portland, Oregon: Worked Example

**Network:** 253 repeater nodes retained from 25,115 global API records (filtered to DEM extent).
**DEM:** Copernicus GLO-30, 5,906 x 1,989 px, ~17,000 km²: West Hills, Tualatin Valley, Columbia River corridor, western Columbia Gorge.
**Compute time:** ~35 minutes for all 253 viewsheds on a mid-range laptop.

### Coverage
100% of land pixels covered by at least one repeater. The distribution is the informative signal: valley floor typically 5-25 repeaters, terrain-shaded southwest areas as low as 1-3.

### Directional Breakdown

| Sector | % of covered pixels |
|---|---|
| NE | 15.8% |
| NW | 15.4% |
| E | 14.8% |
| N | 13.2% |
| W | 12.7% |
| SE | 11.9% |
| **SW** | **8.5%** |
| **S** | **7.6%** |

South and southwest are meaningfully underserved. This reflects the north-south orientation of the West Hills and Chehalem Mountain ridgelines, which cast terrain shadows on their southern slopes. New siting on south-facing high ground is the only fix; the analysis identifies exactly where.

### Node Enrichment Summary
- `peer_count`: range 0-125, mean 9.1
- `coverage_km2`: range 0.07-1,608 km², mean ~201 km², a **23,000x spread** between least and most effective nodes
- `dominant_dir`: E dominant for 92 nodes, NE for 43, NW for 30, W for 24

### Key Findings

**Depth, not breadth, is the useful metric.** Complete pixel coverage sounds impressive, but the peer_count distribution reveals uneven redundancy: some areas covered by 20+ repeaters, others by only one. That distinction is invisible without spatial analysis.

**Node placement has been ad hoc.** The 23,000x spread in individual coverage reach means a small number of ridge-sited nodes carry a disproportionate share of the network's geographic footprint.

**Directional gaps follow terrain, not deployment decisions.** The S/SW shortfall cannot be fixed by repositioning existing nodes; it requires new infrastructure on south-facing high ground.

**`peer_count` as a mesh health proxy.** A node with `peer_count=0` is almost certainly isolated regardless of coverage reach. A node with `peer_count=125` is deeply embedded and its individual failure is low-risk. Actionable without any RF measurement.

---

## Replicating for Your Region

1. Open QGIS and load a basemap (QuickMapServices or XYZ tile layer)
2. Zoom and pan to frame your study region -- this sets the DEM download extent
3. Save the project (File -> Save)
4. Enter your OpenTopography API key in the dock panel
5. Run steps 1-5 in order

Runtime scales with DEM pixel count x node count. A smaller metro area with 50 nodes will complete in a few minutes. Node data is always pulled live from the public API; only the DEM extent changes between regions.

---

## Future: Live MQTT Signal Ingest

The current Signal Quality implementation reads a local packet log produced by a running `packet_capture.py` process. A natural next step is direct MQTT subscription from within the plugin, which would remove the Docker requirement and draw from the full regional packet stream rather than a single Observer's perspective.

What live MQTT ingest would add:

- **No local container required.** The plugin would connect directly to `wss://letsmesh.net` and subscribe to `meshcore/+/+/packets`.
- **Multi-observer data.** The broker aggregates packets heard by all contributing Observers in the region. More observation points produce a better-constrained IDW surface.
- **Configurable collection window.** The task would collect for a user-defined period (e.g. 30 minutes) before interpolating, rather than replaying a static file.

What it requires:

- **`paho-mqtt`** added as a Python dependency
- **FULL_ACCESS subscriber credentials** for `wss://letsmesh.net` -- contact "Tree" (do.not.blink) or "Howl" (hercules.mulligan) on the MeshCore Discord
- A credentials UI in the dock (Host, Port, Username, Password -- all `QgsSettings`-persisted)
- A live-subscribe variant of `SnrHeatmapTask` that connects, collects, then interpolates on disconnect

The local-file POC and the live-MQTT implementation share the same interpolation and symbology code; only the data collection layer changes.

---

## Data Sources

- **Node data:** MeshCore public map API (`map.meshcore.dev`), unauthenticated, live global registry
- **Terrain data:** [Copernicus GLO-30 DEM](https://spacedata.copernicus.eu) via [OpenTopography](https://opentopography.org), open licence, attribution required
- **Packet data:** live capture from Observer hardware via `meshcore-packet-capture`

---

*MIT License; see [LICENSE](LICENSE)*
