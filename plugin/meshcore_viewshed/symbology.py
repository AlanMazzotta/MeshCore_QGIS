"""
Auto-symbology applied when layers are loaded by the plugin.

Coverage raster  — 4-class discrete log-scale ramp, breaks derived from
                   actual pixel distribution so any dataset is interpretable.
DEM              — Interpolated terrain ramp, labeled in meters.
Enriched nodes   — 5-class rule-based renderer matching Test_1_ASM.
SNR heatmap      — Continuous Inferno ramp, dynamic range from raster stats.
"""

from qgis.PyQt.QtGui import QColor, QFont


# ---------------------------------------------------------------------------
# Coverage raster (cumulative_viewshed.tif)
# ---------------------------------------------------------------------------

def apply_coverage_symbology(layer) -> None:
    """
    4-class discrete ramp with log-scale breaks derived from the actual pixel
    distribution.  Log-scale handles the typical power-law falloff in
    cumulative viewshed outputs — most pixels see few nodes, a dense core
    sees many — keeping all four classes visually meaningful regardless of
    the specific network or extent.
    """
    import numpy as np
    from osgeo import gdal
    from qgis.core import (
        QgsSingleBandPseudoColorRenderer,
        QgsColorRampShader,
        QgsRasterShader,
    )

    # --- read pixel data and compute log-scale class breaks ---
    ds = gdal.Open(layer.source())
    band = ds.GetRasterBand(1)
    nodata = band.GetNoDataValue()
    arr = band.ReadAsArray().astype(float)
    ds = None

    if nodata is not None:
        arr[arr == nodata] = np.nan
    arr[arr == 0] = np.nan
    valid = arr[~np.isnan(arr)]

    if len(valid) == 0:
        return

    log_vals = np.log1p(valid)
    raw_breaks = np.expm1(np.percentile(log_vals, [0, 25, 50, 75, 100])).astype(int)
    breaks = list(dict.fromkeys(raw_breaks))  # deduplicate while preserving order

    # --- amber-to-rust palette (pale → dense) ---
    _COLORS = [
        QColor(255, 247, 188, 200),  # pale yellow  — fringe
        QColor(254, 196,  79, 220),  # amber        — low redundancy
        QColor(217,  95,  14, 235),  # burnt orange — moderate
        QColor(153,  52,   4, 255),  # deep rust    — dense core
    ]

    items = [QgsColorRampShader.ColorRampItem(0, QColor(0, 0, 0, 0), "No coverage")]
    n = len(breaks) - 1
    for i in range(n):
        lo, hi = int(breaks[i]), int(breaks[i + 1])
        label = f"{lo}+ nodes visible" if i == n - 1 else f"{lo}–{hi} nodes visible"
        items.append(QgsColorRampShader.ColorRampItem(hi, _COLORS[min(i, 3)], label))

    fcn = QgsColorRampShader()
    fcn.setColorRampType(QgsColorRampShader.Discrete)
    fcn.setColorRampItemList(items)

    shader = QgsRasterShader()
    shader.setRasterShaderFunction(fcn)

    renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
    layer.setRenderer(renderer)
    layer.setOpacity(0.6)
    layer.triggerRepaint()
    layer.emitStyleChanged()


# ---------------------------------------------------------------------------
# DEM (dem.tif)
# ---------------------------------------------------------------------------

def apply_dem_symbology(layer) -> None:
    """
    Interpolated terrain ramp from actual min to max elevation, labeled in
    metres.  Five stops from lowland green through alpine white give users
    immediate terrain context without any manual configuration.
    """
    try:
        from qgis.core import (
            QgsSingleBandPseudoColorRenderer,
            QgsColorRampShader,
            QgsRasterShader,
            QgsRasterBandStats,
            QgsMessageLog,
            Qgis,
        )

        provider = layer.dataProvider()
        # QgsRasterBandStats.All is safe across all QGIS 3.x versions
        stats = provider.bandStatistics(1, QgsRasterBandStats.All)
        lo = int(stats.minimumValue)
        hi = int(stats.maximumValue)
        span = hi - lo or 1  # guard against flat rasters
        QgsMessageLog.logMessage(
            f"[DEM symbology] min={lo} max={hi}", "MeshCore", Qgis.Info
        )

        # lowland green → mid yellow-brown → alpine white
        items = [
            QgsColorRampShader.ColorRampItem(lo,               QColor( 70, 150,  70), f"{lo} m"),
            QgsColorRampShader.ColorRampItem(lo + span * 0.25, QColor(140, 190,  80), ""),
            QgsColorRampShader.ColorRampItem(lo + span * 0.50, QColor(210, 185, 120), ""),
            QgsColorRampShader.ColorRampItem(lo + span * 0.75, QColor(180, 130,  80), ""),
            QgsColorRampShader.ColorRampItem(hi,               QColor(240, 240, 240), f"{hi} m"),
        ]

        fcn = QgsColorRampShader(lo, hi)
        fcn.setColorRampType(QgsColorRampShader.Interpolated)
        fcn.setColorRampItemList(items)

        shader = QgsRasterShader(lo, hi)
        shader.setRasterShaderFunction(fcn)

        renderer = QgsSingleBandPseudoColorRenderer(provider, 1, shader)
        renderer.setClassificationMin(lo)
        renderer.setClassificationMax(hi)
        layer.setRenderer(renderer)
        layer.setOpacity(0.7)
        layer.triggerRepaint()
        layer.emitStyleChanged()

    except Exception as e:
        from qgis.core import QgsMessageLog, Qgis
        QgsMessageLog.logMessage(
            f"[DEM symbology] Failed: {e}", "MeshCore", Qgis.Warning
        )


