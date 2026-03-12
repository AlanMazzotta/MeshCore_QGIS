"""
create_qgis_project.py — Build the MeshCore + Meshtastic dual-layer QGIS project.

Run this script from the QGIS Python Console (Plugins > Python Console > Run Script),
or from a shell that has the QGIS Python environment on PATH:

    python templates/create_qgis_project.py --output project/mesh_coverage.qgz

This script is designed to be run BEFORE any data exists. It creates the project
with an OpenStreetMap base layer for navigation, plus placeholder node layers that
auto-refresh as the pipeline writes data.

Intended first-run workflow
----------------------------
1. Run this script → opens project/mesh_coverage.qgz in QGIS
2. Navigate in QGIS to your area of interest
3. Run templates/download_dem_from_canvas.py from the QGIS Python Console
   → downloads DEM for the current map view, adds it as a layer
4. In VSCode terminal: python scripts/pipeline.py --dem data/dem.tif
   → node layers and viewshed rasters fill in automatically as QGIS auto-refreshes

Layers created
--------------
    1. OpenStreetMap        — web tile base map for navigation
    2. Elevation (DEM)      — local GeoTIFF, added if data/dem.tif exists
    3. MeshCore Coverage    — cumulative viewshed raster (blue ramp), added if present
    4. Meshtastic Coverage  — cumulative viewshed raster (green ramp), added if present
    5. MeshCore Nodes       — point layer, blue circles, auto-refreshes every 5s
    6. Meshtastic Nodes     — point layer, green circles, auto-refreshes every 5s
"""

import argparse
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Empty GeoJSON placeholder — lets QGIS load the layer before data arrives
# ---------------------------------------------------------------------------

_EMPTY_GEOJSON = json.dumps({
    "type": "FeatureCollection",
    "features": [],
    "metadata": {"count": 0}
})


