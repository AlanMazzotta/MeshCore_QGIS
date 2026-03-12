"""
pipeline.py — Step-by-step orchestrator for the MeshCore + Meshtastic coverage pipeline.

Designed for visual verification: each step writes output files that an open QGIS
project (with auto-refresh enabled) will reload automatically.

Workflow
--------
Step 1  Fetch MeshCore nodes  →  data/meshcore_nodes.geojson    [QGIS refreshes]
Step 2  Fetch Meshtastic nodes →  data/meshtastic_nodes.geojson  [QGIS refreshes]
Step 3  Run viewshed per service → viewsheds/{service}/          [QGIS refreshes]
Step 4  Build cumulative raster  → viewsheds/{service}/cumulative_viewshed.tif

Usage
-----
    # Full pipeline (both services, 30s MQTT listen):
    python scripts/pipeline.py --dem data/dem.tif

    # MeshCore only, 60s listen:
    python scripts/pipeline.py --dem data/dem.tif --service meshcore --timeout 60

    # Dry run — validate environment without connecting to MQTT:
    python scripts/pipeline.py --dem data/dem.tif --dry-run

    # Skip data fetch (use existing GeoJSON), just run viewshed:
    python scripts/pipeline.py --dem data/dem.tif --skip-fetch

Environment
-----------
QGIS_BIN  Override path to QGIS bin directory (used by qgis_utils to locate tools).
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
VIEWSHED_DIR = Path("viewsheds")


# ---------------------------------------------------------------------------
# Step helpers
# ---------------------------------------------------------------------------

def _step(n: int, total: int, description: str) -> None:
    bar = "─" * 60
    logger.info(f"\n{bar}")
    logger.info(f"  Step {n}/{total}: {description}")
    logger.info(f"{bar}")


def _success(msg: str) -> None:
    logger.info(f"  ✓  {msg}")


def _warn(msg: str) -> None:
    logger.warning(f"  !  {msg}")


# ---------------------------------------------------------------------------
# Step 1 & 2: Data fetch
# ---------------------------------------------------------------------------

def fetch_meshcore(output: Path, broker: str, timeout: int, dry_run: bool) -> bool:
    """Fetch MeshCore nodes via MQTT and write GeoJSON."""
    if dry_run:
        logger.info(f"  [dry-run] Would connect to {broker} for {timeout}s → {output}")
        return True

    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from export_nodes import export_from_mqtt, nodes_to_geojson, save_geojson
    except ImportError as e:
        _warn(f"Cannot import export_nodes: {e}")
        return False

    nodes = export_from_mqtt(broker=broker, timeout=timeout)
    if not nodes:
        _warn("No MeshCore nodes collected from MQTT")
        return False

    output.parent.mkdir(parents=True, exist_ok=True)
    geojson = nodes_to_geojson(nodes)
    save_geojson(geojson, str(output))
    _success(f"{len(nodes)} MeshCore nodes → {output}   (QGIS auto-refreshes in ~5s)")
    return True


def fetch_meshtastic(output: Path, broker: str, timeout: int, dry_run: bool) -> bool:
    """Fetch Meshtastic nodes via MQTT and write GeoJSON."""
    if dry_run:
        logger.info(f"  [dry-run] Would connect to {broker} for {timeout}s → {output}")
        return True

    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from meshtastic_fetcher import fetch_from_mqtt, save_geojson
    except ImportError as e:
        _warn(f"Cannot import meshtastic_fetcher: {e}")
        return False

    nodes = fetch_from_mqtt(broker=broker, timeout=timeout)
    if not nodes:
        _warn("No Meshtastic nodes collected from MQTT")
        return False

    output.parent.mkdir(parents=True, exist_ok=True)
    save_geojson(nodes, str(output), broker=broker)
    _success(f"{len(nodes)} Meshtastic nodes → {output}   (QGIS auto-refreshes in ~5s)")
    return True


# ---------------------------------------------------------------------------
# Step 3 & 4: Viewshed
# ---------------------------------------------------------------------------

def run_viewshed(service: str, nodes_path: Path, dem_path: str,
                 output_dir: Path, dry_run: bool) -> bool:
    """Run batch viewshed analysis for one service and write rasters."""
    if not nodes_path.exists():
        _warn(f"Nodes file not found: {nodes_path} — skipping viewshed for {service}")
        return False

    if dry_run:
        logger.info(f"  [dry-run] Would run viewshed for {service} nodes in {nodes_path}")
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
            service_name=service,
        )
        results = processor.process_all()
    except FileNotFoundError as e:
        _warn(str(e))
        return False

    n = results.get("repeaters_processed", 0)
    cum = results.get("cumulative")
    gaps = results.get("gaps", {})

    _success(f"{n} repeater viewsheds processed for {service}")
    if cum:
        _success(f"Cumulative raster → {cum}   (QGIS auto-refreshes in ~10s)")
    if gaps.get("coverage_percent") is not None:
        _success(
            f"Coverage: {gaps['coverage_percent']}%  |  "
            f"Gap: {gaps.get('gap_area_m2', 0):,} m²  |  "
            f"Candidates: {len(gaps.get('gap_candidates', []))}"
        )
    return True


# ---------------------------------------------------------------------------
# Environment check
# ---------------------------------------------------------------------------

def check_environment(dem_path: str) -> bool:
    """Verify QGIS tools and Python dependencies are available."""
    ok = True

    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from qgis_utils import describe_env, find_tool
        env = describe_env()
        logger.info("  QGIS environment:")
        for k, v in env.items():
            logger.info(f"    {k:<28} {v}")

        gdal = find_tool("gdal_viewshed")
        qp = find_tool("qgis_process")
        if gdal == "gdal_viewshed" and qp == "qgis_process":
            _warn("Neither gdal_viewshed nor qgis_process found on PATH or in QGIS install.")
            _warn("Run `python scripts/qgis_utils.py --write-vscode` to configure the environment.")
            ok = False
        else:
            _success(f"Viewshed tool: {gdal if gdal != 'gdal_viewshed' else qp}")
    except ImportError:
        _warn("qgis_utils not found — tool path detection unavailable")

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
        description="MeshCore + Meshtastic coverage pipeline with live QGIS verification"
    )
    parser.add_argument(
        "--dem",
        default="",
        help="Path to DEM GeoTIFF. Required for viewshed steps.",
    )
    parser.add_argument(
        "--service",
        nargs="+",
        default=["meshcore", "meshtastic"],
        choices=["meshcore", "meshtastic"],
        help="Services to process (default: both)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="MQTT listen duration per service in seconds (default: 30)",
    )
    parser.add_argument(
        "--meshcore-broker",
        default="broker.meshcore.dev",
        help="MeshCore MQTT broker (default: broker.meshcore.dev)",
    )
    parser.add_argument(
        "--meshtastic-broker",
        default="mqtt.meshtastic.org",
        help="Meshtastic MQTT broker (default: mqtt.meshtastic.org)",
    )
    parser.add_argument(
        "--output-dir",
        default="viewsheds",
        help="Base directory for viewshed rasters (default: viewsheds)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without connecting to any services",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Skip MQTT fetch steps; use existing GeoJSON files for viewshed",
    )
    parser.add_argument(
        "--check-env",
        action="store_true",
        help="Only check the environment and exit",
    )

    args = parser.parse_args()

    logger.info("=" * 62)
    logger.info("  MeshCore + Meshtastic Coverage Pipeline")
    logger.info(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 62)

    # ---- Environment check ----
    _step(0, 0, "Environment check")
    env_ok = check_environment(args.dem)
    if args.check_env:
        sys.exit(0 if env_ok else 1)

    services = args.service
    has_dem = bool(args.dem) and Path(args.dem).exists()
    total_steps = len(services) * (2 if has_dem else 1)
    step = 0

    for service in services:
        nodes_path = DATA_DIR / f"{service}_nodes.geojson"

        # ---- Fetch ----
        if not args.skip_fetch:
            step += 1
            if service == "meshcore":
                _step(step, total_steps, f"Fetch MeshCore nodes ({args.timeout}s MQTT listen)")
                fetch_meshcore(nodes_path, args.meshcore_broker, args.timeout, args.dry_run)
            elif service == "meshtastic":
                _step(step, total_steps, f"Fetch Meshtastic nodes ({args.timeout}s MQTT listen)")
                fetch_meshtastic(nodes_path, args.meshtastic_broker, args.timeout, args.dry_run)
        else:
            if nodes_path.exists():
                _success(f"Using existing {nodes_path}")
            else:
                _warn(f"No existing data at {nodes_path}")

        # ---- Viewshed ----
        if has_dem:
            step += 1
            _step(step, total_steps, f"Viewshed analysis — {service}")
            run_viewshed(
                service=service,
                nodes_path=nodes_path,
                dem_path=args.dem,
                output_dir=Path(args.output_dir),
                dry_run=args.dry_run,
            )

    logger.info("\n" + "=" * 62)
    logger.info("  Pipeline complete.")
    if not has_dem:
        logger.info("  Note: Viewshed steps skipped (no --dem provided).")
    logger.info("=" * 62)


if __name__ == "__main__":
    main()
