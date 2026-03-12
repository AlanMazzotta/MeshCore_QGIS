"""
download_dem_from_canvas.py — Download a DEM from OpenTopography using the
current QGIS map canvas extent.

Run from the QGIS Python Console (Plugins > Python Console > Show Editor,
open this file, then click Run).

Workflow
--------
1. Navigate in QGIS to your area of interest
2. Run this script
3. A red rectangle appears on the map showing the exact download area
4. Confirm or cancel in the dialog
5. DEM downloads in the background — QGIS stays responsive
6. DEM is added as a layer automatically when complete

Dataset options (edit DATASET below):
    COP30    Copernicus 30m — recommended, best global quality
    SRTMGL1  NASA SRTM 30m
    NASADEM  NASA DEM 30m   — reprocessed SRTM, good void fill
    AW3D30   JAXA AW3D 30m
    SRTMGL3  NASA SRTM 90m  — lower resolution, smaller download
"""

import json
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration — edit these if needed
# ---------------------------------------------------------------------------
DATASET = "COP30"
OUTPUT_PATH = "data/dem.tif"   # relative to the QGIS project file location


# ---------------------------------------------------------------------------
# Resolve project root — check project dir and parent (handles subdirectory
# project files like Test_Project/Test_1_ASM.qgz with .env in repo root)
# ---------------------------------------------------------------------------
def _find_project_root() -> Path:
    try:
        proj_path = QgsProject.instance().fileName()
        if proj_path:
            return Path(proj_path).parent
    except Exception:
        pass
    return Path.cwd()


def _load_api_key(project_root: Path) -> str:
    candidates = [project_root / ".env", project_root.parent / ".env"]
    for env_file in candidates:
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line.startswith("OPENTOPO_API_KEY"):
                    return line.split("=", 1)[-1].strip().strip('"').strip("'")
    return os.environ.get("OPENTOPO_API_KEY", "")


project_root = _find_project_root()
api_key = _load_api_key(project_root)

if not api_key:
    iface.messageBar().pushCritical(
        "DEM Download",
        "No API key found. Add OPENTOPO_API_KEY=your_key to your .env file. "
        "Free registration: https://portal.opentopography.org/newUser"
    )
    raise SystemExit("No OpenTopography API key found.")


# ---------------------------------------------------------------------------
# Get canvas extent in both canvas CRS (for display) and WGS84 (for API)
# ---------------------------------------------------------------------------
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsNetworkAccessManager,
    QgsRasterLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsRubberBand
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.PyQt.QtWidgets import QMessageBox

canvas = iface.mapCanvas()
canvas_extent = canvas.extent()
canvas_crs = canvas.mapSettings().destinationCrs()
wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")

if canvas_crs != wgs84:
    transform = QgsCoordinateTransform(canvas_crs, wgs84, QgsProject.instance())
    wgs84_extent = transform.transformBoundingBox(canvas_extent)
else:
    wgs84_extent = canvas_extent

west  = round(wgs84_extent.xMinimum(), 6)
east  = round(wgs84_extent.xMaximum(), 6)
south = round(wgs84_extent.yMinimum(), 6)
north = round(wgs84_extent.yMaximum(), 6)

if west >= east or south >= north:
    raise ValueError(f"Invalid extent: W={west} E={east} S={south} N={north}")

area = (east - west) * (north - south)


# ---------------------------------------------------------------------------
# Draw preview rectangle on canvas so user sees exactly what will download
# ---------------------------------------------------------------------------
_rubber_band = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
_rubber_band.setColor(QColor(220, 50, 50, 180))
_rubber_band.setFillColor(QColor(220, 50, 50, 40))
_rubber_band.setWidth(2)
_rubber_band.setToGeometry(QgsGeometry.fromRect(canvas_extent), None)


# ---------------------------------------------------------------------------
# Confirmation dialog
# ---------------------------------------------------------------------------
size_warning = ""
if area > 25:
    size_warning = "\n\nWARNING: This area is very large and may time out.\nZoom in for a smaller tile."

confirm = QMessageBox.question(
    None,
    f"Confirm DEM Download — {DATASET}",
    f"Download {DATASET} (30m) elevation data for the red area?\n\n"
    f"  West:  {west}\n"
    f"  East:  {east}\n"
    f"  South: {south}\n"
    f"  North: {north}\n"
    f"  Area:  {area:.2f}°²"
    f"{size_warning}\n\n"
    f"Output: {OUTPUT_PATH}",
    QMessageBox.Yes | QMessageBox.No,
    QMessageBox.Yes,
)

if confirm != QMessageBox.Yes:
    _rubber_band.reset()
    print("Download cancelled.")
    raise SystemExit("Cancelled by user.")


# ---------------------------------------------------------------------------
# Build request URL
# ---------------------------------------------------------------------------
import urllib.parse

_params = urllib.parse.urlencode({
    "demtype": DATASET,
    "south": south,
    "north": north,
    "west": west,
    "east": east,
    "outputFormat": "GTiff",
    "API_Key": api_key,
})
_url = f"https://portal.opentopography.org/API/globaldem?{_params}"
_output_path = project_root / OUTPUT_PATH
_output_path.parent.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Non-blocking download via QgsNetworkAccessManager
# QGIS remains fully responsive while the DEM downloads in the background.
# ---------------------------------------------------------------------------
iface.messageBar().pushInfo(
    "DEM Download", f"Downloading {DATASET} in background — QGIS remains responsive..."
)
print(f"Downloading {DATASET} → {_output_path}")


def _on_finished():
    try:
        if _reply.error() != QNetworkReply.NoError:
            iface.messageBar().pushCritical(
                "DEM Download", f"Network error: {_reply.errorString()}"
            )
            return

        data = bytes(_reply.readAll())

        # OpenTopography returns JSON on error, binary GeoTIFF on success
        if data.strip().startswith(b"{"):
            try:
                err = json.loads(data)
                msg = err.get("error") or err.get("message") or str(err)
            except Exception:
                msg = data.decode(errors="replace")[:300]
            iface.messageBar().pushCritical("DEM Download", f"API error: {msg}")
            return

        _output_path.write_bytes(data)
        size_mb = len(data) / 1_048_576
        print(f"Saved {size_mb:.1f} MB → {_output_path}")

        dem_layer = QgsRasterLayer(str(_output_path), f"DEM ({DATASET})")
        if dem_layer.isValid():
            QgsProject.instance().addMapLayer(dem_layer)
            iface.messageBar().pushSuccess(
                "DEM Download", f"{DATASET} loaded ({size_mb:.1f} MB) — layer added."
            )
            print(f"Layer 'DEM ({DATASET})' added.")
        else:
            iface.messageBar().pushWarning(
                "DEM Download", f"File saved to {_output_path} but layer failed to load."
            )

    except Exception as e:
        iface.messageBar().pushCritical("DEM Download", f"Unexpected error: {e}")
        print(f"ERROR: {e}")

    finally:
        _rubber_band.reset()
        _reply.deleteLater()


_reply = QgsNetworkAccessManager.instance().get(QNetworkRequest(QUrl(_url)))
_reply.finished.connect(_on_finished)
print("Download running in background...")
