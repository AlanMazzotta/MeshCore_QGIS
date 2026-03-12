REQUIRED = ["msgpack", "requests", "geojson"]


def check_dependencies(iface):
    missing = []
    for pkg in REQUIRED:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if not missing:
        return

    from qgis.PyQt.QtWidgets import QPushButton
    from qgis.core import Qgis

    msg = f"MeshCore Viewshed: missing packages: {', '.join(missing)}"
    widget = iface.messageBar().createMessage("MeshCore Viewshed", f"Missing: {', '.join(missing)}")
    btn = QPushButton("Install")
    btn.pressed.connect(lambda: _install(missing, iface))
    widget.layout().addWidget(btn)
    iface.messageBar().pushWidget(widget, Qgis.Warning, duration=0)


def _install(packages, iface):
    import subprocess
    import sys
    from qgis.core import Qgis

    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + packages)
        iface.messageBar().pushMessage(
            "MeshCore Viewshed", "Dependencies installed. Please restart QGIS.",
            level=Qgis.Success, duration=10
        )
    except subprocess.CalledProcessError as e:
        iface.messageBar().pushMessage(
            "MeshCore Viewshed", f"Install failed: {e}",
            level=Qgis.Critical, duration=0
        )
