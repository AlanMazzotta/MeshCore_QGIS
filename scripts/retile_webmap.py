"""
Retile webmap rasters from current QGIS project.

Paste into the QGIS Python Console (Plugins > Python Console > Show Editor).
Run with the Test_4 project open. Both viewshed layers must be loaded.

Outputs:
  docs/webmap/tiles/coverage/   -- cumulative viewshed, zoom 9-14
  docs/webmap/tiles/direction/  -- directional viewshed, zoom 9-14
"""

import os
import shutil
from qgis.core import QgsProject
from qgis.PyQt.QtGui import QColor
import processing

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TILES_BASE = r'C:\Users\alanm\Desktop\Code\MeshCore_QGIS\docs\webmap\tiles'
ZOOM_MIN   = 9
ZOOM_MAX   = 14

# ---------------------------------------------------------------------------
# Find layers by name fragment
# ---------------------------------------------------------------------------

def find_layer(fragment):
    for lyr in QgsProject.instance().mapLayers().values():
        if fragment.lower() in lyr.name().lower():
            return lyr
    return None

coverage_lyr  = find_layer('MeshCore Coverage')
direction_lyr = find_layer('MeshCore Direction')

if not coverage_lyr:
    raise RuntimeError("Could not find cumulative viewshed layer — is it loaded?")
if not direction_lyr:
    raise RuntimeError("Could not find directional viewshed layer — is it loaded?")

print(f"Coverage  : {coverage_lyr.name()}")
print(f"Direction : {direction_lyr.name()}")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

root = QgsProject.instance().layerTreeRoot()

def set_visibility(layer_ids_on):
    """Show only the layers in layer_ids_on; hide everything else."""
    for lyr in QgsProject.instance().mapLayers().values():
        node = root.findLayer(lyr.id())
        if node:
            node.setItemVisibilityChecked(lyr.id() in layer_ids_on)

def extent_str(lyr):
    e = lyr.extent()
    return f'{e.xMinimum()},{e.xMaximum()},{e.yMinimum()},{e.yMaximum()} [EPSG:4326]'

def run_tiles(lyr, out_dir):
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    set_visibility({lyr.id()})
    processing.run("native:tilesxyzdirectory", {
        'EXTENT'          : extent_str(lyr),
        'ZOOM_MIN'        : ZOOM_MIN,
        'ZOOM_MAX'        : ZOOM_MAX,
        'DPI'             : 96,
        'BACKGROUND_COLOR': QColor(0, 0, 0, 0),
        'TILE_FORMAT'     : 0,   # PNG
        'METATILESIZE'    : 4,
        'OUTPUT_DIRECTORY': out_dir,
        'OUTPUT_HTML'     : 'TEMPORARY_OUTPUT',
    })

# ---------------------------------------------------------------------------
# Tile both layers
# ---------------------------------------------------------------------------

# Remember which layers were originally visible
originally_visible = {
    lyr.id()
    for lyr in QgsProject.instance().mapLayers().values()
    if (node := root.findLayer(lyr.id())) and node.isVisible()
}

try:
    print("Tiling coverage …")
    run_tiles(coverage_lyr, os.path.join(TILES_BASE, 'coverage'))
    print("  done.")

    print("Tiling directional …")
    run_tiles(direction_lyr, os.path.join(TILES_BASE, 'direction'))
    print("  done.")

finally:
    # Restore original visibility regardless of errors
    set_visibility(originally_visible)

print("\nAll tiles written. Check docs/webmap/tiles/ then commit + push.")
