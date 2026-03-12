# Terrain-Aware Coverage Analysis for MeshCore Networks
### A Reproducible GIS Workflow — Demonstrated on the Portland Metro Area
*March 2026 | MeshCore_QGIS Project*

---

## What This Is

This document describes a repeatable, open-source workflow for analysing the geographic coverage and structural health of any MeshCore repeater network using terrain-aware viewshed modelling. The method requires no proprietary tools: it uses the public MeshCore map API, a freely available digital elevation model, GDAL, Python, and **QGIS** for visualisation and interactive exploration.

The **Portland, Oregon metropolitan area** is used throughout as the worked example. All numbers, maps, and classifications refer to that region and are included to make the method concrete — not because Portland is unique. The same pipeline has been designed to run against any region where MeshCore repeaters are deployed.

All code is available at the project repository.

---

## Why Terrain-Aware Analysis Matters

MeshCore deployments in mountainous or hilly terrain behave very differently from flat-urban networks. A repeater on a ridgeline may have geometric line-of-sight to hundreds of square kilometres of valley floor, while a node at the base of a hillside may be effectively isolated. Standard signal-strength metrics from device firmware don't capture this spatial structure. A terrain-aware viewshed model does.

This analysis answers three questions that firmware telemetry alone cannot:
1. Where does the network actually reach, and where are the gaps?
2. Which directions are over- or under-served?
3. Which individual nodes are structural single points of failure?

---

## Step 1: Fetch Node Positions

Repeater locations are pulled from the **MeshCore public map API** (`map.meshcore.dev`). The API exposes a global node registry — at time of writing, roughly 25,000 nodes worldwide — encoded in MessagePack binary format. Each record includes device type (Client=1, Repeater=2, Room Server=3), name, coordinates, and last-seen timestamps.

The workflow fetches this payload with Python's `requests` library, decodes it with `msgpack`, and filters to `type=Repeater` only. A second spatial filter trims nodes to the bounding box of your chosen DEM, so only nodes that can interact with local terrain are included.

**Portland result:** 253 repeater nodes retained from 25,115 global records.

The API is unauthenticated and publicly accessible. Refreshing node positions before each analysis run takes a few seconds and ensures results reflect current network state.

---

## Step 2: Acquire a Digital Elevation Model

Terrain data is sourced from the **Copernicus GLO-30 DEM** (COP30) — a freely available global dataset at 30-metre horizontal resolution, accessible via the OpenTopography REST API. Set the download extent to your study region and save the result as a local GeoTIFF.

The DEM serves two roles: it defines the spatial extent of the analysis, and it provides the terrain surface used by the viewshed engine.

**Portland DEM:** 5,906 × 1,989 pixels covering roughly 17,000 km², including the West Hills, Tualatin Valley, Columbia River corridor, and the western edge of the Columbia River Gorge.

For other regions, the same OpenTopography endpoint works worldwide. A typical metro-area DEM downloads in under a minute.

---

## Step 3: Compute Individual Viewsheds

A **line-of-sight viewshed** is computed for each repeater node using `gdal_viewshed` (GDAL 3.11). The model asks: from this node's location at 2 metres above ground level, which terrain pixels are geometrically visible?

The output for each node is a binary raster the same size as the DEM, where visible pixels are marked 255 and non-visible pixels are 0. RF propagation effects such as atmospheric refraction and Fresnel zone clearance are not modelled; this is a geometric first-order approximation that runs quickly and requires no RF parameter tuning.

Individual viewshed rasters are saved as GeoTIFFs named by node key hash, making them stable and reusable across data refreshes. The pipeline supports a `--skip-viewshed` flag to skip re-computing TIFs that already exist on disk, which is important when re-running the pipeline after a node roster update — only new or changed nodes need new viewshed runs.

**Portland compute time:** approximately 30–40 minutes for all 253 nodes on a mid-range laptop.

For a new region, runtime scales roughly linearly with DEM pixel count × node count. Larger DEMs or denser node rosters will take proportionally longer.

---

## Step 4: Build the Cumulative Coverage Raster

