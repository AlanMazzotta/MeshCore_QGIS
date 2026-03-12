# MeshCore_QGIS

A Python pipeline for terrain-aware coverage analysis of MeshCore repeater networks using GDAL viewshed modelling and QGIS visualisation.

**→ [Final_Report.md](Final_Report.md)** — full methodology and findings write-up using the Portland metro as a worked example, including replication instructions for other regions.

---

## What it does

1. **Fetches repeater positions** from the public MeshCore map API and writes them as GeoJSON, spatially filtered to a DEM bounding box.
2. **Runs individual viewsheds** using `gdal_viewshed` (GDAL 3.11) — one binary visibility raster per node.
3. **Builds a cumulative coverage raster** showing how many repeaters have line-of-sight to each terrain pixel.
4. **Generates a directional coverage raster** classifying each visible pixel into the 8-sector compass direction it is reached from.
5. **Enriches the node layer** with derived attributes: `peer_count`, `viewshed_pixels`, `coverage_km2`, and `dominant_dir` — exported as `meshcore_nodes_plus.geojson`.

All outputs load directly into QGIS for visualisation and exploration.

---

## Quick start

### 1. Install dependencies

```
pip install -r requirements.txt
```

Requires QGIS 3.16+ for `gdal_viewshed`. The QGIS Python interpreter (`apps/Python312/python.exe`) must be used when running scripts that use GDAL/osgeo bindings.

### 2. Get a DEM

Download a Copernicus GLO-30 DEM tile for your region from [OpenTopography](https://opentopography.org) (free, requires free account). Save as `data/dem.tif`.

### 3. Run the pipeline

```
python scripts/pipeline.py --dem data/dem.tif
```

Fetches live node data from the MeshCore map API, filters to the DEM extent, runs viewsheds for all repeater nodes, and builds the cumulative raster.

**To skip re-running existing viewsheds** (e.g. after a node roster update):
```
python scripts/pipeline.py --dem data/dem.tif --skip-viewshed
```

**To skip the API fetch** and reuse existing `data/meshcore_nodes.geojson`:
```
python scripts/pipeline.py --dem data/dem.tif --skip-fetch
```

### 4. Generate directional and enriched outputs

```
python scripts/viewshed_directional.py
python scripts/enrich_nodes.py
```

Outputs: `viewsheds/meshcore/directional_viewshed.tif` and `data/meshcore_nodes_plus.geojson`.

---

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/pipeline.py` | Full orchestrator — fetch → filter → viewsheds → cumulative raster |
| `scripts/export_nodes.py` | MeshCore map API fetch and GeoJSON export |
| `scripts/viewshed_batch.py` | Per-node `gdal_viewshed` runs and cumulative raster stacking |
| `scripts/viewshed_directional.py` | 8-sector directional coverage raster from cumulative viewshed |
| `scripts/enrich_nodes.py` | Enrich node GeoJSON with raster-derived attributes |
| `scripts/filter_by_dem.py` | Spatial filter — clip node list to DEM bounding box |
| `scripts/fetch_dem.py` | Download DEM from OpenTopography |
| `scripts/qgis_utils.py` | QGIS installation detection and diagnostics |
| `templates/create_qgis_project.py` | Build a QGIS project with pre-styled layers |

---

## Outputs

| File | Description |
|------|-------------|
| `data/meshcore_nodes.geojson` | Repeater positions from MeshCore map API |
| `data/meshcore_nodes_plus.geojson` | Enriched nodes with coverage and connectivity attributes |
| `viewsheds/meshcore/cumulative_viewshed.tif` | Per-pixel repeater count raster |
| `viewsheds/meshcore/directional_viewshed.tif` | 8-sector directional coverage raster (1=N … 8=NW) |
| `viewsheds/meshcore/viewshed_<hash>.tif` | Individual node viewsheds (gitignored, regenerable) |

---

## Data source

Node positions are fetched from the **MeshCore public map API**:

```
https://map.meshcore.dev/api/v1/nodes?binary=1&short=1
```

Response is MessagePack binary, decoded with `msgpack`. No authentication required.

---

## Node enrichment schema

`meshcore_nodes_plus.geojson` adds four attributes to each node:

| Field | Description |
|-------|-------------|
| `peer_count` | Cumulative viewshed value at node location — how many other repeaters have LOS to this node |
| `viewshed_pixels` | Total visible pixels in this node's individual viewshed |
| `coverage_km2` | Approximate coverage area in km² |
| `dominant_dir` | Modal compass sector (N/NE/E/SE/S/SW/W/NW) of the node's coverage reach |

---

## Dependencies

- Python 3.8+
- `requests` — API fetches
- `msgpack` — MeshCore binary API decoding
- `numpy` — raster stacking
- `geojson` — GeoJSON I/O
- `python-dotenv` — `.env` support
- QGIS 3.16+ — `gdal_viewshed` for viewshed computation; QGIS Python for osgeo/GDAL bindings

---

## License

MIT — see [LICENSE](LICENSE).

---

## Attributions

- **Node data** — MeshCore public map API (`map.meshcore.dev`), unauthenticated, live global registry
- **Terrain data** — [Copernicus GLO-30 DEM](https://spacedata.copernicus.eu) via [OpenTopography](https://opentopography.org), licensed under the Copernicus Data Information Policy (open, attribution required)
