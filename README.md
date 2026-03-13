# MeshCore Viewshed — QGIS Plugin

A self-contained QGIS plugin for terrain-aware coverage analysis of [MeshCore](https://meshcore.co.uk) repeater networks. Pulls live node data from the public MeshCore map API, downloads a digital elevation model, computes per-node viewsheds, and produces coverage rasters and an enriched node dataset — all from a single dock panel inside QGIS.

---

## Prerequisites

- **QGIS 3.x** (tested on 3.34+)
- **Python packages** — install once via the OSGeo4W Shell:
  ```
  pip install msgpack geojson requests
  ```
- **OpenTopography API key** — free account at [opentopography.org](https://opentopography.org). Used to download the Copernicus GLO-30 DEM.

---

## Installation

1. Copy the `plugin/meshcore_viewshed/` folder to your QGIS plugins directory:
   - Windows: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
   - Linux/macOS: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
2. In QGIS: **Plugins → Manage and Install Plugins → Installed → MeshCore Viewshed → Enable**
3. The dock panel appears on the right side of the QGIS window.

---

## Setup

1. **Open or create a QGIS project and save it.** The plugin writes all outputs to the project's home directory — a saved project file is required before running any steps.
2. Paste your **OpenTopography API key** into the key field. It is saved automatically via QgsSettings and persists across sessions.

---

## The 5-Step Pipeline

Each button runs a background task. Progress and errors appear in the log panel below the buttons.

### 1. Fetch Nodes
Pulls the global MeshCore node registry from `map.meshcore.dev`, decodes the MessagePack payload, filters to `type=Repeater`, and saves `data/meshcore_nodes_all.geojson` to the project directory.

### 2. Download DEM
Downloads a Copernicus GLO-30 DEM tile (30 m resolution) from OpenTopography for the bounding box of your QGIS canvas. Saves `data/dem.tif`, then spatially filters the node list to only those within the DEM extent, producing `data/meshcore_nodes.geojson`.

### 3. Run Viewshed
Computes a geometric line-of-sight viewshed for every repeater node using `gdal_viewshed` (observer height: 2 m above terrain). Individual TIFs are saved to `viewsheds/meshcore/` by node key hash. Existing TIFs are skipped on re-runs. After all individual viewsheds are computed, they are stacked via NumPy summation to produce `viewsheds/meshcore/cumulative_viewshed.tif` — a raster where each pixel value is the count of repeaters with line-of-sight to that location.

The coverage raster loads automatically with an **amber heat ramp**: transparent at 0, cream at 1 node, burnt-orange at maximum, 50% layer opacity.

### 4. Directional Raster
Classifies each visible pixel by the compass bearing from its nearest repeater, producing `viewsheds/meshcore/directional_viewshed.tif`. Eight 45° sectors (N, NE, E, SE, S, SW, W, NW) each rendered in a distinct colour. Useful for identifying directionally underserved terrain.

### 5. Enrich Nodes
Samples raster outputs at each node location and appends four derived attributes to produce `data/meshcore_nodes_plus.geojson`:

| Attribute | Description |
|---|---|
| `peer_count` | Cumulative viewshed value at the node — how many other repeaters have line-of-sight to it |
| `viewshed_pixels` | Total visible pixel count from the node's individual TIF |
| `coverage_km2` | Pixel count converted to approximate km² at the node's latitude |
| `dominant_dir` | Modal compass sector of bearings from the node to all its visible pixels |

The enriched layer loads with antenna icon markers and proportional reach circles (see Symbology).

---

## Symbology

### Coverage Raster
Single-band pseudocolor, amber heat ramp. Pixel value = number of repeaters with line-of-sight. 50% layer opacity.

### Enriched Nodes
Each node renders as two stacked symbol layers:

**Reach circle (behind):** A semi-transparent circle drawn in real-world map units. Radius = `sqrt(coverage_km2 / π)` km — the equivalent circular radius of the node's measured viewshed area. Colour matches node class at 50% opacity.

**Antenna icon (front):** A broadcast tower SVG (mast + 3 radiating arcs) coloured by node class.

#### Node Classification

Nodes are classified by intersecting `coverage_km2` and `peer_count` at threshold values (100 km², 5 peers):

| Class | Colour | Criteria | Meaning |
|---|---|---|---|
| **Critical** | Red | coverage ≥ 100 km², peers < 5 | High reach, few redundant paths — single point of failure |
| **Backbone** | Blue | coverage ≥ 100 km², peers ≥ 5 | High reach, well connected — structural core of the network |
| **Redundant** | Green | coverage < 100 km², peers ≥ 5 | Locally over-served, limited unique coverage |
| **Marginal** | Grey | coverage < 100 km², peers < 5 | Peripheral, limited reach and connectivity |
| **No TIF** | Light grey | coverage = 0 | Viewshed not computed or no visible pixels |

Node name labels are displayed in 7 pt white text with a black halo.

---

## Why Terrain-Aware Analysis Matters

Standard MeshCore firmware telemetry (RSSI, SNR, peer lists) describes what signals are being received — it cannot tell you where the network reaches geographically or which terrain features are creating coverage shadows. A geometric viewshed model answers three questions firmware cannot:

1. **Where does the network actually reach, and where are the gaps?**
2. **Which directions are over- or under-served?**
3. **Which individual nodes are structural single points of failure?**

**This is a geometric model, not an RF model.** It does not account for Fresnel zone clearance, antenna directionality and gain, building or vegetation obstruction, or link budget. In hilly terrain, terrain blockage is typically the dominant coverage constraint, and geometric viewshed modelling captures that first-order effect well.

---

## Portland, Oregon — Worked Example

The workflow was first validated against the Portland metro area MeshCore deployment.

**Network:** 253 repeater nodes retained from 25,115 global API records (filtered to DEM extent).
**DEM:** Copernicus GLO-30, 5,906 × 1,989 px, ~17,000 km² — West Hills, Tualatin Valley, Columbia River corridor, western Columbia Gorge.
**Compute time:** ~35 minutes for all 253 viewsheds on a mid-range laptop.

### Coverage
100% of land pixels covered by at least one repeater. The more informative signal is the distribution — valley floor typically 5–25 repeaters, terrain-shaded southwest areas as low as 1–3.

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

South and southwest are meaningfully underserved. This reflects the north-south orientation of the West Hills and Chehalem Mountain ridgelines, which cast terrain shadows on their southern slopes. New siting on south-facing high ground is the only fix — the analysis identifies exactly where.

### Node Enrichment Summary
- `peer_count`: range 0–125, mean 9.1
- `coverage_km2`: range 0.07–1,608 km², mean ~201 km² — a **23,000× spread** between least and most effective nodes
- `dominant_dir`: E dominant for 92 nodes, NE for 43, NW for 30, W for 24

### Key Findings

**Depth, not breadth, is the useful metric.** Complete pixel coverage sounds impressive, but the peer_count distribution reveals uneven redundancy — some areas covered by 20+ repeaters, others by only one. That distinction is invisible without spatial analysis.

**Node placement has been ad hoc.** The 23,000× spread in individual coverage reach means a small number of ridge-sited nodes carry a disproportionate share of the network's geographic footprint.

**Directional gaps follow terrain, not deployment decisions.** The S/SW shortfall cannot be fixed by repositioning existing nodes — it requires new infrastructure on south-facing high ground.

**`peer_count` as a mesh health proxy.** A node with `peer_count=0` is almost certainly isolated regardless of coverage reach. A node with `peer_count=125` is deeply embedded and its individual failure is low-risk. Actionable without any RF measurement.

---

## Replicating for Your Region

1. Open QGIS, load a basemap, zoom to your region, save the project
2. Enter your OpenTopography API key
3. Run steps 1–5 in order

Runtime scales with `DEM pixel count × node count`. A smaller metro area with 50 nodes will complete in a few minutes. Node data is always pulled live from the public API — only the DEM extent changes between regions.

---

## Data Sources

- **Node data** — MeshCore public map API (`map.meshcore.dev`), unauthenticated, live global registry
- **Terrain data** — [Copernicus GLO-30 DEM](https://spacedata.copernicus.eu) via [OpenTopography](https://opentopography.org), open licence, attribution required

---

*MIT License — see [LICENSE](LICENSE)*
