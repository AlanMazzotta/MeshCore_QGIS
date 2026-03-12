import os
import traceback
from qgis.core import QgsTask, QgsVectorLayer, QgsProject


class FetchTask(QgsTask):
    def __init__(self, work_dir, log_fn):
        super().__init__("MeshCore: Fetch Nodes", QgsTask.CanCancel)
        self.work_dir = work_dir
        self.log = log_fn
        self.error = None

    def run(self):
        from meshcore_viewshed.core import export_nodes
        try:
            out_path = os.path.join(self.work_dir, "data", "meshcore_nodes_all.geojson")
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            nodes = export_nodes.fetch_from_map_api()
            if not nodes:
                self.error = "No nodes returned from API"
                return False
            export_nodes.save_geojson(export_nodes.nodes_to_geojson(nodes), out_path)
            return True
        except BaseException as e:
            self.error = traceback.format_exc()
            return False

    def finished(self, result):
        if result:
            self.log("[Fetch] Nodes saved.")
            self._load_layer()
        else:
            self.log(f"[Fetch] Failed: {self.error}")

    def _load_layer(self):
        path = os.path.join(self.work_dir, "data", "meshcore_nodes_all.geojson")
        if not os.path.exists(path):
            return
        layer_name = "MeshCore Nodes (all)"
        for lyr in QgsProject.instance().mapLayersByName(layer_name):
            QgsProject.instance().removeMapLayer(lyr.id())
        layer = QgsVectorLayer(path, layer_name, "ogr")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            self.log(f"[Fetch] Layer loaded: {layer_name} ({layer.featureCount()} nodes)")
        else:
            self.log("[Fetch] Layer invalid — check GeoJSON output.")