# ---------------------------------------------------------------------------
# Directional raster (directional_viewshed.tif)
# ---------------------------------------------------------------------------

def apply_directional_symbology(layer) -> None:
    """
    Paletted renderer for the 8-sector directional viewshed.  Only classes
    1–8 are registered, so the QGIS legend shows nothing beyond NW — the
    raster is a uint8 with a 256-entry palette table baked in by GDAL, and
    without an explicit class list QGIS would display all 256 entries.
    Colors mirror the sector palette defined in viewshed_directional.py.
    """
    from qgis.core import QgsPalettedRasterRenderer

    _SECTORS = [
        (1, ( 30, 100, 200), "N"),
        (2, (  0, 180, 180), "NE"),
        (3, ( 50, 180,  50), "E"),
        (4, (180, 220,   0), "SE"),
        (5, (220, 130,   0), "S"),
        (6, (220,  50,   0), "SW"),
        (7, (160,   0, 200), "W"),
        (8, ( 80,  30, 180), "NW"),
    ]

    classes = [
        QgsPalettedRasterRenderer.Class(val, QColor(r, g, b), label)
        for val, (r, g, b), label in _SECTORS
    ]

    renderer = QgsPalettedRasterRenderer(layer.dataProvider(), 1, classes)
    layer.setRenderer(renderer)
    layer.setOpacity(0.5)
    layer.triggerRepaint()
    layer.emitStyleChanged()


# ---------------------------------------------------------------------------
# Enriched nodes (meshcore_nodes_plus.geojson) — Test_1_ASM 5-class style
# ---------------------------------------------------------------------------

# (filter_expr, label, (R, G, B), size_mm, stroke_width_mm)
# Peer count threshold = 3: a node with 3+ peers has genuine redundant routing
# paths, which is the fundamental mesh property. Nodes with 0-2 peers are
# effectively leaf nodes or spurs regardless of their coverage reach.
_NODE_RULES = [
    ('"coverage_km2" >= 100 AND "peer_count" < 3',  "Critical", (215,  25,  28), 10.5, 0.4),
    ('"coverage_km2" >= 100 AND "peer_count" >= 3', "Backbone", ( 44, 123, 182), 10.5, 0.4),
    ('"coverage_km2" < 100  AND "peer_count" >= 3', "Redundant",(26,  150,  65), 10.5, 0.4),
    ('"coverage_km2" < 100  AND "peer_count" < 3',  "Marginal", (136, 136, 136),  9.0, 0.3),
    ('"coverage_km2" = 0',                          "No TIF",   (204, 204, 204),  7.5, 0.2),
]


