import os
import traceback
from pathlib import Path
from qgis.core import QgsTask, QgsRasterLayer, QgsProject


class DemTask(QgsTask):
    def __init__(self, work_dir, bbox, api_key, log_fn):
        super().__init__("MeshCore: Download DEM", QgsTask.CanCancel)
        self.work_dir = work_dir
        self.bbox = bbox  # (west, south, east, north)
        self.api_key = api_key
        self.log = log_fn
        self.error = None

    def run(self):
        from meshcore_viewshed.core import fetch_dem, filter_by_dem
        try:
            out_path = os.path.join(self.work_dir, "data", "dem.tif")
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            west, south, east, north = self.bbox
            ok = fetch_dem.download_dem(
                west=west, south=south, east=east, north=north,
                output_path=Path(out_path),
                api_key=self.api_key,
                dataset="COP30",
            )
            if not ok:
                self.error = "download_dem returned False"
                return False
            filter_by_dem.filter_nodes(
                nodes_path=os.path.join(self.work_dir, "data", "meshcore_nodes_all.geojson"),
                dem_path=out_path,
                output_path=os.path.join(self.work_dir, "data", "meshcore_nodes.geojson"),
            )
            return True
        except BaseException as e:
            self.error = traceback.format_exc()
            return False

    def finished(self, result):
        if result:
            self.log("[DEM] Download complete. Nodes filtered to extent.")
            self._load_layer()
        else:
            self.log(f"[DEM] Failed: {self.error}")

    def _load_layer(self):
        path = os.path.join(self.work_dir, "data", "dem.tif")
        if not os.path.exists(path):
            return
        layer_name = "Elevation (m)"
        for lyr in QgsProject.instance().mapLayersByName(layer_name):
            QgsProject.instance().removeMapLayer(lyr.id())
        layer = QgsRasterLayer(path, layer_name)
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            from meshcore_viewshed.symbology import apply_dem_symbology
            from qgis.utils import iface
            apply_dem_symbology(layer)
            iface.layerTreeView().refreshLayerSymbology(layer.id())
            self.log("[DEM] Layer loaded.")
        else:
            self.log("[DEM] Layer invalid.")
