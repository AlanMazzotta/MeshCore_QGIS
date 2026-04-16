"""
Creates a DEM extent highlight rectangle as a memory layer with a pale grey
outer glow effect. Paste into the QGIS Python Console and run.

Place the resulting layer above CartoDB Dark and below Base DEM Gray Elv.
"""

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsRectangle, QgsField, QgsSingleSymbolRenderer,
    QgsFillSymbol, QgsSimpleFillSymbolLayer,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor

# DEM extent (EPSG:4326)
WEST, EAST, SOUTH, NORTH = -123.9176, -121.5957, 44.9201, 46.0257

# Create memory layer
layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "DEM Extent Highlight", "memory")
pr = layer.dataProvider()
pr.addAttributes([QgsField("id", QVariant.Int)])
layer.updateFields()

# Add rectangle feature
feat = QgsFeature()
feat.setGeometry(QgsGeometry.fromRect(QgsRectangle(WEST, SOUTH, EAST, NORTH)))
feat.setAttributes([1])
pr.addFeature(feat)
layer.updateExtents()

# --- Symbology: no fill, pale grey outer glow via buffer effect ---
symbol = QgsFillSymbol.createSimple({
    'color': '0,0,0,0',           # fully transparent fill
    'outline_style': 'no',        # no hard border
})

# Add draw effects — outer glow
from qgis.core import (
    QgsEffectStack, QgsOuterGlowEffect, QgsDrawSourceEffect,
)

effect_stack = QgsEffectStack()

# Draw source (the transparent rectangle itself)
source = QgsDrawSourceEffect()
source.setEnabled(True)
effect_stack.appendEffect(source)

# Outer glow
glow = QgsOuterGlowEffect()
glow.setEnabled(True)
glow.setSpread(8.0)          # glow width in mm — adjust to taste
glow.setSpreadUnit(QgsUnitTypes.RenderMillimeters)
glow.setBlurLevel(8)
glow.setOpacity(0.55)        # 0.0–1.0
glow.setColor(QColor(200, 200, 210, 255))  # pale blue-grey
effect_stack.appendEffect(glow)

symbol.symbolLayer(0).setPaintEffect(effect_stack)
layer.setRenderer(QgsSingleSymbolRenderer(symbol))

# Add to project
QgsProject.instance().addMapLayer(layer)
print("DEM Extent Highlight layer added. Move it above CartoDB Dark in the layer panel.")
