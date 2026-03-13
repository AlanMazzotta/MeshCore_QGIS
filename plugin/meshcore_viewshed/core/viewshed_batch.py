"""
Batch viewshed analysis for repeater placement optimization.

Generates viewsheds from DEM and observer point layer, supports:
- Single point viewshed
- Cumulative multi-point viewshed
- Batch processing with result aggregation
"""

import argparse
import json
import logging
import subprocess
import sys
import tempfile
from typing import List, Dict, Any, Optional
from pathlib import Path

# Soft-import so the module loads even without a QGIS environment
try:
    from meshcore_viewshed.core.qgis_utils import find_tool
except ImportError:
    try:
        from qgis_utils import find_tool
    except ImportError:
        def find_tool(name: str) -> str:  # type: ignore[misc]
            return name

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ViewshedAnalyzer:
    """Wrapper for QGIS viewshed analysis."""
    
    def __init__(self, dem_path: str, output_dir: str = "./viewsheds", service_name: str = ""):
        """
        Initialize viewshed analyzer.

        Args:
            dem_path: Path to DEM GeoTIFF file
            output_dir: Base directory for output rasters
            service_name: Optional service label (e.g. 'meshcore', 'meshtastic').
                          When provided, outputs go into output_dir/service_name/.
        """
        self.dem_path = dem_path
        base = Path(output_dir)
        self.output_dir = base / service_name if service_name else base
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if not Path(dem_path).exists():
            raise FileNotFoundError(f"DEM not found: {dem_path}")
    
    def single_viewshed(self, lat: float, lon: float, observer_height: float = 2.0,
                       output_name: str = None) -> Optional[str]:
        """
        Generate viewshed from single observer point.
        
        Args:
            lat: Observer latitude
            lon: Observer longitude
            observer_height: Height above DEM (meters, default 2m for human eye)
            output_name: Output raster filename
        
        Returns:
            Path to output raster or None if failed
        """
        if not output_name:
            output_name = f"viewshed_{lat:.4f}_{lon:.4f}.tif"
        
        output_path = self.output_dir / output_name
        
        logger.info(f"Generating viewshed from ({lat}, {lon})")

        # Try qgis_process first (better CRS handling), fall back to gdal_viewshed directly.
        qgis_process = find_tool("qgis_process")
        gdal_viewshed = find_tool("gdal_viewshed")

        success = False

        # --- Primary: qgis_process run gdal:viewshed ---
        # Observer point must be passed as a temporary GeoJSON file.
        with tempfile.NamedTemporaryFile(
            suffix=".geojson", mode="w", delete=False
        ) as tmp:
            tmp_observer = tmp.name
            json.dump({
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {},
                }],
            }, tmp)

        try:
            cmd_qp = [
                qgis_process, "run", "gdal:viewshed",
                f"--INPUT={self.dem_path}",
                "--BAND=1",
                f"--OBSERVER_HEIGHT={observer_height}",
                "--TARGET_HEIGHT=0",
                "--MAX_DISTANCE=-1",
                f"--OUTPUT={output_path}",
            ]
            _kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}
            result = subprocess.run(cmd_qp, capture_output=True, text=True, check=True, **_kw)
            logger.debug(result.stdout)
            success = True
        except FileNotFoundError:
            logger.debug("qgis_process not found; falling back to gdal_viewshed")
        except subprocess.CalledProcessError as e:
            logger.debug(f"qgis_process gdal:viewshed failed: {e.stderr.strip()}")
        finally:
            Path(tmp_observer).unlink(missing_ok=True)

        # --- Fallback: gdal_viewshed directly ---
        if not success:
            cmd = [
                gdal_viewshed,
                "-ox", str(lon),
                "-oy", str(lat),
                "-oz", str(observer_height),
                "-of", "GTiff",
                self.dem_path,
                str(output_path),
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True, **_kw)
                logger.debug(result.stdout)
                success = True
            except FileNotFoundError:
                logger.error(
                    "Neither qgis_process nor gdal_viewshed found. "
                    "Install QGIS or set the QGIS_BIN environment variable. "
                    "Run: python scripts/qgis_utils.py for diagnostics."
                )
                return None
            except subprocess.CalledProcessError as e:
                logger.error(f"gdal_viewshed failed for ({lat}, {lon}): {e.stderr}")
                return None

        if not success:
            return None

        logger.info(f"Output: {output_path}")
        return str(output_path)
    
    def cumulative_viewshed(self, points: List[Dict[str, float]], 
                           output_name: str = "cumulative_viewshed.tif") -> Optional[str]:
        """
        Stack multiple viewsheds to identify coverage gaps.
        
        Args:
            points: List of dicts with keys: lat, lon, observer_height (optional)
            output_name: Output raster filename
        
        Returns:
            Path to output cumulative raster
        """
        output_path = self.output_dir / output_name
        
        logger.info(f"Generating cumulative viewshed from {len(points)} points")

        try:
            import numpy as np
            from osgeo import gdal
        except ImportError as exc:
            logger.error(
                f"Missing dependency for cumulative viewshed ({exc}). "
                "Install numpy and GDAL (osgeo) — both are available in the QGIS Python environment."
            )
            return None

        individual_paths = []
        for i, pt in enumerate(points):
            name = f"_vs_tmp_{i:04d}.tif"
            path = self.single_viewshed(
                pt["lat"], pt["lon"],
                observer_height=pt.get("observer_height", 2.0),
                output_name=name,
            )
            if path:
                individual_paths.append(path)

        if not individual_paths:
            logger.error("No individual viewsheds generated; cannot build cumulative raster.")
            return None

        # Open first raster to get shape/geotransform/projection
        ds0 = gdal.Open(individual_paths[0])
        cols = ds0.RasterXSize
        rows = ds0.RasterYSize
        gt = ds0.GetGeoTransform()
        proj = ds0.GetProjection()
        ds0 = None

        cumulative = np.zeros((rows, cols), dtype=np.uint16)
        for path in individual_paths:
            ds = gdal.Open(path)
            band = ds.GetRasterBand(1)
            arr = band.ReadAsArray().astype(np.uint16)
            # gdal_viewshed outputs 255 for visible, 0 for not visible
            cumulative += (arr > 0).astype(np.uint16)
            ds = None

        driver = gdal.GetDriverByName("GTiff")
        out_ds = driver.Create(str(output_path), cols, rows, 1, gdal.GDT_UInt16)
        out_ds.SetGeoTransform(gt)
        out_ds.SetProjection(proj)
        out_ds.GetRasterBand(1).WriteArray(cumulative)
        out_ds.GetRasterBand(1).SetNoDataValue(0)
        out_ds.FlushCache()
        out_ds = None

        # Remove temp individual viewsheds
        for path in individual_paths:
            Path(path).unlink(missing_ok=True)

        logger.info(f"Cumulative viewshed written to {output_path}")
        return str(output_path)
    
    def gap_analysis(self, cumulative_viewshed: str, threshold: int = 1) -> Dict[str, Any]:
        """
        Identify coverage gaps from cumulative viewshed.
        
        Args:
            cumulative_viewshed: Path to cumulative viewshed raster
            threshold: Minimum visibility count to consider "covered"
        
        Returns:
            Dictionary with gap statistics
        """
        logger.info(f"Analyzing coverage gaps (threshold: {threshold} nodes)")

        try:
            import numpy as np
            from osgeo import gdal, osr
        except ImportError as exc:
            logger.error(f"Missing dependency for gap analysis ({exc}).")
            return {"error": str(exc)}

        ds = gdal.Open(cumulative_viewshed)
        if ds is None:
            logger.error(f"Cannot open raster: {cumulative_viewshed}")
            return {}

        band = ds.GetRasterBand(1)
        arr = band.ReadAsArray()
        nodata = band.GetNoDataValue()
        gt = ds.GetGeoTransform()
        ds = None

        valid_mask = arr != nodata if nodata is not None else np.ones_like(arr, dtype=bool)
        covered_mask = (arr >= threshold) & valid_mask
        gap_mask = (~covered_mask) & valid_mask

        # Pixel area in degrees² — convert to approximate m² using mid-latitude
        pixel_width_deg = abs(gt[1])
        pixel_height_deg = abs(gt[5])
        origin_lat = gt[3]
        mid_lat = origin_lat - (arr.shape[0] / 2) * pixel_height_deg
        meters_per_deg_lat = 111_320.0
        meters_per_deg_lon = 111_320.0 * abs(__import__("math").cos(__import__("math").radians(mid_lat)))
        pixel_area_m2 = pixel_width_deg * meters_per_deg_lon * pixel_height_deg * meters_per_deg_lat

        total_pixels = int(valid_mask.sum())
        covered_pixels = int(covered_mask.sum())
        gap_pixels = int(gap_mask.sum())

        # Find centroid of the largest contiguous gap region as a repeater candidate
        gap_candidates = []
        gap_rows, gap_cols = np.where(gap_mask)
        if gap_rows.size > 0:
            centroid_row = int(gap_rows.mean())
            centroid_col = int(gap_cols.mean())
            cand_lon = gt[0] + centroid_col * gt[1]
            cand_lat = gt[3] + centroid_row * gt[5]
            gap_candidates.append({"latitude": round(cand_lat, 6), "longitude": round(cand_lon, 6)})

        stats = {
            "total_area_m2": round(total_pixels * pixel_area_m2),
            "covered_area_m2": round(covered_pixels * pixel_area_m2),
            "gap_area_m2": round(gap_pixels * pixel_area_m2),
            "coverage_percent": round(covered_pixels / total_pixels * 100, 2) if total_pixels else 0.0,
            "gap_candidates": gap_candidates,
        }

        logger.info(
            f"Coverage: {stats['coverage_percent']}% "
            f"({covered_pixels}/{total_pixels} pixels, threshold={threshold})"
        )
        return stats


