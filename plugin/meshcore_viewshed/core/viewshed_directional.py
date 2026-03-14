"""
viewshed_directional.py — Generate a directional viewshed raster.

For each pixel visible in the cumulative viewshed, computes the compass bearing
from the nearest repeater to that pixel and classifies it into one of 8 sectors.
The result can be loaded into QGIS and styled with a unique color per sector.

Sector encoding (output raster values):
    1 = N     (337.5 - 22.5°)
    2 = NE    (22.5  - 67.5°)
    3 = E     (67.5  - 112.5°)
    4 = SE    (112.5 - 157.5°)
    5 = S     (157.5 - 202.5°)
    6 = SW    (202.5 - 247.5°)
    7 = W     (247.5 - 292.5°)
    8 = NW    (292.5 - 337.5°)
    0 = NoData (not visible)

Usage (run with QGIS Python for osgeo access):
    "C:\\Program Files\\QGIS 3.40.10\\apps\\Python312\\python.exe" scripts/viewshed_directional.py

    Optional arguments:
    --viewshed  viewsheds/meshcore/cumulative_viewshed.tif
    --nodes     data/meshcore_nodes.geojson
    --output    viewsheds/meshcore/directional_viewshed.tif
    --sectors   8   (use 4 for N/E/S/W only)
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

try:
    from osgeo import gdal, osr
except ImportError as _e:
    raise ImportError("osgeo not available — run inside QGIS Python") from _e


SECTOR_LABELS = {
    4: ["N", "E", "S", "W"],
    8: ["N", "NE", "E", "SE", "S", "SW", "W", "NW"],
}

# Colors: (R, G, B) per sector, index 0 = first sector (N), clockwise
SECTOR_COLORS_8 = [
    (30,  100, 200),   # 1 N     — blue
    (0,   180, 180),   # 2 NE    — teal
    (50,  180,  50),   # 3 E     — green
    (180, 220,   0),   # 4 SE    — yellow-green
    (220, 130,   0),   # 5 S     — amber
    (220,  50,   0),   # 6 SW    — red-orange
    (160,   0, 200),   # 7 W     — purple
    (80,   30, 180),   # 8 NW    — indigo
]

SECTOR_COLORS_4 = [
    (30,  100, 200),   # 1 N     — blue
    (50,  180,  50),   # 2 E     — green
    (220, 130,   0),   # 3 S     — amber
    (160,   0, 200),   # 4 W     — purple
]


def bearing_degrees(from_lat, from_lon, to_lat, to_lon):
    """
    Compute bearing in degrees (0=N, 90=E, 180=S, 270=W) from one point to another.
    Inputs can be numpy arrays.
    """
    dlat = np.radians(to_lat - from_lat)
    dlon = np.radians(to_lon - from_lon)
    lat1 = np.radians(from_lat)
    lat2 = np.radians(to_lat)

    x = np.sin(dlon) * np.cos(lat2)
    y = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    bearing = np.degrees(np.arctan2(x, y)) % 360
    return bearing


def bearing_to_sector(bearing, n_sectors):
    """Map bearing (0–360) to sector index 1..n_sectors."""
    sector_size = 360.0 / n_sectors
    # Shift by half a sector so N starts centred on 0°
    return (np.floor((bearing + sector_size / 2) % 360 / sector_size).astype(np.uint8) % n_sectors) + 1


def run(viewshed_path: str, nodes_path: str, output_path: str, n_sectors: int):
    logger.info("Loading viewshed: %s", viewshed_path)
    ds = gdal.Open(viewshed_path)
    if ds is None:
        raise RuntimeError(f"Cannot open {viewshed_path}")

    band = ds.GetRasterBand(1)
    viewshed = band.ReadAsArray().astype(np.int32)
    gt = ds.GetGeoTransform()
    projection = ds.GetProjection()
    rows, cols = viewshed.shape
    logger.info("  Raster size: %d x %d pixels", cols, rows)

    # Build pixel-centre coordinate grids
    col_idx, row_idx = np.meshgrid(np.arange(cols, dtype=np.float64),
                                    np.arange(rows, dtype=np.float64))
    px_lon = gt[0] + (col_idx + 0.5) * gt[1] + (row_idx + 0.5) * gt[2]
    px_lat = gt[3] + (col_idx + 0.5) * gt[4] + (row_idx + 0.5) * gt[5]

    # Visible mask
    nodata = band.GetNoDataValue()
    if nodata is not None:
        visible = (viewshed > 0) & (viewshed != int(nodata))
    else:
        visible = viewshed > 0

    n_visible = visible.sum()
    logger.info("  Visible pixels: %d", n_visible)

    # Load repeater positions
    logger.info("Loading nodes: %s", nodes_path)
    with open(nodes_path) as f:
        geojson = json.load(f)

    repeaters = [
        (feat["geometry"]["coordinates"][1], feat["geometry"]["coordinates"][0])
        for feat in geojson["features"]
        if feat["properties"].get("type") == "Repeater"
        and feat["geometry"]["coordinates"][0] != 0.0
    ]
    logger.info("  Repeaters: %d", len(repeaters))

    if not repeaters:
        raise RuntimeError("No Repeater nodes found in GeoJSON")

    rpt_lats = np.array([r[0] for r in repeaters], dtype=np.float64)
    rpt_lons = np.array([r[1] for r in repeaters], dtype=np.float64)

    # Find nearest repeater for each pixel (memory-efficient: iterate over repeaters)
    logger.info("Computing nearest repeater per pixel...")
    cos_lat = np.cos(np.radians(np.mean(rpt_lats)))
    min_dist2 = np.full((rows, cols), np.inf, dtype=np.float64)
    nearest_idx = np.zeros((rows, cols), dtype=np.int32)

    for i, (rlat, rlon) in enumerate(repeaters):
        if i % 50 == 0:
            logger.debug("  Repeater %d/%d...", i + 1, len(repeaters))
        dlat = px_lat - rlat
        dlon = (px_lon - rlon) * cos_lat
        d2 = dlat * dlat + dlon * dlon
        closer = d2 < min_dist2
        min_dist2[closer] = d2[closer]
        nearest_idx[closer] = i

    # Compute bearing from nearest repeater to each pixel
    logger.info("Computing bearings...")
    n_lat = rpt_lats[nearest_idx]
    n_lon = rpt_lons[nearest_idx]
    bearing = bearing_degrees(n_lat, n_lon, px_lat, px_lon)

    # Classify into sectors
    sector = bearing_to_sector(bearing, n_sectors)
    sector[~visible] = 0   # mask non-visible pixels

    # Write output raster
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    driver = gdal.GetDriverByName("GTiff")
    out_ds = driver.Create(output_path, cols, rows, 1, gdal.GDT_Byte,
                           ["COMPRESS=LZW", "TILED=YES"])
    out_ds.SetGeoTransform(gt)
    out_ds.SetProjection(projection)
    # Build colour table before writing data — TIFF locks PhotometricInterpretation
    # once data is written, so the palette must be set first.
    ct = gdal.ColorTable()
    ct.SetColorEntry(0, (0, 0, 0, 0))  # transparent nodata
    colors = SECTOR_COLORS_8 if n_sectors == 8 else SECTOR_COLORS_4
    labels = SECTOR_LABELS[n_sectors]
    for idx, (r, g, b) in enumerate(colors):
        ct.SetColorEntry(idx + 1, (r, g, b, 255))

    out_band = out_ds.GetRasterBand(1)
    out_band.SetNoDataValue(0)
    out_band.SetRasterColorTable(ct)
    out_band.SetRasterColorInterpretation(gdal.GCI_PaletteIndex)
    out_band.WriteArray(sector)

    out_ds.FlushCache()
    out_ds = None
    ds = None

    logger.info("Directional viewshed written: %s", output_path)
    for i, label in enumerate(labels):
        count = int((sector == i + 1).sum())
        pct = 100 * count / n_visible if n_visible else 0
        logger.info("  %s  %d px  (%.1f%%)", label, count, pct)

    # QGIS snippet only printed when run as a standalone script (not as a task)
    _print_qgis_snippet(output_path, n_sectors)


def _print_qgis_snippet(output_path: str, n_sectors: int):
    """Print a ready-to-paste QGIS Python Console snippet."""
    colors = SECTOR_COLORS_8 if n_sectors == 8 else SECTOR_COLORS_4
    labels = SECTOR_LABELS[n_sectors]
    color_lines = []
    for i, (label, (r, g, b)) in enumerate(zip(labels, colors)):
        color_lines.append(f'    QgsPalettedRasterRenderer.Class({i+1}, QColor({r},{g},{b}), "{label}"),')

    snippet = f"""
