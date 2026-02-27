# MeshCore_QGIS

A Python toolkit for extracting live MeshCore mesh network data and performing geospatial analysis in QGIS to support repeater placement and coverage analysis.

**Status**: Phase 1 & 2 complete — foundation and script scaffolding in place.

## Overview

This project pulls live node positions from multiple MeshCore data sources (MQTT, MESH-API, MeshCore Python API, map.meshcore.dev) and exports them as GeoJSON for QGIS analysis. The toolkit supports viewshed analysis for optimal repeater placement and coverage gap identification.

For the **complete project plan, data source details, and QGIS workflow**, see [FirstPlan.md](FirstPlan.md).

## What's Implemented

### Core Scripts (scaffolds with TODO implementations)
- **`scripts/export_nodes.py`** — Extract node data from API, MQTT, CSV ? GeoJSON. Supports:
  - MeshCore Python API (USB/BLE/TCP)
  - MQTT gateway telemetry
  - CSV input
  
- **`scripts/mqtt_listener.py`** — Subscribe to MeshCore MQTT broker and stream position updates to GeoJSON
  
- **`scripts/viewshed_batch.py`** — Batch viewshed analysis (single/cumulative/gap detection)

### Configuration
- `requirements.txt` — Python dependencies (meshcore, paho-mqtt, geojson, requests, python-dotenv)
- `setup.py` — Package setup
- `.gitignore` — Excludes venv, cache, QGIS autosaves, DEM files

### Structure
```
scripts/          # Core data extraction and analysis tools
templates/        # QGIS project templates (TBD)
data/             # Data outputs and samples
docs/             # Documentation (TBD)
tests/            # Unit tests (stubs)
```

## Quick Start

### Setup environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Export nodes from MQTT
```powershell
python scripts/mqtt_listener.py --broker broker.meshcore.dev --output nodes.geojson
```

### Export nodes from MeshCore API (when implemented)
```powershell
python scripts/export_nodes.py --source api --port COM3 --output nodes.geojson
```

### Export nodes from MESH-API (when implemented)
```powershell
python scripts/export_nodes.py --source mesh-api --output nodes.geojson
```

### Run viewshed analysis (requires DEM and node GeoJSON)
```powershell
python scripts/viewshed_batch.py --dem data/dem.tif --nodes nodes.geojson
```

## Data Sources (from FirstPlan.md)

| Source | Type | Notes |
|--------|------|-------|
| **map.meshcore.dev** | Web/Interactive | Live crowd-sourced node positions |
| **MeshCore Python API** | Serial/BLE/TCP | Direct connection to node, returns lat/lon/alt/battery/uptime |
| **MQTT Bridge** | JSON over MQTT | Gateway nodes stream position telemetry |
| **MESH-API (GitHub)** | REST API | Bidirectional Meshtastic?MeshCore bridge with 30+ extensions |
| **nodakmesh.org/meshcore/map** | Web | Regional filtering by node type |

## TODO (Implementation Priority)

1. Implement MQTT GeoJSON parser in `mqtt_listener.py` (connects to live broker)
2. Implement MESH-API REST fetcher in `export_nodes.py`
3. Implement MeshCore Python API reader (USB/BLE/TCP)
4. Implement map.meshcore.dev fetcher (REST/scrape)
5. Integrate viewshed with PyQGIS or GDAL
6. Add sample data and QGIS template

## Dependencies

- Python 3.8+
- meshcore >= 0.1.0
- paho-mqtt >= 1.6.1
- geojson >= 2.5.0
- requests >= 2.28.0
- python-dotenv >= 0.21.0
- QGIS 3.16+ (desktop, for viewshed analysis)

## References

- **FirstPlan.md** — Full project plan, data sourcing, QGIS workflow, best practices
- [map.meshcore.dev](https://map.meshcore.dev)
- [nodakmesh.org/meshcore/map](https://nodakmesh.org/meshcore/map/)
- [MESH-API GitHub](https://github.com/meshtastic/MESH-API)
- [MeshCore Documentation](https://meshcore.dev)
- [QGIS Visibility Analysis Plugin](https://plugins.qgis.org)

## License

TBD

## Contact

[your contact info]
