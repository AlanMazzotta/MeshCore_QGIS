import os
import traceback
from qgis.core import QgsTask, QgsRasterLayer, QgsProject


class DirectionalTask(QgsTask):
    def __init__(self, work_dir, log_fn):
        super().__init__("MeshCore: Directional Raster", QgsTask.CanCancel)
        self.work_dir = work_dir
        self.log = log_fn
        self.error = None

    def run(self):
        from meshcore_viewshed.core import viewshed_directional
        try:
            cumulative_path = os.path.join(self.work_dir, "viewsheds", "meshcore", "cumulative_viewshed.tif")
            nodes_path = os.path.join(self.work_dir, "data", "meshcore_nodes.geojson")
            out_path = os.path.join(self.work_dir, "viewsheds", "meshcore", "directional_viewshed.tif")
            viewshed_directional.run(
                viewshed_path=cumulative_path,
                nodes_path=nodes_path,
                output_path=out_path,
                n_sectors=8,
            )
            return True
        except BaseException as e:
            self.error = traceback.format_exc()
            return False

    def finished(self, result):
        if result:
            self.log("[Directional] Complete.")
            self._load_layer()
        else:
            self.log(f"[Directional] Failed: {self.error}")

    def _load_layer(self):
        path = os.path.join(self.work_dir, "viewsheds", "meshcore", "directional_viewshed.tif")
        if not os.path.exists(path):
            return
        layer_name = "MeshCore Direction"
        for lyr in QgsProject.instance().mapLayersByName(layer_name):
            QgsProject.instance().removeMapLayer(lyr.id())
        layer = QgsRasterLayer(path, layer_name)
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            from meshcore_viewshed.symbology import apply_directional_symbology
            from qgis.utils import iface
            apply_directional_symbology(layer)
            iface.layerTreeView().refreshLayerSymbology(layer.id())
            self.log("[Directional] Layer loaded.")