# === Paste into QGIS Python Console (Script Editor: Ctrl+Alt+S) ===
from qgis.core import QgsPalettedRasterRenderer, QgsRasterLayer, QgsProject
from qgis.PyQt.QtGui import QColor

layer = QgsProject.instance().mapLayersByName("directional_viewshed")
if not layer:
    layer = iface.addRasterLayer(r"{output_path}", "directional_viewshed")
else:
    layer = layer[0]

classes = [
{chr(10).join(color_lines)}
]
renderer = QgsPalettedRasterRenderer(layer.dataProvider(), 1, classes)
layer.setRenderer(renderer)
layer.triggerRepaint()
print("Directional viewshed styled.")
# ===================================================================
"""
    print(snippet)


def main():
    parser = argparse.ArgumentParser(
        description="Generate a directional viewshed raster coloured by compass sector"
    )
    parser.add_argument("--viewshed", default="viewsheds/meshcore/cumulative_viewshed.tif")
    parser.add_argument("--nodes",    default="data/meshcore_nodes.geojson")
    parser.add_argument("--output",   default="viewsheds/meshcore/directional_viewshed.tif")
    parser.add_argument("--sectors",  type=int, default=8, choices=[4, 8],
                        help="Number of sectors: 4 (N/E/S/W) or 8 (adds NE/SE/SW/NW)")
    args = parser.parse_args()

    run(
        viewshed_path=args.viewshed,
        nodes_path=args.nodes,
        output_path=args.output,
        n_sectors=args.sectors,
    )


if __name__ == "__main__":
    main()
