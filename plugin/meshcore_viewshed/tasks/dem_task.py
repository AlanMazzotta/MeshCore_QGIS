import sys
import os
from qgis.core import QgsTask, QgsRasterLayer, QgsProject


class DemTask(QgsTask):
    def __init__(self, repo_root, bbox, api_key, log_fn):
        super().__init__("MeshCore: Download DEM", QgsTask.CanCancel)
        self.repo_root = repo_root
        self.bbox = bbox  # (west, south, east, north)
        self.api_key = api_key
        self.log = log_fn
        self.error = None

    def run(self):
        scripts_dir = os.path.join(self.repo_root, "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        try:
            import fetch_dem
            out_path = os.path.join(self.repo_root, "data", "dem.tif")
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            west, south, east, north = self.bbox
            fetch_dem._save_key_to_env(self.api_key)
            ok = fetch_dem.download_dem(
                west=west, south=south, east=east, north=north,
                output_path=__import__("pathlib").Path(out_path),
                api_key=self.api_key,
                dataset="COP30",
            )
            if not ok:
                self.error = "download_dem returned False"
                return False
            return True
        except Exception as e:
            self.error = str(e)
            return False

    def finished(self, result):
        if result:
            self.log("[DEM] Download complete.")
            self._load_layer()
            self._run_filter()
        else:
            self.log(f"[DEM] Failed: {self.error}")

    def _load_layer(self):
        path = os.path.join(self.repo_root, "data", "dem.tif")
        if not os.path.exists(path):
            return
        layer_name = "DEM"
        for lyr in QgsProject.instance().mapLayersByName(layer_name):
            QgsProject.instance().removeMapLayer(lyr.id())
        layer = QgsRasterLayer(path, layer_name)
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            self.log("[DEM] Layer loaded.")
        else:
            self.log("[DEM] Layer invalid.")

    def _run_filter(self):
        """Filter all nodes to DEM extent and keep Repeaters only."""
        scripts_dir = os.path.join(self.repo_root, "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        try:
            import filter_by_dem
            filter_by_dem.filter_nodes(
                nodes_path=os.path.join(self.repo_root, "data", "meshcore_nodes_all.geojson"),
                dem_path=os.path.join(self.repo_root, "data", "dem.tif"),
                output_path=os.path.join(self.repo_root, "data", "meshcore_nodes.geojson"),
            )
            self.log("[DEM] Nodes filtered to DEM extent.")
        except Exception as e:
            self.log(f"[DEM] Filter warning: {e}")
