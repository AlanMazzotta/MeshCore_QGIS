import os
import traceback
from qgis.core import QgsTask, QgsVectorLayer, QgsProject


class EnrichTask(QgsTask):
    def __init__(self, work_dir, log_fn):
        super().__init__("MeshCore: Enrich Nodes", QgsTask.CanCancel)
        self.work_dir = work_dir
        self.log = log_fn
        self.error = None

    def run(self):
        from meshcore_viewshed.core import enrich_nodes
        try:
            nodes_path = os.path.join(self.work_dir, "data", "meshcore_nodes.geojson")
            cumulative_path = os.path.join(self.work_dir, "viewsheds", "meshcore", "cumulative_viewshed.tif")
            viewshed_dir = os.path.join(self.work_dir, "viewsheds", "meshcore")
            out_path = os.path.join(self.work_dir, "data", "meshcore_nodes_plus.geojson")
            enrich_nodes.run(
                nodes_path=nodes_path,
                cumulative_path=cumulative_path,
                viewshed_dir=viewshed_dir,
                output_path=out_path,
            )
            return True
        except BaseException as e:
            self.error = traceback.format_exc()
            return False

    def finished(self, result):
        if result:
            self.log("[Enrich] Complete.")
            self._load_layer()
        else:
            self.log(f"[Enrich] Failed: {self.error}")

    def _load_layer(self):
        path = os.path.join(self.work_dir, "data", "meshcore_nodes_plus.geojson")
        if not os.path.exists(path):
            return
        layer_name = "MeshCore Nodes (enriched)"
        for lyr in QgsProject.instance().mapLayersByName(layer_name):
            QgsProject.instance().removeMapLayer(lyr.id())
        layer = QgsVectorLayer(path, layer_name, "ogr")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            from meshcore_viewshed.symbology import apply_nodes_plus_symbology
            apply_nodes_plus_symbology(layer)
            self.log(f"[Enrich] Layer loaded: {layer.featureCount()} nodes with derived attributes.")
        else:
            self.log("[Enrich] Layer invalid.")
