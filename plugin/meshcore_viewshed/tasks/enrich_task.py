import sys
import os
from qgis.core import QgsTask, QgsVectorLayer, QgsProject


class EnrichTask(QgsTask):
    def __init__(self, repo_root, log_fn):
        super().__init__("MeshCore: Enrich Nodes", QgsTask.CanCancel)
        self.repo_root = repo_root
        self.log = log_fn
        self.error = None

    def run(self):
        scripts_dir = os.path.join(self.repo_root, "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        try:
            import enrich_nodes
            nodes_path = os.path.join(self.repo_root, "data", "meshcore_nodes.geojson")
            cumulative_path = os.path.join(self.repo_root, "viewsheds", "meshcore", "cumulative_viewshed.tif")
            viewshed_dir = os.path.join(self.repo_root, "viewsheds", "meshcore")
            out_path = os.path.join(self.repo_root, "data", "meshcore_nodes_plus.geojson")
            enrich_nodes.run(
                nodes_path=nodes_path,
                cumulative_path=cumulative_path,
                viewshed_dir=viewshed_dir,
                output_path=out_path,
            )
            return True
        except Exception as e:
            self.error = str(e)
            return False

    def finished(self, result):
        if result:
            self.log("[Enrich] Complete.")
            self._load_layer()
        else:
            self.log(f"[Enrich] Failed: {self.error}")

    def _load_layer(self):
        path = os.path.join(self.repo_root, "data", "meshcore_nodes_plus.geojson")
        if not os.path.exists(path):
            return
        layer_name = "MeshCore Nodes (enriched)"
        for lyr in QgsProject.instance().mapLayersByName(layer_name):
            QgsProject.instance().removeMapLayer(lyr.id())
        layer = QgsVectorLayer(path, layer_name, "ogr")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            self.log(f"[Enrich] Layer loaded: {layer.featureCount()} nodes with derived attributes.")
        else:
            self.log("[Enrich] Layer invalid.")