def apply_nodes_plus_symbology(layer) -> None:
    """5-class rule-based renderer — coverage × peer_count quadrant."""
    import os
    from qgis.core import (
        QgsRuleBasedRenderer,
        QgsSymbol,
        QgsSimpleMarkerSymbolLayer,
        QgsSvgMarkerSymbolLayer,
        QgsUnitTypes,
        QgsProperty,
        QgsSymbolLayer,
    )

    _svg_path = os.path.join(os.path.dirname(__file__), "icons", "antenna.svg")

    root_rule = QgsRuleBasedRenderer.Rule(None)

    reach_expr = (
        'CASE WHEN "coverage_km2" > 0 '
        'THEN 2 * sqrt("coverage_km2" / pi()) * 1000 '
        'ELSE 2000 END'
    )

    for expr, label, (r, g, b), size, stroke in _NODE_RULES:
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        symbol.deleteSymbolLayer(0)

        # Layer 0: reach circle (drawn first = behind the dot)
        circle = QgsSimpleMarkerSymbolLayer()
        circle.setColor(QColor(r, g, b, 77))             # 30% opacity fill
        circle.setStrokeColor(QColor(153, 153, 153, 128)) # 60% grey, 50% opacity
        circle.setStrokeWidth(0.4)
        circle.setShape(QgsSimpleMarkerSymbolLayer.Circle)
        circle.setSize(1)
        circle.setSizeUnit(QgsUnitTypes.RenderMetersInMapUnits)
        circle.setDataDefinedProperty(
            QgsSymbolLayer.PropertySize,
            QgsProperty.fromExpression(reach_expr),
        )
        symbol.appendSymbolLayer(circle)

        # Layer 1: antenna SVG on top (full opacity, independent of circle)
        svg = QgsSvgMarkerSymbolLayer(_svg_path)
        svg.setSize(size)
        svg.setSizeUnit(QgsUnitTypes.RenderMillimeters)
        svg.setFillColor(QColor(r, g, b, 255))
        svg.setStrokeColor(QColor(255, 255, 255, 255))
        svg.setStrokeWidth(0.8)
        symbol.appendSymbolLayer(svg)

        rule = QgsRuleBasedRenderer.Rule(symbol)
        rule.setFilterExpression(expr)
        rule.setLabel(label)
        root_rule.appendChild(rule)

    layer.setRenderer(QgsRuleBasedRenderer(root_rule))
    _apply_nodes_plus_labels(layer)
    layer.triggerRepaint()


# ---------------------------------------------------------------------------
# SNR heatmap (meshcore_snr_heatmap.tif)
# ---------------------------------------------------------------------------

def apply_snr_heatmap_symbology(layer) -> None:
    """
    Continuous Inferno ramp from actual data min to max.  The two endpoints
    are labelled with quality tier and dB value so the legend is readable
    without needing to interpret raw numbers.  Dynamic range is derived from
    raster stats so any observation window renders meaningfully.
    """
    try:
        from qgis.core import (
            QgsSingleBandPseudoColorRenderer,
            QgsColorRampShader,
            QgsRasterShader,
            QgsRasterBandStats,
            QgsMessageLog,
            Qgis,
        )

        provider = layer.dataProvider()
        stats = provider.bandStatistics(1, QgsRasterBandStats.All)
        lo = stats.minimumValue
        hi = stats.maximumValue
        span = hi - lo or 1.0

        def _quality(db):
            if db >= 10:  return "Excellent"
            if db >= 5:   return "Good"
            if db >= 0:   return "Marginal"
            return "Weak"

        lo_label = f"{_quality(lo)}  ({lo:.1f} dB)"
        hi_label = f"{_quality(hi)}  ({hi:.1f} dB)"

        # Inferno palette: dark purple (weak) → orange → bright yellow (strong)
        items = [
            QgsColorRampShader.ColorRampItem(lo,               QColor( 20,  11,  52), lo_label),
            QgsColorRampShader.ColorRampItem(lo + span * 0.25, QColor(132,  32, 107), ""),
            QgsColorRampShader.ColorRampItem(lo + span * 0.50, QColor(229,  92,  48), ""),
            QgsColorRampShader.ColorRampItem(lo + span * 0.75, QColor(253, 187,  48), ""),
            QgsColorRampShader.ColorRampItem(hi,               QColor(252, 255, 164), hi_label),
        ]

        fcn = QgsColorRampShader(lo, hi)
        fcn.setColorRampType(QgsColorRampShader.Interpolated)
        fcn.setColorRampItemList(items)

        shader = QgsRasterShader(lo, hi)
        shader.setRasterShaderFunction(fcn)

        renderer = QgsSingleBandPseudoColorRenderer(provider, 1, shader)
        renderer.setClassificationMin(lo)
        renderer.setClassificationMax(hi)
        layer.setRenderer(renderer)
        layer.setOpacity(0.6)
        layer.setName(f"Signal Quality  |  {lo_label} → {hi_label}")
        layer.triggerRepaint()
        layer.emitStyleChanged()

    except Exception as e:
        from qgis.core import QgsMessageLog, Qgis
        QgsMessageLog.logMessage(
            f"[SNR symbology] Failed: {e}", "MeshCore", Qgis.Warning
        )


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
