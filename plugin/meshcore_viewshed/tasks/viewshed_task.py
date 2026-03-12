import os
from qgis.core import QgsTask, QgsRasterLayer, QgsProject, QgsVectorLayer


class ViewshedTask(QgsTask):
    def __init__(self, work_dir, log_fn, progress_fn=None):
        super().__init__("MeshCore: Run Viewshed", QgsTask.CanCancel)
        self.work_dir = work_dir
        self.log = log_fn
        self.progress_fn = progress_fn
        self.error = None

    def run(self):
        from meshcore_viewshed.core.viewshed_batch import BatchViewshedProcessor
        try:
            nodes_path = os.path.join(self.work_dir, "data", "meshcore_nodes.geojson")
            dem_path = os.path.join(self.work_dir, "data", "dem.tif")
            out_dir = os.path.join(self.work_dir, "viewsheds", "meshcore")
            os.makedirs(out_dir, exist_ok=True)

            processor = BatchViewshedProcessor(
                dem_path=dem_path,
                nodes_geojson=nodes_path,
                output_dir=out_dir,
            )
            processor.process_all()
            self.setProgress(100)
            if self.progress_fn:
                self.progress_fn(100)
            return True
        except Exception as e:
            self.error = str(e)
            return False

    def finished(self, result):
        if result:
            self.log("[Viewshed] Complete.")
            self._load_layers()
        else:
            self.log(f"[Viewshed] Failed: {self.error}")

    def _load_layers(self):
        cumulative = os.path.join(self.work_dir, "viewsheds", "meshcore", "cumulative_viewshed.tif")
        nodes_plus = os.path.join(self.work_dir, "data", "meshcore_nodes.geojson")

        for path, name, is_raster in [
            (cumulative, "MeshCore Coverage", True),
            (nodes_plus, "MeshCore Nodes", False),
        ]:
            if not os.path.exists(path):
                continue
            for lyr in QgsProject.instance().mapLayersByName(name):
                QgsProject.instance().removeMapLayer(lyr.id())
            if is_raster:
                layer = QgsRasterLayer(path, name)
            else:
                layer = QgsVectorLayer(path, name, "ogr")
            if layer.isValid():
                QgsProject.instance().addMapLayer(layer)
                self.log(f"[Viewshed] Layer loaded: {name}")