With all individual viewshed TIFs computed, they are **stacked via NumPy summation** using the GDAL Python bindings. Each pixel in the resulting raster holds an integer count: how many repeaters have geometric line-of-sight to that location.

A pixel value of 0 means no coverage. A value of 10 means 10 repeaters can theoretically reach that point. This raster is the primary deliverable for coverage QA — it immediately shows gaps, transition zones, and areas of deep redundancy.

**Portland result:** 100% of land pixels covered by at least one repeater. While complete coverage is notable, the more interesting signal is in the distribution of values — most of the valley floor sits in the 5–25 range, while terrain-shaded areas in the southwest drop to 1–3.

This raster loads directly into QGIS. Apply a pseudocolor ramp (e.g. yellow → dark red) to visualise coverage depth at a glance.

---

## Step 5: Directional Coverage Analysis

The cumulative raster shows *how much* coverage exists but not *which directions* it extends from. The directional analysis answers this.

For each visible pixel, the **nearest repeater** is identified by Euclidean distance. The compass bearing from that repeater to the pixel is computed using the haversine forward azimuth formula. Bearings are then classified into eight 45° compass sectors (N, NE, E, SE, S, SW, W, NW), and the result is written as a new raster where each pixel's value encodes its sector.

This produces a spatial map of coverage reach direction across the study area — useful for identifying which parts of the terrain are underserved from a directional standpoint and where a new repeater would fill the most gap.

**Portland directional breakdown:**

| Sector | % of covered pixels |
|--------|-------------------|
| NE     | 15.8% |
| NW     | 15.4% |
| N      | 13.2% |
| E      | 14.8% |
| W      | 12.7% |
| SE     | 11.9% |
| **SW** | **8.5%** |
| **S**  | **7.6%** |

The south and southwest are meaningfully underserved relative to the rest of the compass rose. This aligns with local terrain: the West Hills and Chehalem Mountain ridgelines run north-south, creating shadow on their southern slopes that reduces effective coverage reach in those directions. Any region with similar oriented terrain features will produce similar directional asymmetries.

---

## Step 6: Enrich Nodes with Derived Attributes

The raw node GeoJSON contains only position and metadata from the API. A final enrichment step adds four derived attributes computed from the raster outputs:

- **`peer_count`** — the cumulative viewshed value sampled at the node's own location. How many other repeaters have line-of-sight to this node? Higher values mean the node sits in a well-connected mesh zone; a value of 0 or 1 flags isolation.
- **`viewshed_pixels`** — total visible pixels in the node's individual TIF, representing raw coverage reach in pixel units.
- **`coverage_km2`** — pixel count converted to approximate square kilometres at the node's latitude.
- **`dominant_dir`** — modal compass sector of all bearings from the node to its visible pixels, identifying the primary direction the node "faces."

The enriched dataset is exported as `meshcore_nodes_plus.geojson` and can be loaded directly into QGIS or any GIS tool for further analysis and mapping.

**Portland enrichment summary:**
- `peer_count`: range 0–125, mean 9.1
- `coverage_km2`: range 0.07–1,608 km², mean ~201 km² (a 23,000× spread between least and most effective nodes)
- `dominant_dir`: E dominant for 92 nodes, NE for 43, NW for 30, W for 24 — eastern-facing nodes are most common

---

## Step 7: Classify Nodes by Role

Intersecting `coverage_km2` and `peer_count` using a threshold-based quadrant classification produces four operationally meaningful node categories:

- **Critical** (high coverage, low peer visibility): covers large terrain but is seen by few peers. Single point of failure — its loss removes significant coverage with no mesh fallback.
- **Backbone** (high coverage, high peer visibility): well-connected, high-reach nodes forming the structural core of the network.
- **Redundant** (low coverage, high peer visibility): locally over-served, contributes marginal unique coverage but is well-integrated.
- **Marginal** (low coverage, low peer visibility): peripheral nodes with limited reach and limited connectivity.

