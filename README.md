# MeshCore_QGIS

A Python-based toolkit for extracting MeshCore mesh network data and performing geospatial analysis with QGIS for repeater placement optimization.

## Project Status

**Phase 1-2 Complete**: Core infrastructure and script skeleton in place. Scripts are ready for implementation of MeshCore API integration.

## What's Included

### Scripts
- **`export_nodes.py`** — CLI tool to extract node data from multiple sources (API, MQTT, CSV) and output GeoJSON
- **`mqtt_listener.py`** — Background service to subscribe to MeshCore MQTT gateway telemetry and stream updates
- **`viewshed_batch.py`** — Batch viewshed analysis wrapper for QGIS viewshed generation and gap analysis

### Project Structure
```
MeshCore_QGIS/
├── README.md                      # This file
├── FirstPlan.md                   # Original vision & reference
├── .gitignore                     # Git configuration
├── requirements.txt               # Python dependencies
├── setup.py                       # Package configuration
│
├── scripts/                       # Core analysis tools
│   ├── __init__.py
│   ├── export_nodes.py           # Node data extraction
│   ├── mqtt_listener.py          # MQTT telemetry listener
│   └── viewshed_batch.py         # Viewshed analysis
│
├── templates/                     # QGIS resources
│   └── (QGIS project templates - TBD)
│
├── data/                          # Data artifacts
│   └── .gitkeep
│
├── docs/                          # Documentation
│   └── (Documentation files - TBD)
│
└── tests/                         # Unit tests
    ├── __init__.py
    └── test_export.py            # Test stubs
# MeshCore_QGIS

A Python toolkit for extracting MeshCore mesh network data and performing geospatial analysis in QGIS to support repeater placement and coverage analysis.

Status: Phase 1 & 2 complete — project foundation and script skeletons are present.

What this repository contains (current state):

- `scripts/export_nodes.py` — CLI skeleton to extract node data from API, MQTT, or CSV and export GeoJSON.
- `scripts/mqtt_listener.py` — MQTT telemetry listener skeleton that can stream position updates to a GeoJSON file.
- `scripts/viewshed_batch.py` — Viewshed analysis scaffolding for single, cumulative, and batch processing (PyQGIS/GDAL integration TODO).
- `requirements.txt`, `setup.py`, and `.gitignore` for packaging and environment setup.
- `templates/`, `data/`, and `docs/` directories for QGIS templates, sample data, and documentation (placeholders).

Quick start (local development):

1. Create a virtual environment and install dependencies:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Export nodes (example using CSV input):
```powershell
python scripts/export_nodes.py --source csv --csv data/sample_nodes.csv --output nodes.geojson
```

3. Listen to MQTT (example):
```powershell
python scripts/mqtt_listener.py --broker broker.meshcore.dev --output data/telemetry.geojson
```

4. Run batch viewshed (requires DEM and node GeoJSON):
```powershell
python scripts/viewshed_batch.py --dem data/dem.tif --nodes data/nodes.geojson
```

Notes:
- Core functions for MeshCore API, MQTT parsing, and PyQGIS/GDAL viewshed processing are TODO — current scripts are scaffolds with CLI and data-handling helpers.
- See `FirstPlan.md` for the original project plan, data sources, and workflow guidance.

Next steps (recommended):
1. Implement MeshCore API integration for `export_nodes.py` (USB/BLE/TCP serial reads).
2. Implement MQTT parsing and robust GeoJSON streaming in `mqtt_listener.py`.
3. Integrate viewshed generation using PyQGIS or GDAL in `viewshed_batch.py`.
4. Add sample data and a QGIS project template in `templates/`.

License: TBD

Contact: [your contact info]
