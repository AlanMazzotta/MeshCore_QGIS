# Lightning Talk — GIS in Action 2026
**Title:** Terrain-Aware Coverage Modeling for LoRa Mesh Networks
**Time:** 3 minutes

---

## 0:00 — The Hook (30 sec)

> "Raise your hand if you've heard of Meshtastic."

Brief pause. Whatever the response:

> "LoRa mesh radios — long range, low power, no cell towers required. They're being used for emergency comms, hiking groups, and neighborhood networks. Portland has one running right now. You can see every repeater on a map. But here's the question nobody could answer: *where does it actually reach?*"

---

## 0:30 — The Problem (30 sec)

> "A node map tells you *where* repeaters are. It doesn't tell you *what they see*."

Point to the poster's node map section.

> "Radio signals don't care about straight-line distance. They care about terrain. That ridge, that building, that valley — those are your real coverage boundaries. And that's a GIS problem."

---

## 1:00 — The Solution (60 sec)

Point to the 5-step pipeline flowchart on the poster.

> "So I built a QGIS plugin. Five steps, all automated:"

Walk through quickly:
1. **Fetch** — pulls live repeater data from the MeshCore API
2. **DEM** — downloads a 30-meter elevation model from OpenTopography
3. **Viewshed** — GDAL line-of-sight analysis, one TIF per repeater, stacked into a cumulative coverage raster
4. **Directional** — classifies every visible pixel by compass bearing from its nearest repeater
5. **Enrich** — samples everything back to the nodes: coverage area, peer visibility, Free Space Path Loss

> "You click five buttons. You get a terrain-aware picture of your network."

---

## 2:00 — The Numbers (45 sec)

Point to the analytic deep-dive section of the poster.

> "Here's what we found in Portland."

Hit 2-3 specific findings (fill in with actual run results):
- "The West Hills nodes — [Node Name] and [Node Name] — cover 15+ km² down into the valley. They're doing the heavy lifting."
- "East-side nodes average under 3 km² because the Cascades foothills are right there."
- "Seven nodes have zero line-of-sight peers within their viewshed. They're isolated islands."

> "That's information you cannot get from a node map. That's the analysis."

---

## 2:45 — Call to Action (15 sec)

Point to QR codes on poster.

> "The plugin is free, MIT licensed, runs in QGIS 3.16 or newer. If your city has a mesh network — Meshtastic, MeshCore, anything with coordinates — you can run this on it tonight."

> "QR code on the poster goes straight to GitHub. Thanks."

---

## Backup / Q&A Points

- **"What about buildings?"** — GLO-30 is a surface model, so it includes building heights in dense areas. Not perfect, but better than nothing.
- **"How long does it take?"** — About 2 minutes for 30 nodes on a modern laptop.
- **"Does it work for Meshtastic?"** — The plugin currently connects to MeshCore's API, but any GeoJSON point layer of node locations can be dropped in manually.
- **"What frequency?"** — FSPL calculations use 910 MHz (US LoRa band). Configurable in future versions.