This classification surfaces actionable priorities: Critical nodes warrant immediate attention for redundancy planning; SW-facing coverage gaps indicate where new siting would have the highest impact.

In QGIS, the enriched layer can be styled using rule-based symbology with the four quadrant rules to display all node categories simultaneously on the map.

---

## Replicating This for Your Region

The pipeline is fully automated and parameterised. To run it for a different region:

1. Download a COP30 DEM tile covering your area from OpenTopography
2. Point the pipeline at your DEM — it will auto-filter API nodes to that bounding box
3. Run `python scripts/pipeline.py` — viewsheds, cumulative raster, and node GeoJSON are all produced in sequence
4. Run `scripts/viewshed_directional.py` and `scripts/enrich_nodes.py` to generate the directional and enriched outputs

The only region-specific inputs are the DEM file and the study bounding box derived from it. Node data is always pulled live from the public API.

If your region has fewer nodes than Portland's 253, compute time will be proportionally shorter. All outputs — TIFs, GeoJSONs, and QGIS styling code — are designed to be drop-in compatible regardless of region or node count.

---

### QGIS as an Analysis Tool

QGIS played a central role throughout this workflow — not just as a display layer at the end, but as an interactive analysis environment. The cumulative and directional rasters were loaded into QGIS during development to visually QA intermediate outputs, verify spatial alignment between the DEM and node positions, and iterate on symbology. The Script Editor (accessible via `Ctrl+Alt+S`) allows custom Python to run directly against loaded layers, which is how the paletted directional symbology and rule-based node classification were applied without leaving the GIS environment. For anyone following this workflow, QGIS 3.x is free, cross-platform, and handles all of the raster and vector outputs produced here natively.

---

## Analysis Insights and Limitations

### What This Analysis Can and Cannot Tell You

The most important caveat in this entire workflow: **this is a geometric model, not a radio frequency model.** Every coverage claim made here is based on terrain line-of-sight only. The analysis does not account for:

- **Fresnel zone clearance** — a path that clears the terrain surface by only a metre or two may still be significantly attenuated in practice
- **Antenna directionality and gain** — most repeaters are not omnidirectional in practice; a node's real coverage pattern depends on its antenna type and orientation
- **Building and vegetation obstruction** — the COP30 DEM is a bare-earth model; urban canopy, structures, and tree cover are not represented
- **Link budget and receiver sensitivity** — geometric visibility says nothing about whether the signal will be strong enough to decode at the far end

What the model *is* good at: identifying large-scale terrain shadows, ranking nodes by relative coverage reach, and surfacing directional asymmetries that are driven by landform rather than RF parameters. In hilly terrain, terrain blockage is often the dominant constraint on coverage, and geometric viewshed modelling captures that first-order effect well.

### Insights From the Portland Example

Running this workflow on a live deployment produced several findings that would be difficult or impossible to see from firmware telemetry alone:

- **Depth, not breadth, is the useful metric.** 100% pixel coverage sounds impressive, but the directional breakdown and peer_count distribution reveal a network with uneven redundancy — some areas are covered by 20+ repeaters, others by only one. That distinction is invisible without spatial analysis.
- **The 23,000× spread in individual node coverage reach** suggests that node placement history has been ad hoc rather than planned. A handful of ridge-sited nodes carry a disproportionate share of the network's geographic footprint.
- **Directional gaps follow terrain, not deployment decisions.** The S/SW shortfall is not a mistake — it reflects the physical geometry of the West Hills. No amount of repositioning existing nodes will solve it; new siting on south-facing high ground is the only fix. The analysis points directly to where that high ground is.
- **peer_count as a mesh health proxy** is a useful heuristic even without RF data. A node with peer_count=0 is almost certainly isolated regardless of its coverage reach. A node with peer_count=125 is deeply embedded in the mesh and its individual failure is low-risk.

These insights are transferable. Any MeshCore deployment in terrain with similar structural characteristics — ridgelines, valleys, urban canyons — will produce analogous patterns. The value of this workflow is making those patterns visible and actionable.

---

*All scripts, data outputs, and QGIS styling code are available in the project repository.*
