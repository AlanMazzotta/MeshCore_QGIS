"""
fetch_dem.py — Download a DEM (Digital Elevation Model) from OpenTopography.

OpenTopography provides free global DEM datasets via a REST API. A free account
is required to get an API key (registration takes ~2 minutes).

    Sign up: https://portal.opentopography.org/newUser

Usage
-----
    # Auto-detect bounding box from existing node GeoJSON files:
    python scripts/fetch_dem.py --api-key YOUR_KEY

    # Explicit bounding box (west south east north):
    python scripts/fetch_dem.py --api-key YOUR_KEY --bbox -123.5 45.2 -121.8 46.0

    # Higher-resolution Copernicus DEM (30m, best available globally):
    python scripts/fetch_dem.py --api-key YOUR_KEY --dataset COP30

    # Save to a specific path:
    python scripts/fetch_dem.py --api-key YOUR_KEY --output data/my_area.tif

    # Store the API key in a .env file and omit --api-key:
    #   echo OPENTOPO_API_KEY=your_key >> .env
    python scripts/fetch_dem.py --bbox -123.5 45.2 -121.8 46.0

Available datasets (--dataset):
    SRTMGL1     NASA SRTM 30m  (global, 2000 acquisition)
    SRTMGL3     NASA SRTM 90m  (global, lower resolution)
    AW3D30      JAXA AW3D 30m  (global)
    COP30       Copernicus 30m (global, most recent, recommended)
    NASADEM     NASADEM 30m    (reprocessed SRTM, often better than SRTMGL1)

Output
------
    data/dem.tif — GeoTIFF, WGS84 (EPSG:4326), single band, elevation in metres.
    The pipeline and viewshed_batch.py both default to this path.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Buffer added around the auto-detected bounding box (decimal degrees)
_BBOX_BUFFER_DEG = 0.15

_OPENTOPO_URL = "https://portal.opentopography.org/API/globaldem"

_DATASET_CHOICES = ["SRTMGL1", "SRTMGL3", "AW3D30", "COP30", "NASADEM"]


# ---------------------------------------------------------------------------
# Bounding box helpers
# ---------------------------------------------------------------------------

def _bbox_from_geojson(path: Path) -> tuple:
    """Return (west, south, east, north) from a GeoJSON FeatureCollection."""
    with open(path) as f:
        data = json.load(f)
    lons, lats = [], []
    for feat in data.get("features", []):
        coords = feat.get("geometry", {}).get("coordinates", [])
        if coords and len(coords) >= 2:
            lons.append(coords[0])
            lats.append(coords[1])
    if not lons:
        return None
    return min(lons), min(lats), max(lons), max(lats)


def _auto_bbox(data_dir: Path, buffer: float) -> tuple:
    """
    Scan data/*.geojson and return a combined bounding box with buffer.
    Returns None if no valid GeoJSON is found.
    """
    all_lons, all_lats = [], []
    for gj in data_dir.glob("*.geojson"):
        result = _bbox_from_geojson(gj)
        if result:
            w, s, e, n = result
            all_lons += [w, e]
            all_lats += [s, n]

    if not all_lons:
        return None

    return (
        round(min(all_lons) - buffer, 6),
        round(min(all_lats) - buffer, 6),
        round(max(all_lons) + buffer, 6),
        round(max(all_lats) + buffer, 6),
    )


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_dem(
    west: float,
    south: float,
    east: float,
    north: float,
    dataset: str,
    api_key: str,
    output_path: Path,
) -> bool:
    """
    Download a DEM tile from OpenTopography and save it as a GeoTIFF.

    Returns True on success, False on failure.
    """
    try:
        import requests
    except ImportError:
        print("ERROR: requests library not installed. Run: pip install requests")
        return False

    params = {
        "demtype": dataset,
        "south": south,
        "north": north,
        "west": west,
        "east": east,
        "outputFormat": "GTiff",
        "API_Key": api_key,
    }

    area_deg2 = (east - west) * (north - south)
    print(f"Requesting {dataset} DEM for bbox [{west:.4f}, {south:.4f}, {east:.4f}, {north:.4f}]")
    print(f"  Area: ~{area_deg2:.3f}°² — may take a few seconds for large areas...")

    try:
        response = requests.get(_OPENTOPO_URL, params=params, timeout=120, stream=True)
    except Exception as e:
        print(f"ERROR: Request failed: {e}")
        return False

    # OpenTopography returns JSON on error, binary GeoTIFF on success
    content_type = response.headers.get("Content-Type", "")
    if "application/json" in content_type or response.status_code != 200:
        try:
            error_data = response.json()
            msg = error_data.get("error") or error_data.get("message") or str(error_data)
        except Exception:
            msg = response.text[:300]
        print(f"ERROR: OpenTopography returned an error (HTTP {response.status_code}):")
        print(f"  {msg}")
        if "API_Key" in msg or "key" in msg.lower():
            print("\n  Get a free API key at: https://portal.opentopography.org/newUser")
            print("  Then re-run with: --api-key YOUR_KEY")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    bytes_written = 0
    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=65536):
            f.write(chunk)
            bytes_written += len(chunk)

    size_mb = bytes_written / 1_048_576
    print(f"  Downloaded {size_mb:.1f} MB → {output_path}")
    print(f"\nDEM ready. Use with the pipeline:")
    print(f"  python scripts/pipeline.py --dem {output_path}")
    return True


# ---------------------------------------------------------------------------
# Key persistence
# ---------------------------------------------------------------------------

def _save_key_to_env(api_key: str) -> None:
    """
    Write OPENTOPO_API_KEY to the .env file so it is remembered for future runs.
    Creates the file if absent; updates the existing line if present.
    The .env file is gitignored and never committed.
    """
    env_path = Path(".env")
    key_line = f"OPENTOPO_API_KEY={api_key}\n"

    if env_path.exists():
        lines = env_path.read_text().splitlines(keepends=True)
        updated = False
        for i, line in enumerate(lines):
            if line.startswith("OPENTOPO_API_KEY"):
                if lines[i] == key_line:
                    return  # already correct, nothing to write
                lines[i] = key_line
                updated = True
                break
        if not updated:
            lines.append(key_line)
        env_path.write_text("".join(lines))
    else:
        env_path.write_text(key_line)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Download a DEM from OpenTopography for viewshed analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("OPENTOPO_API_KEY", ""),
        help=(
            "OpenTopography API key. "
            "Free registration: https://portal.opentopography.org/newUser  "
            "Can also be set via OPENTOPO_API_KEY environment variable or .env file."
        ),
    )
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        help=(
            "Bounding box in decimal degrees (WGS84). "
            "If omitted, auto-detected from data/*.geojson files."
        ),
    )
    parser.add_argument(
        "--buffer",
        type=float,
        default=_BBOX_BUFFER_DEG,
        help=f"Degrees to add around auto-detected bbox (default: {_BBOX_BUFFER_DEG})",
    )
    parser.add_argument(
        "--dataset",
        default="COP30",
        choices=_DATASET_CHOICES,
        help="DEM dataset to download (default: COP30 — Copernicus 30m, recommended)",
    )
    parser.add_argument(
        "--output",
        default="data/dem.tif",
        help="Output GeoTIFF path (default: data/dem.tif)",
    )

    args = parser.parse_args()

    # Load .env if present (picks up OPENTOPO_API_KEY)
    try:
        from dotenv import load_dotenv
        load_dotenv()
        if not args.api_key:
            args.api_key = os.environ.get("OPENTOPO_API_KEY", "")
    except ImportError:
        pass

    if not args.api_key:
        print("ERROR: No API key provided.")
        print("  Get a free key at: https://portal.opentopography.org/newUser")
        print("  Then run: python scripts/fetch_dem.py --api-key YOUR_KEY")
        print("  Or add OPENTOPO_API_KEY=your_key to your .env file.")
        sys.exit(1)

    # Persist the key to .env so the user doesn't need to supply it again
    _save_key_to_env(args.api_key)

    # Resolve bounding box
    if args.bbox:
        west, south, east, north = args.bbox
    else:
        data_dir = Path("data")
        bbox = _auto_bbox(data_dir, args.buffer)
        if bbox is None:
            print(
                "ERROR: No bounding box provided and no GeoJSON found in data/.\n"
                "  Either run the pipeline first to fetch nodes, or supply --bbox WEST SOUTH EAST NORTH"
            )
            sys.exit(1)
        west, south, east, north = bbox
        print(f"Auto-detected bbox (with {args.buffer}° buffer): {west}, {south}, {east}, {north}")

    # Validate
    if west >= east or south >= north:
        print(f"ERROR: Invalid bounding box: west={west} east={east} south={south} north={north}")
        sys.exit(1)

    ok = download_dem(
        west=west, south=south, east=east, north=north,
        dataset=args.dataset,
        api_key=args.api_key,
        output_path=Path(args.output),
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