class BatchViewshedProcessor:
    """Process multiple viewshed analyses."""
    
    def __init__(self, dem_path: str, nodes_geojson: str, output_dir: str = "./viewsheds",
                 service_name: str = "", skip_existing: bool = False):
        """
        Initialize batch processor.

        Args:
            dem_path: Path to DEM GeoTIFF
            nodes_geojson: Path to nodes GeoJSON layer
            output_dir: Base output directory for viewshed rasters
            service_name: Service label used as a sub-directory (e.g. 'meshcore')
            skip_existing: If True, skip individual viewshed generation and only
                           rebuild the cumulative raster from existing TIFs.
        """
        self.analyzer = ViewshedAnalyzer(dem_path, output_dir=output_dir, service_name=service_name)
        self.nodes_geojson = nodes_geojson
        self.skip_existing = skip_existing
        self.results = {}
    
    def load_nodes(self) -> List[Dict[str, Any]]:
        """Load node coordinates from GeoJSON."""
        import json
        
        try:
            with open(self.nodes_geojson) as f:
                geojson = json.load(f)
            
            nodes = []
            for feature in geojson.get("features", []):
                coords = feature["geometry"]["coordinates"]
                props = feature["properties"]
                
                nodes.append({
                    "id": props.get("id"),
                    "name": props.get("name"),
                    "lon": coords[0],
                    "lat": coords[1],
                    "type": props.get("type"),
                    "altitude": props.get("altitude", 0)
                })
            
            logger.info(f"Loaded {len(nodes)} nodes from {self.nodes_geojson}")
            return nodes
        
        except FileNotFoundError:
            logger.error(f"GeoJSON not found: {self.nodes_geojson}")
            return []
    
    def process_all(self) -> Dict[str, Any]:
        """
        Process viewshed for all repeater nodes.
        
        Returns:
            Dictionary of results
        """
        nodes = self.load_nodes()
        repeaters = [n for n in nodes if n["type"] == "Repeater"]
        
        logger.info(f"Processing {len(repeaters)} repeater nodes")
        
        viewshed_paths = []
        for node in repeaters:
            output_name = f"viewshed_{node['id']}.tif"
            existing = self.analyzer.output_dir / output_name
            if self.skip_existing and existing.exists():
                viewshed_paths.append(str(existing))
                continue
            path = self.analyzer.single_viewshed(
                node["lat"], node["lon"],
                observer_height=2.0,
                output_name=output_name
            )
            if path:
                viewshed_paths.append(path)
        
        if viewshed_paths:
            cumulative = self.analyzer.cumulative_viewshed(
                [{"lat": n["lat"], "lon": n["lon"]} for n in repeaters]
            )
            gaps = self.analyzer.gap_analysis(cumulative)
            
            self.results = {
                "repeaters_processed": len(repeaters),
                "viewsheds": viewshed_paths,
                "cumulative": cumulative,
                "gaps": gaps
            }
        
        return self.results


def main():
    """CLI interface for batch viewshed analysis."""
    parser = argparse.ArgumentParser(
        description="Batch viewshed analysis for repeater placement"
    )
    parser.add_argument(
        "--dem",
        required=True,
        help="Path to DEM GeoTIFF file"
    )
    parser.add_argument(
        "--nodes",
        required=True,
        help="Path to nodes GeoJSON layer"
    )
    parser.add_argument(
        "--output-dir",
        default="./viewsheds",
        help="Base output directory for viewshed rasters (default: ./viewsheds)"
    )
    parser.add_argument(
        "--service",
        default="",
        help="Service name sub-directory (e.g. 'meshcore' or 'meshtastic')"
    )

    args = parser.parse_args()

    try:
        processor = BatchViewshedProcessor(
            args.dem, args.nodes,
            output_dir=args.output_dir,
            service_name=args.service,
        )
        results = processor.process_all()
        
        logger.info(f"✓ Processed {results.get('repeaters_processed', 0)} repeaters")
        logger.info(f"✓ Cumulative viewshed: {results.get('cumulative')}")
    
    except Exception as e:
        logger.error(f"Failed: {e}")


if __name__ == "__main__":
    main()
