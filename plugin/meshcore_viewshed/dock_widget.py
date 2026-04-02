import os
from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QProgressBar,
    QTextEdit, QGroupBox, QSizePolicy, QCheckBox
)
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsApplication, QgsProject, QgsSettings


class MeshCoreViewshedDock(QDockWidget):
    default_area = Qt.RightDockWidgetArea
    _SETTINGS_KEY    = "meshcore_viewshed/opentopo_api_key"
    _BASEMAP_KEY     = "meshcore_viewshed/add_basemap"
    _PACKETS_PATH_KEY = "meshcore_viewshed/packets_path"
    _BASEMAP_URL  = ("type=xyz&url=https://basemaps.cartocdn.com/"
                     "dark_all/{z}/{x}/{y}.png&zmax=19&zmin=0")
    _BASEMAP_NAME = "Basemap (CartoDB Dark)"

    def __init__(self, iface, parent=None):
        super().__init__("MeshCore Viewshed", parent)
        self.iface = iface
        self.setObjectName("MeshCoreViewshedDock")
        self.setMinimumWidth(280)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # --- API key ---
        api_group = QGroupBox("OpenTopography API Key")
        api_layout = QVBoxLayout(api_group)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("Required for DEM download")
        self.api_key_edit.setText(QgsSettings().value(self._SETTINGS_KEY, ""))
        api_layout.addWidget(self.api_key_edit)
        layout.addWidget(api_group)

        # --- Region ---
        region_group = QGroupBox("Region")
        region_layout = QVBoxLayout(region_group)
        self.bbox_btn = QPushButton("Use Current Canvas Extent")
        self.bbox_btn.clicked.connect(self._set_bbox_from_canvas)
        self.bbox_label = QLabel("No extent set")
        self.bbox_label.setWordWrap(True)
        self.bbox_label.setStyleSheet("color: gray; font-size: 10px;")
        region_layout.addWidget(self.bbox_btn)
        region_layout.addWidget(self.bbox_label)
        layout.addWidget(region_group)

        # --- Pipeline steps ---
        steps_group = QGroupBox("Pipeline Steps")
        steps_layout = QVBoxLayout(steps_group)

        self.btn_fetch = QPushButton("1. Fetch Nodes")
        self.btn_dem = QPushButton("2. Download DEM")
        self.btn_viewshed = QPushButton("3. Run Viewshed")
        self.btn_directional = QPushButton("4. Directional Raster")
        self.btn_enrich = QPushButton("5. Enrich Nodes")

        for btn in (self.btn_fetch, self.btn_dem, self.btn_viewshed,
                    self.btn_directional, self.btn_enrich):
            steps_layout.addWidget(btn)

        layout.addWidget(steps_group)

        # --- Options ---
        self.chk_basemap = QCheckBox("Add dark basemap (CartoDB)")
        self.chk_basemap.setChecked(
            QgsSettings().value(self._BASEMAP_KEY, True, type=bool)
        )
        self.chk_basemap.stateChanged.connect(
            lambda state: QgsSettings().setValue(self._BASEMAP_KEY, bool(state))
        )
        layout.addWidget(self.chk_basemap)

        # --- Run All ---
        self.btn_run_all = QPushButton("Run All")
        self.btn_run_all.setStyleSheet(
            "QPushButton { background-color: #2d6a4f; color: white; font-weight: bold; padding: 6px; }"
            "QPushButton:hover { background-color: #40916c; }"
            "QPushButton:disabled { background-color: #888; }"
        )
        layout.addWidget(self.btn_run_all)

        # --- Progress ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # --- Log ---
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(150)
        self.log.setStyleSheet("font-size: 10px; font-family: monospace;")
        layout.addWidget(self.log)

        # --- Signal Quality (POC) ---
        snr_group = QGroupBox("Signal Quality (POC)")
        snr_layout = QVBoxLayout(snr_group)

        snr_layout.addWidget(QLabel("Packets file (NDJSON):"))
        self.packets_path_edit = QLineEdit()
        self.packets_path_edit.setPlaceholderText(
            "e.g. C:/…/meshcore-packet-capture/data/packets.ndjson"
        )
        self.packets_path_edit.setText(
            QgsSettings().value(self._PACKETS_PATH_KEY, "")
        )
        snr_layout.addWidget(self.packets_path_edit)

        self.btn_snr = QPushButton("Generate SNR Heatmap")
        snr_layout.addWidget(self.btn_snr)
        layout.addWidget(snr_group)

        layout.addStretch()
        self.setWidget(container)

        # Wire buttons
        self.btn_fetch.clicked.connect(self._run_fetch)
        self.btn_dem.clicked.connect(self._run_dem)
        self.btn_viewshed.clicked.connect(self._run_viewshed)
        self.btn_directional.clicked.connect(self._run_directional)
        self.btn_enrich.clicked.connect(self._run_enrich)
        self.btn_run_all.clicked.connect(self._run_all)
        self.btn_snr.clicked.connect(self._run_snr_heatmap)

        self._bbox = None  # (west, south, east, north) in WGS84

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _work_dir(self):
        """Return the QGIS project home directory as the working root.

        Outputs (data/, viewsheds/) are written here, so they stay
        alongside the .qgz file and survive plugin reinstalls.
        """
        path = QgsProject.instance().homePath()
        if not path:
            self.log_msg(
                "[Error] No QGIS project is open. "
                "Save your project first — outputs will be written next to the .qgz file."
            )
            return None
        return path

    def _get_api_key(self):
        key = self.api_key_edit.text().strip()
        if key:
            QgsSettings().setValue(self._SETTINGS_KEY, key)
        return key

    def log_msg(self, msg):
        self.log.append(msg)

    def _set_bbox_from_canvas(self):
        from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform
        canvas = self.iface.mapCanvas()
        extent = canvas.extent()
        src_crs = canvas.mapSettings().destinationCrs()
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        xform = QgsCoordinateTransform(src_crs, wgs84, QgsProject.instance())
        rect = xform.transformBoundingBox(extent)
        self._bbox = (rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum())
        self.bbox_label.setText(
            f"W:{self._bbox[0]:.3f} S:{self._bbox[1]:.3f} "
            f"E:{self._bbox[2]:.3f} N:{self._bbox[3]:.3f}"
        )
        self.bbox_label.setStyleSheet("color: white; font-size: 10px;")
        self.log_msg(f"[Region] Canvas extent captured: {self._bbox}")

    def _add_basemap(self):
        """Add CartoDB Dark Matter basemap if the checkbox is checked.

        Skips silently if a layer with the same name already exists, so
        re-running the plugin never duplicates the basemap.  The layer is
        moved to the bottom of the layer tree so it sits behind all outputs.
        """
        if not self.chk_basemap.isChecked():
            return
        if QgsProject.instance().mapLayersByName(self._BASEMAP_NAME):
            return  # already present
        from qgis.core import QgsRasterLayer
        layer = QgsRasterLayer(self._BASEMAP_URL, self._BASEMAP_NAME, "wms")
        if not layer.isValid():
            self.log_msg("[Basemap] Failed to load CartoDB Dark layer.")
            return
        QgsProject.instance().addMapLayer(layer, False)  # False = don't add to tree yet
        root = QgsProject.instance().layerTreeRoot()
        root.insertLayer(-1, layer)  # -1 = bottom of stack
        self.log_msg("[Basemap] CartoDB Dark added.")

    def _set_buttons_enabled(self, enabled):
        for btn in (self.btn_fetch, self.btn_dem, self.btn_viewshed,
                    self.btn_directional, self.btn_enrich, self.btn_run_all,
                    self.btn_snr):
            btn.setEnabled(enabled)

    def _on_task_started(self, label):
        self._set_buttons_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.log_msg(f"[Start] {label}")

    def _on_task_progress(self, pct):
        self.progress_bar.setValue(int(pct))

    def _on_task_done(self, label, success, message=""):
        self._set_buttons_enabled(True)
        self.progress_bar.setVisible(False)
        if success:
            self.log_msg(f"[Done] {label}")
        else:
            self.log_msg(f"[Error] {label}: {message}")

    # ------------------------------------------------------------------
    # Task launchers
    # ------------------------------------------------------------------

    def _run_fetch(self):
        work_dir = self._work_dir()
        if not work_dir:
            return
        self._add_basemap()
        from .tasks.fetch_task import FetchTask
        self._on_task_started("Fetch Nodes")
        task = FetchTask(work_dir, self.log_msg)
        task.taskCompleted.connect(lambda: self._on_task_done("Fetch Nodes", True))
        task.taskTerminated.connect(lambda t=task: self._on_task_done("Fetch Nodes", False, t.error or "task terminated"))
        QgsApplication.taskManager().addTask(task)

    def _run_dem(self):
        if not self._bbox:
            self.log_msg("[Error] Set canvas extent first.")
            return
        api_key = self._get_api_key()
        if not api_key:
            self.log_msg("[Error] OpenTopography API key required.")
            return
        work_dir = self._work_dir()
        if not work_dir:
            return
        from .tasks.dem_task import DemTask
        self._on_task_started("Download DEM")
        task = DemTask(work_dir, self._bbox, api_key, self.log_msg)
        task.taskCompleted.connect(lambda: self._on_task_done("Download DEM", True))
        task.taskTerminated.connect(lambda t=task: self._on_task_done("Download DEM", False, t.error or "task terminated"))
        QgsApplication.taskManager().addTask(task)

    def _run_viewshed(self):
        work_dir = self._work_dir()
        if not work_dir:
            return
        from .tasks.viewshed_task import ViewshedTask
        self._on_task_started("Run Viewshed")
        task = ViewshedTask(work_dir, self.log_msg)
        task.progressChanged.connect(self._on_task_progress)
        task.taskCompleted.connect(lambda: self._on_task_done("Run Viewshed", True))
        task.taskTerminated.connect(lambda t=task: self._on_task_done("Run Viewshed", False, t.error or "task terminated"))
        QgsApplication.taskManager().addTask(task)

    def _run_directional(self):
        work_dir = self._work_dir()
        if not work_dir:
            return
        from .tasks.directional_task import DirectionalTask
        self._on_task_started("Directional Raster")
        task = DirectionalTask(work_dir, self.log_msg)
        task.taskCompleted.connect(lambda: self._on_task_done("Directional Raster", True))
        task.taskTerminated.connect(lambda t=task: self._on_task_done("Directional Raster", False, t.error or "task terminated"))
        QgsApplication.taskManager().addTask(task)

    def _run_enrich(self):
        work_dir = self._work_dir()
        if not work_dir:
            return
        from .tasks.enrich_task import EnrichTask
        self._on_task_started("Enrich Nodes")
        task = EnrichTask(work_dir, self.log_msg)
        task.taskCompleted.connect(lambda: self._on_task_done("Enrich Nodes", True))
        task.taskTerminated.connect(lambda t=task: self._on_task_done("Enrich Nodes", False, t.error or "task terminated"))
        QgsApplication.taskManager().addTask(task)

    def _run_snr_heatmap(self):
        packets_path = self.packets_path_edit.text().strip()
        if not packets_path:
            self.log_msg("[Error] Set the packets file path first.")
            return
        QgsSettings().setValue(self._PACKETS_PATH_KEY, packets_path)
        work_dir = self._work_dir()
        if not work_dir:
            return
        from .tasks.snr_heatmap_task import SnrHeatmapTask
        self._on_task_started("SNR Heatmap")
        task = SnrHeatmapTask(work_dir, packets_path, self.log_msg)
        task.taskCompleted.connect(lambda: self._on_task_done("SNR Heatmap", True))
        task.taskTerminated.connect(
            lambda t=task: self._on_task_done("SNR Heatmap", False, t.error or "task terminated")
        )
        QgsApplication.taskManager().addTask(task)

    def _run_all(self):
        if not self._bbox:
            self.log_msg("[Error] Set canvas extent first.")
            return
        api_key = self._get_api_key()
        if not api_key:
            self.log_msg("[Error] OpenTopography API key required.")
            return
        work_dir = self._work_dir()
        if not work_dir:
            return

        from .tasks.fetch_task import FetchTask
        from .tasks.dem_task import DemTask
        from .tasks.viewshed_task import ViewshedTask
        from .tasks.directional_task import DirectionalTask
        from .tasks.enrich_task import EnrichTask

        self._set_buttons_enabled(False)
        self.progress_bar.setVisible(True)

        fetch = FetchTask(work_dir, self.log_msg)
        dem = DemTask(work_dir, self._bbox, api_key, self.log_msg)
        vs = ViewshedTask(work_dir, self.log_msg)
        vs.progressChanged.connect(self._on_task_progress)
        direc = DirectionalTask(work_dir, self.log_msg)
        enrich = EnrichTask(work_dir, self.log_msg)

        # Chain: each task triggers next on success
        fetch.taskCompleted.connect(lambda: QgsApplication.taskManager().addTask(dem))
        dem.taskCompleted.connect(lambda: QgsApplication.taskManager().addTask(vs))
        vs.taskCompleted.connect(lambda: QgsApplication.taskManager().addTask(direc))
        direc.taskCompleted.connect(lambda: QgsApplication.taskManager().addTask(enrich))
        enrich.taskCompleted.connect(lambda: self._on_task_done("Run All", True))

        for t, label in [(fetch, "Fetch"), (dem, "DEM"), (vs, "Viewshed"),
                         (direc, "Directional"), (enrich, "Enrich")]:
            t.taskTerminated.connect(
                lambda lbl=label: self._on_task_done("Run All", False, f"{lbl} failed")
            )

        self.log_msg("[Run All] Starting pipeline...")
        QgsApplication.taskManager().addTask(fetch)
