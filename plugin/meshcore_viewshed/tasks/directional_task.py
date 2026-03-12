import sys
import os
from qgis.core import QgsTask, QgsRasterLayer, QgsProject


class DirectionalTask(QgsTask):
    def __init__(self, repo_root, log_fn):
        super().__init__("MeshCore: Directional Raster", QgsTask.CanCancel)
        self.repo_root = repo_root
        self.log = log_fn
        self.error = None

    def run(self):
        scripts_dir = os.path.join(self.repo_root, "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        try:
            import viewshed_directional
            cumulative_path = os.path.join(self.repo_root, "viewsheds", "meshcore", "cumulative_viewshed.tif")
            nodes_path = os.path.join(self.repo_root, "data", "meshcore_nodes.geojson")
            out_path = os.path.join(self.repo_root, "viewsheds", "meshcore", "directional_viewshed.tif")
            viewshed_directional.run(
                viewshed_path=cumulative_path,
                nodes_path=nodes_path,
                output_path=out_path,
                n_sectors=8,
            )
            return True
        except Exception as e:
            self.error = str(e)
            return False

    def finished(self, result):
        if result:
            self.log("[Directional] Complete.")
            self._load_layer()
        else:
            self.log(f"[Directional] Failed: {self.error}")

    def _load_layer(self):
        path = os.path.join(self.repo_root, "viewsheds", "meshcore", "directional_viewshed.tif")
        if not os.path.exists(path):
            return
        layer_name = "MeshCore Direction"
        for lyr in QgsProject.instance().mapLayersByName(layer_name):
            QgsProject.instance().removeMapLayer(lyr.id())
        layer = QgsRasterLayer(path, layer_name)
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            self.log("[Directional] Layer loaded.")
