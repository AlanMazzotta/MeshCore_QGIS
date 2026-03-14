# GIS in Action 2026 — Map Gallery Submission

**Category:** Analytic
**Title:** Terrain-Aware Coverage Modeling for LoRa Mesh Networks: A QGIS Plugin Approach

---

## Abstract

LoRa (Long Range) radio mesh networks are gaining traction for off-grid and emergency communications. Community-operated networks such as MeshCore and Meshtastic rely on elevated repeater nodes to relay messages across terrain — but knowing *where* a repeater is located tells you nothing about *where its signal actually reaches*. Propagation is shaped by ridgelines, buildings, and valley topography that flat node maps completely ignore.

This project presents a five-step QGIS plugin that bridges live network topology data with terrain-aware viewshed analysis to produce quantified, per-node coverage metrics for the Portland, Oregon MeshCore repeater network.

The workflow begins by fetching repeater locations from the public MeshCore API in real time. A Copernicus GLO-30 digital elevation model (30 m resolution) is then downloaded for the area of interest. GDAL's `gdal_viewshed` algorithm computes a geometric line-of-sight viewshed for each repeater, which are stacked into a cumulative coverage raster showing how many nodes can "see" any given point. A directional raster classifies every visible pixel by the compass bearing from its nearest repeater, revealing dominant propagation corridors. Finally, all rasters are sampled back to the node layer, enriching each repeater with eight analytic attributes: visible area (km²), pixel reach count, dominant compass sector, line-of-sight peer count, and Free Space Path Loss statistics (average, minimum, and maximum dB) to all visible neighbors.

Applied to the Portland network, this analysis revealed significant coverage asymmetry — nodes on the West Hills extend 12–18 km² southeast toward the valley floor, while nodes on the east side show sub-2 km² reach constrained by the Cascades foothills. Network planners can use these outputs to identify underserved gaps, prioritize repeater placement, and evaluate link budgets before any hardware is deployed.

All outputs are produced as standard QGIS vector and raster layers with auto-applied symbology, making the analysis accessible without command-line expertise.

**Data sources:** MeshCore public API (map.meshcore.dev), Copernicus GLO-30 DEM via OpenTopography
**Tools:** QGIS 3.16+, GDAL, Python (NumPy)
**License:** MIT — https://github.com/alanmazzotta/MeshCore_QGIS

---

*Word count: ~270*
