"""
enrich_nodes.py — Add viewshed-derived attributes to each repeater node.

For each node in meshcore_nodes.geojson, computes:

  peer_count      int    How many other repeaters have line-of-sight to this
                         node's location (sampled from cumulative_viewshed.tif).
                         High value = well-connected node; low = isolated.

  viewshed_pixels int    Total pixels this node's individual viewshed covers.
                         Proxy for its broadcast reach (area it can serve).

  dominant_dir    str    Primary compass sector this node's coverage extends
                         into: N / NE / E / SE / S / SW / W / NW.
                         Derived from the modal bearing across all visible
                         pixels in the node's individual viewshed TIF.

  coverage_km2    float  Approximate area covered by this node's viewshed
                         in square kilometres (pixel count * pixel area).

Outputs
-------
  data/meshcore_nodes_plus.geojson

Usage (run with QGIS Python for osgeo):
  "C:\\Program Files\\QGIS 3.40.10\\apps\\Python312\\python.exe" scripts/enrich_nodes.py
"""

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

try:
    from osgeo import gdal
except ImportError:
    print("ERROR: osgeo not available. Run with QGIS Python:")
    print(r'  "C:\Program Files\QGIS 3.40.10\apps\Python312\python.exe" scripts/enrich_nodes.py')
    sys.exit(1)

SECTOR_NAMES = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def latlon_to_pixel(gt, lat, lon):
    """Convert geographic coordinates to raster pixel (row, col)."""
    col = (lon - gt[0]) / gt[1]
    row = (lat - gt[3]) / gt[5]
    return int(row), int(col)


def pixel_grid(gt, rows, cols):
    """Return (lat_grid, lon_grid) arrays for pixel centres."""
    col_idx, row_idx = np.meshgrid(np.arange(cols, dtype=np.float64),
                                    np.arange(rows, dtype=np.float64))
    lon_grid = gt[0] + (col_idx + 0.5) * gt[1] + (row_idx + 0.5) * gt[2]
    lat_grid = gt[3] + (col_idx + 0.5) * gt[4] + (row_idx + 0.5) * gt[5]
    return lat_grid, lon_grid


def bearing_degrees(from_lat, from_lon, to_lat, to_lon):
    """Vectorised bearing (0=N, 90=E) from one point to arrays of points."""
    dlon = np.radians(to_lon - from_lon)
    lat1 = np.radians(from_lat)
    lat2 = np.radians(to_lat)
    x = np.sin(dlon) * np.cos(lat2)
    y = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    return np.degrees(np.arctan2(x, y)) % 360


def bearing_to_sector(bearing_arr, n_sectors=8):
    """Map bearings to sector indices 0..n_sectors-1."""
    size = 360.0 / n_sectors
    return ((bearing_arr + size / 2) % 360 / size).astype(np.int32) % n_sectors


def pixel_area_km2(gt, lat):
    """Approximate area of one pixel in km² at given latitude."""
    dx_km = abs(gt[1]) * 111.32 * math.cos(math.radians(lat))
    dy_km = abs(gt[5]) * 110.574
    return dx_km * dy_km


# ---------------------------------------------------------------------------
# Raster sampling
# ---------------------------------------------------------------------------

def sample_raster_at_point(ds, gt, lat, lon):
    """Return raster value at the pixel containing (lat, lon), or None."""
    band = ds.GetRasterBand(1)
    rows = ds.RasterYSize
    cols = ds.RasterXSize
    row, col = latlon_to_pixel(gt, lat, lon)
    if 0 <= row < rows and 0 <= col < cols:
        arr = band.ReadAsArray(col, row, 1, 1)
        return int(arr[0, 0])
    return None


# ---------------------------------------------------------------------------
# Per-node viewshed analysis
# ---------------------------------------------------------------------------

