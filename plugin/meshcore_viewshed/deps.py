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


def _find_python():
    """Find the real Python executable (not qgis-bin.exe) in the QGIS environment."""
    import os
    import sys
    exe = sys.executable
    if os.path.basename(exe).lower().startswith("python"):
        return exe
    # QGIS on Windows: python lives in <qgis_root>/apps/PythonXXX/python.exe
    qgis_root = os.path.dirname(os.path.dirname(exe))
    apps_dir = os.path.join(qgis_root, "apps")
    if os.path.isdir(apps_dir):
        for entry in sorted(os.listdir(apps_dir), reverse=True):
            if entry.lower().startswith("python"):
                candidate = os.path.join(apps_dir, entry, "python.exe")
                if os.path.exists(candidate):
                    return candidate
    return "python"  # last resort


def _install(packages, iface):
    import subprocess
    from qgis.core import Qgis

    python = _find_python()
    try:
        subprocess.check_call([python, "-m", "pip", "install"] + packages)
        iface.messageBar().pushMessage(
            "MeshCore Viewshed", "Dependencies installed. Please restart QGIS.",
            level=Qgis.Success, duration=10
        )
    except subprocess.CalledProcessError as e:
        iface.messageBar().pushMessage(
            "MeshCore Viewshed", f"Install failed: {e}",
            level=Qgis.Critical, duration=0
        )
