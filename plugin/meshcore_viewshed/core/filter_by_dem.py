"""Filter a node GeoJSON to only nodes within a DEM's bounding box."""
import json
import sys
import argparse
from pathlib import Path


def get_dem_bbox(dem_path: str):
    """Get bounding box of a GeoTIFF using gdalinfo."""
    import subprocess, re, shutil

    gdalinfo = shutil.which("gdalinfo") or r"C:\Program Files\QGIS 3.40.10\bin\gdalinfo.exe"
    try:
        result = subprocess.run([gdalinfo, dem_path], capture_output=True, text=True, check=True)
    except Exception as e:
        raise RuntimeError(f"gdalinfo failed: {e}") from e

    # Parse "Lower Left  ( -123.0, 45.2)" style lines
    coords = {}
    for line in result.stdout.splitlines():
        for corner in ("Lower Left", "Upper Right", "Lower Right", "Upper Left"):
            if line.strip().startswith(corner):
                m = re.search(r'\(\s*([-\d.]+),\s*([-\d.]+)\)', line)
                if m:
                    coords[corner] = (float(m.group(1)), float(m.group(2)))

    if len(coords) < 2:
        raise RuntimeError("Could not parse DEM extent from gdalinfo output")

    west = min(v[0] for v in coords.values())
    east = max(v[0] for v in coords.values())
    south = min(v[1] for v in coords.values())
    north = max(v[1] for v in coords.values())
    return west, south, east, north


def filter_nodes(nodes_path: str, dem_path: str, output_path: str = None) -> int:
    """Filter nodes GeoJSON to DEM extent. Returns count of kept nodes."""
    west, south, east, north = get_dem_bbox(dem_path)
    print(f"DEM extent: W={west:.4f} S={south:.4f} E={east:.4f} N={north:.4f}")

    with open(nodes_path) as f:
        gj = json.load(f)

    total = len(gj["features"])
    gj["features"] = [
        f for f in gj["features"]
        if west <= f["geometry"]["coordinates"][0] <= east
        and south <= f["geometry"]["coordinates"][1] <= north
    ]
    if "metadata" not in gj:
        gj["metadata"] = {}
    gj["metadata"]["count"] = len(gj["features"])

    out = output_path or nodes_path
    with open(out, "w") as f:
        json.dump(gj, f, indent=2)

    kept = len(gj["features"])
    print(f"Filtered {total} -> {kept} nodes within DEM extent")
    return kept


def main():
    parser = argparse.ArgumentParser(description="Filter nodes to DEM extent")
    parser.add_argument("--nodes", default="data/meshcore_nodes.geojson")
    parser.add_argument("--dem", required=True)
    parser.add_argument("--output", default=None, help="Output path (default: overwrites input)")
    args = parser.parse_args()

    west, south, east, north = get_dem_bbox(args.dem)
    print(f"DEM extent: W={west:.4f} S={south:.4f} E={east:.4f} N={north:.4f}")

    with open(args.nodes) as f:
        gj = json.load(f)

    total = len(gj["features"])
    gj["features"] = [
        f for f in gj["features"]
        if west <= f["geometry"]["coordinates"][0] <= east
        and south <= f["geometry"]["coordinates"][1] <= north
    ]
    gj["metadata"]["count"] = len(gj["features"])

    out = args.output or args.nodes
    with open(out, "w") as f:
        json.dump(gj, f, indent=2)

    print(f"Filtered {total} -> {len(gj['features'])} nodes within DEM extent")
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
