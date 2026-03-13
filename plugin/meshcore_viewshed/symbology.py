"""
Auto-symbology applied when layers are loaded by the plugin.

Coverage raster  — SinglebandPseudocolor, amber heat ramp, 50% opacity.
Enriched nodes   — 5-class rule-based renderer matching Test_1_ASM.
"""

from qgis.PyQt.QtGui import QColor, QFont


# ---------------------------------------------------------------------------
# Coverage raster (cumulative_viewshed.tif)
# ---------------------------------------------------------------------------

def apply_coverage_symbology(layer) -> None:
    """Amber heat ramp: transparent at 0, cream → burnt-orange at max."""
    from qgis.core import (
        QgsSingleBandPseudoColorRenderer,
        QgsColorRampShader,
        QgsRasterShader,
        QgsRasterBandStats,
    )

    provider = layer.dataProvider()
    stats = provider.bandStatistics(1, QgsRasterBandStats.Max, layer.extent(), 0)
    max_val = max(int(stats.maximumValue), 2)

    fcn = QgsColorRampShader()
    fcn.setColorRampType(QgsColorRampShader.Interpolated)
    fcn.setClassificationMode(QgsColorRampShader.Continuous)
    fcn.setColorRampItemList([
        QgsColorRampShader.ColorRampItem(0,       QColor(0,   0,   0,   0),   "No coverage"),
        QgsColorRampShader.ColorRampItem(1,       QColor(255, 247, 188, 200), "1 node"),
        QgsColorRampShader.ColorRampItem(max_val, QColor(217,  95,  14, 255), f"{max_val} nodes"),
    ])

    shader = QgsRasterShader()
    shader.setRasterShaderFunction(fcn)

    renderer = QgsSingleBandPseudoColorRenderer(provider, 1, shader)
    layer.setRenderer(renderer)
    layer.setOpacity(0.5)
    layer.triggerRepaint()


# ---------------------------------------------------------------------------
# Enriched nodes (meshcore_nodes_plus.geojson) — Test_1_ASM 5-class style
# ---------------------------------------------------------------------------

# (filter_expr, label, (R, G, B), size_mm, stroke_width_mm)
_NODE_RULES = [
    ('"coverage_km2" >= 100 AND "peer_count" < 5',  "Critical", (215,  25,  28), 6.0, 0.4),
    ('"coverage_km2" >= 100 AND "peer_count" >= 5', "Backbone", ( 44, 123, 182), 6.0, 0.4),
    ('"coverage_km2" < 100  AND "peer_count" >= 5', "Redundant",(26,  150,  65), 3.5, 0.4),
    ('"coverage_km2" < 100  AND "peer_count" < 5',  "Marginal", (136, 136, 136), 3.0, 0.3),
    ('"coverage_km2" = 0',                          "No TIF",   (204, 204, 204), 2.5, 0.2),
]


def apply_nodes_plus_symbology(layer) -> None:
    """5-class rule-based renderer — coverage × peer_count quadrant."""
    from qgis.core import (
        QgsRuleBasedRenderer,
        QgsSymbol,
        QgsSimpleMarkerSymbolLayer,
        QgsUnitTypes,
    )

    root_rule = QgsRuleBasedRenderer.Rule(None)

    for expr, label, (r, g, b), size, stroke in _NODE_RULES:
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        symbol.deleteSymbolLayer(0)

        marker = QgsSimpleMarkerSymbolLayer()
        marker.setColor(QColor(r, g, b, 255))
        marker.setStrokeColor(QColor(255, 255, 255, 255))
        marker.setStrokeWidth(stroke)
        marker.setShape(QgsSimpleMarkerSymbolLayer.Circle)
        marker.setSize(size)
        marker.setSizeUnit(QgsUnitTypes.RenderMillimeters)
        symbol.appendSymbolLayer(marker)

        rule = QgsRuleBasedRenderer.Rule(symbol)
        rule.setFilterExpression(expr)
        rule.setLabel(label)
        root_rule.appendChild(rule)

    layer.setRenderer(QgsRuleBasedRenderer(root_rule))
    _apply_nodes_plus_labels(layer)
    layer.triggerRepaint()


def _apply_nodes_plus_labels(layer) -> None:
    """Node name label, 7pt white text with thin black halo."""
    from qgis.core import (
        QgsPalLayerSettings,
        QgsVectorLayerSimpleLabeling,
        QgsTextFormat,
        QgsTextBufferSettings,
        QgsUnitTypes,
    )

    fmt = QgsTextFormat()
    fmt.setFont(QFont("Arial", 7))
    fmt.setSize(7)
    fmt.setSizeUnit(QgsUnitTypes.RenderPoints)
    fmt.setColor(QColor(255, 255, 255))

    buf = QgsTextBufferSettings()
    buf.setEnabled(True)
    buf.setSize(0.8)
    buf.setSizeUnit(QgsUnitTypes.RenderMillimeters)
    buf.setColor(QColor(0, 0, 0))
    fmt.setBuffer(buf)

    settings = QgsPalLayerSettings()
    settings.fieldName = "name"
    settings.enabled = True
    settings.setFormat(fmt)

    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)
