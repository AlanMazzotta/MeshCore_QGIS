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

  los_peer_count  int    Number of other repeater nodes directly visible in
                         this node's individual viewshed TIF.

  avg_peer_fspl   float  Average Free Space Path Loss (dB) to LoS peers.
                         FSPL = 32.45 + 20·log10(freq_mhz) + 20·log10(d_km).
                         Null if no LoS peers found.

  min_peer_fspl   float  FSPL (dB) to the nearest LoS peer node.

  max_peer_fspl   float  FSPL (dB) to the farthest LoS peer node.

Outputs
-------
  data/meshcore_nodes_plus.geojson

Usage (run with QGIS Python for osgeo):
  "C:\\Program Files\\QGIS 3.40.10\\apps\\Python312\\python.exe" scripts/enrich_nodes.py
"""

import argparse
import json
import logging
import math
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

import numpy as np

try:
    from osgeo import gdal
except ImportError as _e:
    raise ImportError("osgeo not available — run inside QGIS Python") from _e

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


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km between two WGS84 points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def fspl_db(d_km, freq_mhz):
    """Free Space Path Loss in dB.  d_km > 0, freq_mhz > 0."""
    return 32.45 + 20 * math.log10(freq_mhz) + 20 * math.log10(d_km)


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

def analyse_individual_viewshed(tif_path, node_lat, node_lon, gt, lat_grid, lon_grid,
                                peer_nodes=None, freq_mhz=910):
    """
    Read one individual viewshed TIF and return:
      (viewshed_pixels, dominant_dir_name, coverage_km2,
       los_peer_count, avg_peer_fspl, min_peer_fspl, max_peer_fspl)

    peer_nodes : list of (lat, lon) for all other repeater nodes.
                 When provided, each peer's pixel is sampled; visible peers
                 get a pairwise FSPL computed.
    freq_mhz   : transmit frequency for FSPL calculation (default 910).

    Returns (0, None, 0.0, 0, None, None, None) if the TIF cannot be opened.
    """
    ds = gdal.Open(str(tif_path))
    if ds is None:
        return 0, None, 0.0, 0, None, None, None

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
        return 0, None, 0.0, 0, None, None, None

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

    # Pairwise FSPL to LoS peer nodes
    fspl_vals = []
    if peer_nodes:
        raster_rows, raster_cols = arr.shape
        for peer_lat, peer_lon in peer_nodes:
            p_row, p_col = latlon_to_pixel(gt, peer_lat, peer_lon)
            if 0 <= p_row < raster_rows and 0 <= p_col < raster_cols:
                if arr[p_row, p_col] > 0:
                    d_km = haversine_km(node_lat, node_lon, peer_lat, peer_lon)
                    if d_km > 0:
                        fspl_vals.append(fspl_db(d_km, freq_mhz))

    los_peer_count = len(fspl_vals)
    avg_fspl = round(sum(fspl_vals) / los_peer_count, 1) if fspl_vals else None
    min_fspl = round(min(fspl_vals), 1) if fspl_vals else None
    max_fspl = round(max(fspl_vals), 1) if fspl_vals else None

    return n_visible, dominant, coverage_km2, los_peer_count, avg_fspl, min_fspl, max_fspl


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(nodes_path, cumulative_path, viewshed_dir, output_path, freq_mhz=910):  # 910 MHz = US LoRa band
    logger.info("Loading nodes: %s", nodes_path)
    with open(nodes_path) as f:
        geojson = json.load(f)
    features = geojson["features"]
    logger.info("  %d features", len(features))

    logger.info("Opening cumulative viewshed: %s", cumulative_path)
    cum_ds = gdal.Open(cumulative_path)
    if cum_ds is None:
        raise RuntimeError(f"Cannot open {cumulative_path}")
    cum_gt = cum_ds.GetGeoTransform()
    rows = cum_ds.RasterYSize
    cols = cum_ds.RasterXSize
    logger.info("  Raster: %d x %d", cols, rows)

    # Build shared pixel grid (same extent for all individual TIFs)
    lat_grid, lon_grid = pixel_grid(cum_gt, rows, cols)

    viewshed_dir = Path(viewshed_dir)
    out_features = []
    missing_tifs = 0

    # Build list of (lat, lon) for all nodes — used for pairwise FSPL sampling
    all_node_coords = [
        (f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0])
        for f in features
    ]

    for i, feat in enumerate(features):
        node_id = feat["properties"].get("id", "")
        node_lon, node_lat = feat["geometry"]["coordinates"][:2]
        node_type = feat["properties"].get("type", "")

        # ---- peer_count: sample cumulative raster at node location ----
        peer_count = sample_raster_at_point(cum_ds, cum_gt, node_lat, node_lon)
        if peer_count is None:
            peer_count = 0  # outside raster extent; treat as zero visible peers

        # Peers = all nodes except self
        peer_nodes = [c for j, c in enumerate(all_node_coords) if j != i]

        # ---- individual viewshed TIF ----
        tif_path = viewshed_dir / f"viewshed_{node_id}.tif"
        if tif_path.exists():
            (viewshed_pixels, dominant_dir, coverage_km2,
             los_peer_count, avg_peer_fspl, min_peer_fspl, max_peer_fspl) = \
                analyse_individual_viewshed(
                    tif_path, node_lat, node_lon, cum_gt, lat_grid, lon_grid,
                    peer_nodes=peer_nodes, freq_mhz=freq_mhz,
                )
        else:
            viewshed_pixels, dominant_dir, coverage_km2 = 0, None, 0.0
            los_peer_count, avg_peer_fspl, min_peer_fspl, max_peer_fspl = 0, None, None, None
            missing_tifs += 1

        if i % 50 == 0:
            name = (feat['properties'].get('name') or '?')[:20]
            name_safe = name.encode('ascii', 'replace').decode('ascii')
            logger.info("  Node %d/%d  %s", i + 1, len(features), name_safe)

        new_props = dict(feat["properties"])
        new_props["peer_count"]      = peer_count
        new_props["viewshed_pixels"] = viewshed_pixels
        new_props["dominant_dir"]    = dominant_dir
        new_props["coverage_km2"]    = coverage_km2
        new_props["los_peer_count"]  = los_peer_count
        # FSPL predictions for the link performance audit (see README Future section):
        # delta between these values and observed multi-observer SNR surfaces per-node performance gaps.
        new_props["avg_peer_fspl"]   = avg_peer_fspl
        new_props["min_peer_fspl"]   = min_peer_fspl
        new_props["max_peer_fspl"]   = max_peer_fspl

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
            "freq_mhz": freq_mhz,
            "attributes_added": [
                "peer_count", "viewshed_pixels", "dominant_dir", "coverage_km2",
                "los_peer_count", "avg_peer_fspl", "min_peer_fspl", "max_peer_fspl",
            ],
        },
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(out_geojson, f, indent=2)

    logger.info("Saved: %s", output_path)
    logger.info("  Nodes enriched : %d", len(out_features))
    logger.info("  Missing TIFs   : %d", missing_tifs)

    # Summary stats
    peer_vals = [f["properties"]["peer_count"] for f in out_features if f["properties"]["peer_count"] > 0]
    pix_vals  = [f["properties"]["viewshed_pixels"] for f in out_features if f["properties"]["viewshed_pixels"] > 0]
    dir_counts = {}
    for f in out_features:
        d = f["properties"]["dominant_dir"]
        if d:
            dir_counts[d] = dir_counts.get(d, 0) + 1

    if peer_vals:
        logger.info("  peer_count   min=%d  max=%d  mean=%.1f",
                    min(peer_vals), max(peer_vals), sum(peer_vals) / len(peer_vals))
    if pix_vals:
        logger.info("  viewshed_px  min=%d  max=%d  mean=%.0f",
                    min(pix_vals), max(pix_vals), sum(pix_vals) / len(pix_vals))
    if dir_counts:
        logger.info("  Dominant direction breakdown: %s", dir_counts)

    # QGIS snippet only printed when run as a standalone script (not as a task)
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
