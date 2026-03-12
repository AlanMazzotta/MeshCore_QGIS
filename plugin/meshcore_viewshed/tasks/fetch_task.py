import sys
import os
from qgis.core import QgsTask, QgsVectorLayer, QgsProject


class FetchTask(QgsTask):
    def __init__(self, repo_root, log_fn):
        super().__init__("MeshCore: Fetch Nodes", QgsTask.CanCancel)
        self.repo_root = repo_root
        self.log = log_fn
        self.error = None

    def run(self):
        scripts_dir = os.path.join(self.repo_root, "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        try:
            import export_nodes
            out_path = os.path.join(self.repo_root, "data", "meshcore_nodes_all.geojson")
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            nodes = export_nodes.fetch_from_map_api()
            if not nodes:
                self.error = "No nodes returned from API"
                return False
            export_nodes.save_geojson(export_nodes.nodes_to_geojson(nodes), out_path)
            return True
        except Exception as e:
            self.error = str(e)
            return False

    def finished(self, result):
        if result:
            self.log("[Fetch] Nodes saved.")
            self._load_layer()
        else:
            self.log(f"[Fetch] Failed: {self.error}")

    def _load_layer(self):
        path = os.path.join(self.repo_root, "data", "meshcore_nodes_all.geojson")
        if not os.path.exists(path):
            return
        layer_name = "MeshCore Nodes (all)"
        # Remove existing layer with same name before reloading
        for lyr in QgsProject.instance().mapLayersByName(layer_name):
            QgsProject.instance().removeMapLayer(lyr.id())
        layer = QgsVectorLayer(path, layer_name, "ogr")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            self.log(f"[Fetch] Layer loaded: {layer_name} ({layer.featureCount()} nodes)")
        else:
            self.log("[Fetch] Layer invalid — check GeoJSON output.")
