import os
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon

PLUGIN_DIR = os.path.dirname(__file__)


class MeshCoreViewshedPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.dock = None
        self.action = None

    def initGui(self):
        from .dock_widget import MeshCoreViewshedDock
        from .deps import check_dependencies

        icon_path = os.path.join(PLUGIN_DIR, "icon.png")
        self.action = QAction(QIcon(icon_path), "MeshCore Viewshed", self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.triggered.connect(self._toggle_dock)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("MeshCore Viewshed", self.action)

        self.dock = MeshCoreViewshedDock(self.iface, self.iface.mainWindow())
        self.iface.addDockWidget(self.dock.default_area, self.dock)
        self.dock.visibilityChanged.connect(self.action.setChecked)

        check_dependencies(self.iface)

    def unload(self):
        self.iface.removeToolBarIcon(self.action)
        self.iface.removePluginMenu("MeshCore Viewshed", self.action)
        if self.dock:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None

    def _toggle_dock(self, checked):
        if self.dock:
            self.dock.setVisible(checked)
