# MeshCore_QGIS

A Python toolkit for fetching live MeshCore and Meshtastic node positions and
performing geospatial coverage analysis in QGIS to support repeater placement
and network planning.

## What it does

1. **Fetches node positions** from MeshCore and Meshtastic MQTT brokers (or the
   MeshCore REST map API) and writes them as GeoJSON — one file per service.
2. **Runs viewshed analysis** using GDAL/QGIS tools to compute what each repeater
   node can see from its elevation.
3. **Builds a cumulative coverage raster** showing which areas are reachable from
   at least one node, and identifies candidate locations for new repeaters.
4. **Creates a live QGIS project** with auto-refreshing layers so you can watch
   results appear in real time while the pipeline runs headlessly from a terminal.

## Quick start

### 1. Install dependencies

```
pip install -r requirements.txt
```

Requires QGIS 3.16+ installed for viewshed analysis. The scripts auto-detect
your QGIS installation — no manual PATH configuration needed.

### 2. Configure VSCode (optional)

Point VSCode at QGIS's bundled Python for IntelliSense:
```
python scripts/qgis_utils.py --write-vscode
```

### 3. Get a DEM

Download elevation data for your area (free, requires free API key):
```
python scripts/fetch_dem.py --api-key YOUR_KEY --bbox WEST SOUTH EAST NORTH
```

See [docs/dem_guide.md](docs/dem_guide.md) for dataset options and instructions
for experienced GIS users who already have a DEM.

### 4. Run the pipeline

```
python scripts/pipeline.py --dem data/dem.tif
```

This fetches nodes from both MeshCore and Meshtastic, runs viewshed analysis
for each service, and prints step-by-step progress. A QGIS project loaded with
the output files will auto-refresh as each step completes.

### 5. Create the QGIS project

From the QGIS Python Console or a QGIS-aware shell:
```
python templates/create_qgis_project.py --dem data/dem.tif
```

Opens `project/mesh_coverage.qgz` with five auto-refreshing layers:
DEM base → MeshCore coverage raster → Meshtastic coverage raster →
MeshCore nodes (blue) → Meshtastic nodes (green).

## Pipeline options

```
python scripts/pipeline.py --help

--dem PATH           Path to DEM GeoTIFF (required for viewshed steps)
--service meshcore meshtastic
                     Services to process (default: both)
--timeout 30         MQTT listen duration per service in seconds
--skip-fetch         Use existing GeoJSON files, skip MQTT fetch
--dry-run            Print steps without connecting to anything
--check-env          Verify QGIS tools and environment, then exit
```

## Individual scripts

| Script | Purpose |
|--------|---------|
| `scripts/pipeline.py` | Full orchestrator — fetch + viewshed + report |
| `scripts/fetch_dem.py` | Download DEM from OpenTopography |
| `scripts/export_nodes.py` | MeshCore node fetcher (MQTT or REST API) |
| `scripts/meshtastic_fetcher.py` | Meshtastic node fetcher (MQTT) |
| `scripts/mqtt_listener.py` | MeshCore live MQTT listener |
| `scripts/viewshed_batch.py` | GDAL viewshed + cumulative raster + gap analysis |
| `scripts/qgis_utils.py` | QGIS installation auto-detection and diagnostics |
| `templates/create_qgis_project.py` | Build the dual-layer QGIS project |

## Data sources

| Service | Broker / URL | Topics |
|---------|-------------|--------|
| MeshCore MQTT | `broker.meshcore.dev:1883` | `meshcore/#` |
| MeshCore REST | `https://map.meshcore.dev/api/nodes` | — |
| Meshtastic MQTT | `mqtt.meshtastic.org:1883` | `msh/#` |

## GeoJSON schema

Both services output the same schema so QGIS layer styles work across both:

```json
{
  "type": "FeatureCollection",
  "features": [{
    "type": "Feature",
    "geometry": { "type": "Point", "coordinates": [lon, lat, alt] },
    "properties": {
      "id": "string",
      "name": "string",
      "type": "Repeater|Companion|Router|Gateway",
      "rssi": -80,
      "snr": 5.0,
      "battery": 85,
      "timestamp": "2026-01-01T00:00:00"
    }
  }]
}
```

Fields unavailable for a given service are set to `null` (not omitted), keeping
the schema consistent. Nodes at coordinates (0, 0) are filtered out.

## Environment check

```
python scripts/qgis_utils.py
```

Prints detected QGIS paths, Python interpreter, and GDAL tool locations. Useful
for diagnosing why viewshed analysis isn't finding QGIS tools.

## Running tests

```
python -m pytest tests/ -v
```

Tests cover GeoJSON schema validation, coordinate order, null-island filtering,
MQTT message parsing, and Meshtastic state machine logic. No live broker or
DEM needed.

## Dependencies

- Python 3.8+
- `paho-mqtt` — MQTT client
- `requests` — REST API fetches
- `python-dotenv` — `.env` file support
- `numpy` — cumulative raster stacking
- `meshtastic` — Meshtastic MQTT message type constants
- QGIS 3.16+ — `gdal_viewshed` and `qgis_process` for viewshed analysis

## Future: Reticulum/RNode layer

A third layer for Reticulum network nodes is planned once MeshCore and Meshtastic
layers are stable. See [FirstPlan.md](FirstPlan.md) for details.

## License

TBD
