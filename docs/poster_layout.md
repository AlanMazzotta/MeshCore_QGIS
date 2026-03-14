# Poster Layout — GIS in Action 2026

**Format:** Landscape, JPG, ≤10 MB, ≤4 ft × 6 ft
**Title:** Terrain-Aware Coverage Modeling for LoRa Mesh Networks

---

## Layout Grid (landscape, 3 columns × 2 rows + header)

```
┌─────────────────────────────────────────────────────────────────────┐
│  HEADER: Title + Author + Conference tag                            │
├─────────────────┬─────────────────────────┬─────────────────────────┤
│  COL 1 (left)   │  COL 2 (center)         │  COL 3 (right)          │
│  Context        │  THE MAP                │  The Numbers            │
│  (rows 1+2)     │  (large, rows 1+2)      │  (rows 1+2)             │
├─────────────────┴─────────────────────────┴─────────────────────────┤
│  FOOTER: QR codes + data sources + license                          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Section-by-Section Copy

### HEADER
**Title:** Terrain-Aware Coverage Modeling for LoRa Mesh Networks
**Subtitle:** A QGIS Plugin for Quantified Repeater Analysis
**Author:** Alan Mazzotta | GIS in Action 2026 | Analytic Category

---

### COL 1 — Context (stacked vertically)

#### 1A. You've heard of Meshtastic...
*[Small icon: radio wave / node diagram]*

LoRa (Long Range) radios form low-power, off-grid mesh networks — no cell towers, no internet required. Hobbyists, hikers, and emergency responders are deploying them in cities nationwide.

**MeshCore** is an open-source alternative firmware focused on infrastructure-grade repeater nodes. Portland's network is live at **pdx.meshmapper.net** — you can watch packets route in real time.

But a node map answers only one question: *"Where are the radios?"*

---

#### 1B. The Problem
*[Simple before/after diagram: flat node dot-map vs. terrain-shaded viewshed]*

Radio propagation is governed by **terrain**. A repeater on a hilltop may cover 15 km² of valley floor. The same radio in a hollow may reach nothing beyond a few city blocks.

Without terrain-aware analysis, network planners are guessing.

---

#### 1C. The Plugin — 5-Step Pipeline
*[Flowchart: icons + arrows]*

① **Fetch Nodes** — Live repeater locations from MeshCore API
② **Download DEM** — Copernicus GLO-30 (30 m) via OpenTopography
③ **Run Viewshed** — GDAL line-of-sight per repeater → cumulative raster
④ **Directional Raster** — Classify visible pixels by compass bearing
⑤ **Enrich Nodes** — Sample rasters → 8 analytic attributes per node

*Runs in QGIS 3.16+ — no command line required.*

---

### COL 2 — The Map (LARGE, dominant visual)

**Main visual:** Full-extent viewshed output for Portland area
- Background: hillshade DEM
- Cumulative viewshed raster (semi-transparent, color-ramped: 0 peers = transparent → 5+ peers = deep blue)
- Directional raster overlay (8-color sector palette)
- Repeater node points with proportional reach circles
- Inset: pdx.meshmapper.net screenshot (live topology for comparison)

**Caption:**
> Cumulative viewshed coverage for the Portland MeshCore repeater network. Color shows how many nodes have line-of-sight to each point; sector hue shows the dominant bearing from the nearest repeater. Node circles are scaled to individual viewshed area (km²).

---

### COL 3 — The Numbers

#### 3A. Per-Node Stats Table
*[Table: top 5–8 nodes by coverage_km2, with columns: Name | Coverage km² | Peer Count | LoS Peers | Dominant Dir | Avg FSPL (dB)]*

*(Fill in with real Portland run results)*

---

#### 3B. Network Summary
*[2–3 callout boxes / stat cards]*

- **[X] repeater nodes** analyzed
- **[Y] km²** total visible area (union)
- **[Z]** nodes with zero LoS peers (isolated)
- Dominant network sector: **[DIR]**

---

#### 3C. FSPL Explainer
*[Small diagram: two nodes, distance arrow, dB label]*

**Free Space Path Loss (FSPL)** is the signal attenuation between two nodes assuming unobstructed line-of-sight:

> FSPL (dB) = 32.45 + 20·log₁₀(MHz) + 20·log₁₀(km)

At 910 MHz (US LoRa band):
- **1 km** → ~91.6 dB loss
- **5 km** → ~105.6 dB loss
- **10 km** → ~111.6 dB loss

Lower is better. A typical LoRa link budget is ~150 dB — anything below that is a viable link.

---

#### 3D. West Hills vs. East Side
*[Small comparison bar chart or split map]*

West Hills nodes avg **~14 km²** coverage — commanding views down to the valley floor.
East-side nodes avg **~2.5 km²** — constrained by the Cascades foothills.

This asymmetry explains why packets crossing the metro area require multi-hop routing through the hilltop nodes.

---

### FOOTER

| QR: GitHub Plugin | QR: pdx.meshmapper.net | Data Sources |
|---|---|---|
| *[QR code]* | *[QR code]* | DEM: Copernicus GLO-30 via OpenTopography |
| github.com/alanmazzotta/MeshCore_QGIS | pdx.meshmapper.net | Nodes: map.meshcore.dev API |
| MIT License | Live Portland Network Map | Analysis: GDAL viewshed, NumPy |

---

## Design Notes

- **Color palette:** Dark basemap (Carto Dark or QGIS hillshade) with the 8-sector directional palette as the dominant visual color story
- **Font:** Clean sans-serif (Montserrat or similar); header bold, body regular
- **Callout boxes:** Use rounded rectangles with subtle fill matching sector colors
- **Node circles:** SVG antenna marker (already in plugin) — scale by `coverage_km2`
- **Fill in placeholder stats** after running the plugin on the current Portland network data before final export
