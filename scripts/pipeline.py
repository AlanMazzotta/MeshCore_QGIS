"""
pipeline.py — Orchestrator for the MeshCore coverage pipeline.

Designed for visual verification: each step writes output files that an open QGIS
project (with auto-refresh enabled) will reload automatically.

Workflow
--------
Step 1  Fetch MeshCore nodes from public map API  →  data/meshcore_nodes_all.geojson
Step 2  Filter nodes to DEM extent                →  data/meshcore_nodes.geojson  [QGIS refreshes]
Step 3  Run viewshed per repeater node            →  viewsheds/meshcore/           [QGIS refreshes]
Step 4  Build cumulative raster                   →  viewsheds/meshcore/cumulative_viewshed.tif

Usage
-----
    # Full pipeline:
    python scripts/pipeline.py --dem data/dem.tif

    # Skip fetch (use existing GeoJSON), only run viewshed:
    python scripts/pipeline.py --dem data/dem.tif --skip-fetch

    # Skip viewshed (use existing TIFs), only rebuild cumulative raster:
    python scripts/pipeline.py --dem data/dem.tif --skip-fetch --skip-viewshed

    # Dry run — validate environment without connecting to anything:
    python scripts/pipeline.py --dem data/dem.tif --dry-run

Environment
-----------
QGIS_BIN  Override path to QGIS bin directory (used by qgis_utils to locate tools).
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
VIEWSHED_DIR = Path("viewsheds")

_ALL_NODES_FILE = DATA_DIR / "meshcore_nodes_all.geojson"
_FILTERED_NODES_FILE = DATA_DIR / "meshcore_nodes.geojson"


def _step(n: int, total: int, description: str) -> None:
    bar = "-" * 62
    logger.info(f"\n{bar}")
    logger.info(f"  Step {n}/{total}: {description}")
    logger.info(f"{bar}")


def _success(msg: str) -> None:
    logger.info(f"  OK  {msg}")


def _warn(msg: str) -> None:
    logger.warning(f"  !   {msg}")


# ---------------------------------------------------------------------------
# Step 1: Fetch from map API
# ---------------------------------------------------------------------------

def fetch_nodes(output: Path, api_url: str, dry_run: bool) -> bool:
    if dry_run:
        logger.info(f"  [dry-run] Would fetch from map API -> {output}")
        return True

    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from export_nodes import fetch_from_map_api, nodes_to_geojson, save_geojson
    except ImportError as e:
        _warn(f"Cannot import export_nodes: {e}")
        return False

    nodes = fetch_from_map_api(api_url=api_url)
    if not nodes:
        _warn("No nodes returned from map API")
        return False

    output.parent.mkdir(parents=True, exist_ok=True)
    save_geojson(nodes_to_geojson(nodes), str(output))
    _success(f"{len(nodes)} nodes -> {output}")
    return True


# ---------------------------------------------------------------------------
# Step 2: Filter to DEM extent
# ---------------------------------------------------------------------------

def filter_nodes(all_nodes: Path, filtered_nodes: Path, dem_path: str, dry_run: bool) -> bool:
    if dry_run:
        logger.info(f"  [dry-run] Would filter {all_nodes} to DEM extent -> {filtered_nodes}")
        return True

    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from filter_by_dem import filter_geojson_to_dem
    except ImportError as e:
        _warn(f"Cannot import filter_by_dem: {e}")
        return False

    count = filter_geojson_to_dem(
        geojson_path=str(all_nodes),
        dem_path=dem_path,
        output_path=str(filtered_nodes),
        node_type="Repeater",
    )
    if count == 0:
        _warn("No Repeater nodes found within DEM extent")
        return False

    _success(f"{count} Repeater nodes within DEM -> {filtered_nodes}   (QGIS auto-refreshes in ~5s)")
    return True


# ---------------------------------------------------------------------------
# Step 3 & 4: Viewshed
# ---------------------------------------------------------------------------

def run_viewshed(nodes_path: Path, dem_path: str, output_dir: Path,
                 skip_viewshed: bool, dry_run: bool) -> bool:
    if not nodes_path.exists():
        _warn(f"Nodes file not found: {nodes_path}")
        return False

    if dry_run:
        logger.info(f"  [dry-run] Would run viewshed for nodes in {nodes_path}")
        return True

    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from viewshed_batch import BatchViewshedProcessor
    except ImportError as e:
        _warn(f"Cannot import viewshed_batch: {e}")
        return False

    try:
        processor = BatchViewshedProcessor(
            dem_path=dem_path,
            nodes_geojson=str(nodes_path),
            output_dir=str(output_dir),
            service_name="meshcore",
            skip_existing=skip_viewshed,
        )
        results = processor.process_all()
    except FileNotFoundError as e:
        _warn(str(e))
        return False

    n = results.get("repeaters_processed", 0)
    cum = results.get("cumulative")
    gaps = results.get("gaps", {})

    _success(f"{n} repeater viewsheds processed")
    if cum:
        _success(f"Cumulative raster -> {cum}   (QGIS auto-refreshes in ~10s)")
    if gaps.get("coverage_percent") is not None:
        _success(
            f"Coverage: {gaps['coverage_percent']}%  |  "
            f"Gap: {gaps.get('gap_area_m2', 0):,} m2  |  "
            f"Candidates: {len(gaps.get('gap_candidates', []))}"
        )
    return True


# ---------------------------------------------------------------------------
# Environment check
# ---------------------------------------------------------------------------

def check_environment(dem_path: str) -> bool:
    ok = True

    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from qgis_utils import describe_env, find_tool
        env = describe_env()
        logger.info("  QGIS environment:")
        for k, v in env.items():
            logger.info(f"    {k:<28} {v}")

        gdal = find_tool("gdal_viewshed")
        if gdal == "gdal_viewshed":
            _warn("gdal_viewshed not found on PATH or in QGIS install.")
            ok = False
        else:
            _success(f"Viewshed tool: {gdal}")
    except ImportError:
        _warn("qgis_utils not found")

    if dem_path and not Path(dem_path).exists():
        _warn(f"DEM not found: {dem_path}")
        ok = False
    elif dem_path:
        _success(f"DEM: {dem_path}")

    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="MeshCore coverage pipeline with live QGIS verification"
    )
    parser.add_argument(
        "--dem",
        default="data/dem.tif",
        help="Path to DEM GeoTIFF (default: data/dem.tif)",
    )
    parser.add_argument(
        "--api-url",
        default="https://map.meshcore.dev/api/v1/nodes?binary=1&short=1",
        help="MeshCore map API URL",
    )
    parser.add_argument(
        "--output-dir",
        default="viewsheds",
        help="Base directory for viewshed rasters (default: viewsheds)",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Skip API fetch; use existing data/meshcore_nodes.geojson",
    )
    parser.add_argument(
        "--skip-viewshed",
        action="store_true",
        help="Skip individual viewshed generation; only rebuild cumulative raster",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without connecting to anything",
    )
    parser.add_argument(
        "--check-env",
        action="store_true",
        help="Only check the environment and exit",
    )

    args = parser.parse_args()

    logger.info("=" * 62)
    logger.info("  MeshCore Coverage Pipeline")
    logger.info(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 62)

    _step(0, 0, "Environment check")
    env_ok = check_environment(args.dem)
    if args.check_env:
        sys.exit(0 if env_ok else 1)

    has_dem = bool(args.dem) and Path(args.dem).exists()
    total_steps = 2 + (2 if has_dem else 0)
    step = 0

    # Step 1: Fetch
    step += 1
    _step(step, total_steps, "Fetch MeshCore nodes from map API")
    if args.skip_fetch:
        if _FILTERED_NODES_FILE.exists():
            _success(f"Using existing {_FILTERED_NODES_FILE}")
        else:
            _warn(f"No existing data at {_FILTERED_NODES_FILE} — remove --skip-fetch to fetch")
    else:
        fetch_nodes(_ALL_NODES_FILE, args.api_url, args.dry_run)

        # Step 2: Filter
        step += 1
        _step(step, total_steps, "Filter nodes to DEM extent (Repeater type only)")
        if has_dem:
            filter_nodes(_ALL_NODES_FILE, _FILTERED_NODES_FILE, args.dem, args.dry_run)
        else:
            _warn("No DEM provided — skipping filter step, using all fetched nodes")

    # Step 3 & 4: Viewshed
    if has_dem:
        step += 1
        _step(step, total_steps, "Viewshed analysis")
        run_viewshed(
            nodes_path=_FILTERED_NODES_FILE,
            dem_path=args.dem,
            output_dir=Path(args.output_dir),
            skip_viewshed=args.skip_viewshed,
            dry_run=args.dry_run,
        )

    logger.info("\n" + "=" * 62)
    logger.info("  Pipeline complete.")
    if not has_dem:
        logger.info("  Note: Viewshed steps skipped (DEM not found).")
    logger.info("=" * 62)


if __name__ == "__main__":
    main()