def _ensure_placeholder(path: Path) -> None:
    """Create an empty GeoJSON file if one doesn't exist yet."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_EMPTY_GEOJSON)
        print(f"  Created placeholder: {path}")


def build_project(
    meshcore_geojson: str,
    meshtastic_geojson: str,
    dem_path: str,
    meshcore_viewshed: str = "",
    meshtastic_viewshed: str = "",
    output_path: str = "mesh_coverage.qgz",
) -> None:
    try:
        from qgis.core import (
            QgsProject,
            QgsVectorLayer,
            QgsRasterLayer,
            QgsSymbol,
            QgsSimpleMarkerSymbolLayer,
            QgsSingleSymbolRenderer,
            QgsTextFormat,
            QgsPalLayerSettings,
            QgsVectorLayerSimpleLabeling,
            QgsColorRampShader,
            QgsSingleBandPseudoColorRenderer,
            QgsRasterShader,
        )
        from qgis.PyQt.QtGui import QColor, QFont
    except ImportError:
        print(
            "ERROR: PyQGIS not available. Run this script from the QGIS Python Console "
            "or a shell with QGIS on PATH."
        )
        sys.exit(1)

    project = QgsProject.instance()
    project.clear()

    # ------------------------------------------------------------------
    # Helper: enable auto-refresh so QGIS reloads from disk when the
    # pipeline writes new data (supports live visual verification).
    # ------------------------------------------------------------------
    def enable_auto_refresh(layer, interval_ms: int):
        layer.setAutoRefreshInterval(interval_ms)
        layer.setAutoRefreshEnabled(True)

    # ------------------------------------------------------------------
    # Helper: label layer by 'name' property
    # ------------------------------------------------------------------
    def add_labels(layer, font_size: int = 8):
        settings = QgsPalLayerSettings()
        settings.fieldName = "name"
        settings.enabled = True
        fmt = QgsTextFormat()
        font = QFont()
        font.setPointSize(font_size)
        fmt.setFont(font)
        fmt.setSize(font_size)
        settings.setFormat(fmt)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        layer.setLabelsEnabled(True)

    # ------------------------------------------------------------------
    # Helper: style a point layer with a solid circle
    # ------------------------------------------------------------------
    def style_points(layer, color_hex: str, size_mm: float = 3.0):
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        marker = QgsSimpleMarkerSymbolLayer()
        marker.setColor(QColor(color_hex))
        marker.setSize(size_mm)
        symbol.changeSymbolLayer(0, marker)
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))

    # ------------------------------------------------------------------
    # Helper: apply pseudo-color ramp to a single-band raster
    # ------------------------------------------------------------------
    def style_raster(layer, color_ramp: list):
        shader_items = [
            QgsColorRampShader.ColorRampItem(val, QColor(col))
            for val, col in color_ramp
        ]
        ramp_shader = QgsColorRampShader()
        ramp_shader.setColorRampType(QgsColorRampShader.Interpolated)
        ramp_shader.setColorRampItemList(shader_items)
        raster_shader = QgsRasterShader()
        raster_shader.setRasterShaderFunction(ramp_shader)
        renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, raster_shader)
        layer.setRenderer(renderer)

    # ------------------------------------------------------------------
    # 1. OpenStreetMap base layer — always added for navigation
    # ------------------------------------------------------------------
    osm_uri = (
        "type=xyz"
        "&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        "&zmax=19&zmin=0"
        "&crs=EPSG:3857"
    )
    osm_layer = QgsRasterLayer(osm_uri, "OpenStreetMap", "wms")
    if osm_layer.isValid():
        project.addMapLayer(osm_layer)
        print("  Added OpenStreetMap base layer")
    else:
        print("  WARNING: Could not add OpenStreetMap layer (no internet connection?)")

    # ------------------------------------------------------------------
    # 2. DEM base layer (optional — added when file exists)
    # ------------------------------------------------------------------
    if Path(dem_path).exists():
        dem_layer = QgsRasterLayer(dem_path, "Elevation (DEM)")
        if dem_layer.isValid():
            project.addMapLayer(dem_layer)
            print(f"  Added DEM layer: {dem_path}")
        else:
            print(f"  WARNING: Could not load DEM from {dem_path}")
    else:
        print(f"  DEM not present yet ({dem_path}) — download it via templates/download_dem_from_canvas.py")

    # ------------------------------------------------------------------
    # 3 & 4. Viewshed rasters (optional — skip if files not present yet)
    # ------------------------------------------------------------------
    blue_ramp  = [(0, "#00000000"), (1, "#4575b4"), (5, "#ffffbf"), (10, "#d73027")]
    green_ramp = [(0, "#00000000"), (1, "#1a9641"), (5, "#ffffbf"), (10, "#d7191c")]

    if meshcore_viewshed and Path(meshcore_viewshed).exists():
        mc_vs = QgsRasterLayer(meshcore_viewshed, "MeshCore Coverage")
        if mc_vs.isValid():
            style_raster(mc_vs, blue_ramp)
            enable_auto_refresh(mc_vs, 10_000)
            project.addMapLayer(mc_vs)

    if meshtastic_viewshed and Path(meshtastic_viewshed).exists():
        mt_vs = QgsRasterLayer(meshtastic_viewshed, "Meshtastic Coverage")
        if mt_vs.isValid():
            style_raster(mt_vs, green_ramp)
            enable_auto_refresh(mt_vs, 10_000)
            project.addMapLayer(mt_vs)

    # ------------------------------------------------------------------
    # 5 & 6. Node layers — placeholder GeoJSON created if absent so the
    # layer exists from the start and auto-refreshes when data arrives.
    # ------------------------------------------------------------------
    _ensure_placeholder(Path(meshcore_geojson))
    _ensure_placeholder(Path(meshtastic_geojson))

    mc_layer = QgsVectorLayer(meshcore_geojson, "MeshCore Nodes", "ogr")
    if mc_layer.isValid():
        style_points(mc_layer, "#2166ac", size_mm=3.5)
        add_labels(mc_layer)
        enable_auto_refresh(mc_layer, 5_000)
        project.addMapLayer(mc_layer)
        print("  Added MeshCore Nodes layer (empty, auto-refreshes when pipeline runs)")
    else:
        print(f"  WARNING: Could not load MeshCore GeoJSON from {meshcore_geojson}")

    mt_layer = QgsVectorLayer(meshtastic_geojson, "Meshtastic Nodes", "ogr")
    if mt_layer.isValid():
        style_points(mt_layer, "#1a9641", size_mm=3.5)
        add_labels(mt_layer)
        enable_auto_refresh(mt_layer, 5_000)
        project.addMapLayer(mt_layer)
        print("  Added Meshtastic Nodes layer (empty, auto-refreshes when pipeline runs)")
    else:
        print(f"  WARNING: Could not load Meshtastic GeoJSON from {meshtastic_geojson}")

    # ------------------------------------------------------------------
    # Save project
    # ------------------------------------------------------------------
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    project.setFileName(str(out.resolve()))
    ok = project.write()
    if ok:
        print(f"\nProject saved: {output_path}")
        print("Next steps:")
        print("  1. Open the project in QGIS")
        print("  2. Navigate to your area of interest")
        print("  3. Run templates/download_dem_from_canvas.py from the QGIS Python Console")
        print("  4. Run: python scripts/pipeline.py --dem data/dem.tif")
    else:
        print(f"ERROR: Failed to write project to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Create the MeshCore + Meshtastic QGIS project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--meshcore", default="data/meshcore_nodes.geojson",
                        help="MeshCore nodes GeoJSON (created as empty placeholder if absent)")
    parser.add_argument("--meshtastic", default="data/meshtastic_nodes.geojson",
                        help="Meshtastic nodes GeoJSON (created as empty placeholder if absent)")
    parser.add_argument("--dem", default="data/dem.tif",
                        help="DEM GeoTIFF (optional at project creation time)")
    parser.add_argument("--meshcore-viewshed", default="",
                        help="MeshCore cumulative viewshed raster (optional)")
    parser.add_argument("--meshtastic-viewshed", default="",
                        help="Meshtastic cumulative viewshed raster (optional)")
    parser.add_argument("--output", default="project/mesh_coverage.qgz",
                        help="Output QGIS project file (default: project/mesh_coverage.qgz)")

    args = parser.parse_args()

    build_project(
        meshcore_geojson=args.meshcore,
        meshtastic_geojson=args.meshtastic,
        dem_path=args.dem,
        meshcore_viewshed=args.meshcore_viewshed,
        meshtastic_viewshed=args.meshtastic_viewshed,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