def analyse_individual_viewshed(tif_path, node_lat, node_lon, gt, lat_grid, lon_grid):
    """
    Read one individual viewshed TIF and return:
      (viewshed_pixels, dominant_dir_name, coverage_km2)
    Returns (0, None, 0.0) if the TIF cannot be opened.
    """
    ds = gdal.Open(str(tif_path))
    if ds is None:
        return 0, None, 0.0

    band = ds.GetRasterBand(1)
    nodata = band.GetNoDataValue()
    arr = band.ReadAsArray()
    ds = None

    if nodata is not None:
        visible = (arr > 0) & (arr != int(nodata))
    else:
        visible = arr > 0

    n_visible = int(visible.sum())
    if n_visible == 0:
        return 0, None, 0.0

    # Dominant direction: modal sector of bearings to visible pixels
    vis_lat = lat_grid[visible]
    vis_lon = lon_grid[visible]
    bearings = bearing_degrees(node_lat, node_lon, vis_lat, vis_lon)
    sectors = bearing_to_sector(bearings, n_sectors=8)
    counts = np.bincount(sectors, minlength=8)
    dominant = SECTOR_NAMES[int(counts.argmax())]

    # Approximate area
    mean_lat = float(np.mean(vis_lat))
    px_area = pixel_area_km2(gt, mean_lat)
    coverage_km2 = round(n_visible * px_area, 2)

    return n_visible, dominant, coverage_km2


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(nodes_path, cumulative_path, viewshed_dir, output_path):
    print(f"Loading nodes: {nodes_path}")
    with open(nodes_path) as f:
        geojson = json.load(f)
    features = geojson["features"]
    print(f"  {len(features)} features")

    print(f"Opening cumulative viewshed: {cumulative_path}")
    cum_ds = gdal.Open(cumulative_path)
    if cum_ds is None:
        print(f"ERROR: Cannot open {cumulative_path}")
        sys.exit(1)
    cum_gt = cum_ds.GetGeoTransform()
    rows = cum_ds.RasterYSize
    cols = cum_ds.RasterXSize
    print(f"  Raster: {cols} x {rows}")

    # Build shared pixel grid (same extent for all individual TIFs)
    lat_grid, lon_grid = pixel_grid(cum_gt, rows, cols)

    viewshed_dir = Path(viewshed_dir)
    out_features = []
    missing_tifs = 0

    for i, feat in enumerate(features):
        node_id = feat["properties"].get("id", "")
        node_lon, node_lat = feat["geometry"]["coordinates"][:2]
        node_type = feat["properties"].get("type", "")

        # ---- peer_count: sample cumulative raster at node location ----
        peer_count = sample_raster_at_point(cum_ds, cum_gt, node_lat, node_lon)
        if peer_count is None:
            peer_count = -1  # outside raster extent

        # ---- individual viewshed TIF ----
        tif_path = viewshed_dir / f"viewshed_{node_id}.tif"
        if tif_path.exists():
            viewshed_pixels, dominant_dir, coverage_km2 = analyse_individual_viewshed(
                tif_path, node_lat, node_lon, cum_gt, lat_grid, lon_grid
            )
        else:
            viewshed_pixels, dominant_dir, coverage_km2 = 0, None, 0.0
            missing_tifs += 1

        if i % 50 == 0:
            name = (feat['properties'].get('name') or '?')[:20]
            name_safe = name.encode('ascii', 'replace').decode('ascii')
            print(f"  Node {i+1}/{len(features)}  {name_safe}")

        new_props = dict(feat["properties"])
        new_props["peer_count"]      = peer_count
        new_props["viewshed_pixels"] = viewshed_pixels
        new_props["dominant_dir"]    = dominant_dir
        new_props["coverage_km2"]    = coverage_km2

        out_features.append({
            "type": "Feature",
            "geometry": feat["geometry"],
            "properties": new_props,
        })

    cum_ds = None

    out_geojson = {
        "type": "FeatureCollection",
        "features": out_features,
        "metadata": {
            **geojson.get("metadata", {}),
            "enriched": True,
            "attributes_added": ["peer_count", "viewshed_pixels", "dominant_dir", "coverage_km2"],
        },
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(out_geojson, f, indent=2)

    print(f"\nSaved: {output_path}")
    print(f"  Nodes enriched : {len(out_features)}")
    print(f"  Missing TIFs   : {missing_tifs}")

    # Summary stats
    peer_vals = [f["properties"]["peer_count"] for f in out_features if f["properties"]["peer_count"] >= 0]
    pix_vals  = [f["properties"]["viewshed_pixels"] for f in out_features if f["properties"]["viewshed_pixels"] > 0]
    dir_counts = {}
    for f in out_features:
        d = f["properties"]["dominant_dir"]
        if d:
            dir_counts[d] = dir_counts.get(d, 0) + 1

    if peer_vals:
        print(f"\n  peer_count   min={min(peer_vals)}  max={max(peer_vals)}  mean={sum(peer_vals)/len(peer_vals):.1f}")
    if pix_vals:
        print(f"  viewshed_px  min={min(pix_vals):,}  max={max(pix_vals):,}  mean={sum(pix_vals)/len(pix_vals):,.0f}")
    if dir_counts:
        print("\n  Dominant direction breakdown:")
        for name in SECTOR_NAMES:
            count = dir_counts.get(name, 0)
            bar = "#" * (count * 30 // max(dir_counts.values()))
            print(f"    {name:3s}  {count:3d}  {bar}")

    print("\nTo load in QGIS, paste into Script Editor (Ctrl+Alt+S):")
    _print_qgis_snippet(output_path)


def _print_qgis_snippet(output_path):
    abs_path = str(Path(output_path).resolve())
    print(f"""
# === Paste into QGIS Script Editor (Ctrl+Alt+S) ===
from qgis.core import QgsVectorLayer, QgsProject
layer = iface.addVectorLayer(r"{abs_path}", "meshcore_nodes_plus", "ogr")
if layer and layer.isValid():
    print("Loaded meshcore_nodes_plus — style by peer_count or dominant_dir")
else:
    print("ERROR: Could not load layer")
# ===================================================
""")


def main():
    parser = argparse.ArgumentParser(
        description="Enrich MeshCore node GeoJSON with viewshed-derived attributes"
    )
    parser.add_argument("--nodes",      default="data/meshcore_nodes.geojson")
    parser.add_argument("--cumulative", default="viewsheds/meshcore/cumulative_viewshed.tif")
    parser.add_argument("--viewshed-dir", default="viewsheds/meshcore")
    parser.add_argument("--output",     default="data/meshcore_nodes_plus.geojson")
    args = parser.parse_args()

    run(
        nodes_path=args.nodes,
        cumulative_path=args.cumulative,
        viewshed_dir=args.viewshed_dir,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
