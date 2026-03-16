"""
analyze_coverage_breaks.py

Reads the cumulative viewshed raster, analyzes the pixel value distribution,
and derives logical class breaks for display. Outputs both quantile-based
and log-scale breaks, plus a JSON file ready to consume in the Leaflet web map.

Run from the repo root in the OSGeo4W shell or any Python env with GDAL + NumPy:
    python scripts/analyze_coverage_breaks.py

Or paste into the QGIS Python console (update RASTER_PATH as needed).
"""

import json
import numpy as np
from osgeo import gdal

# --- Config ---
RASTER_PATH = "Test_Project/viewsheds/meshcore/cumulative_viewshed.tif"
OUTPUT_JSON = "scripts/coverage_breaks.json"
N_CLASSES = 5


# --- Load raster ---
ds = gdal.Open(RASTER_PATH)
if ds is None:
    raise FileNotFoundError(f"Could not open: {RASTER_PATH}")

band = ds.GetRasterBand(1)
nodata = band.GetNoDataValue()
arr = band.ReadAsArray().astype(float)
ds = None

# Mask NoData and zero (no-coverage pixels)
if nodata is not None:
    arr[arr == nodata] = np.nan
arr[arr == 0] = np.nan
valid = arr[~np.isnan(arr)].astype(int)

print(f"Valid (covered) pixels : {len(valid):,}")
print(f"Min : {valid.min()}")
print(f"Max : {valid.max()}")
print(f"Mean: {valid.mean():.1f}")
print(f"Median: {int(np.median(valid))}")
print(f"p25 / p75 / p90 / p95: "
      f"{int(np.percentile(valid, 25))} / "
      f"{int(np.percentile(valid, 75))} / "
      f"{int(np.percentile(valid, 90))} / "
      f"{int(np.percentile(valid, 95))}")
print()


# --- Break computation helpers ---

def quantile_breaks(values, n):
    """Equal-frequency (quantile) breaks."""
    pcts = np.linspace(0, 100, n + 1)
    return np.unique(np.percentile(values, pcts).astype(int))


def log_breaks(values, n):
    """Log-scale breaks — better for exponential/power-law distributions."""
    log_vals = np.log1p(values)
    pcts = np.linspace(0, 100, n + 1)
    log_b = np.percentile(log_vals, pcts)
    return np.unique(np.expm1(log_b).astype(int))


def describe_breaks(label, breaks, values):
    print(f"=== {label} ===")
    classes = []
    for i in range(len(breaks) - 1):
        lo, hi = int(breaks[i]), int(breaks[i + 1])
        is_last = i == len(breaks) - 2
        count = int(np.sum((values >= lo) & (values <= hi)))
        pct = count / len(values) * 100
        lbl = node_label(lo, hi, is_last)
        print(f"  Class {i + 1}: {lo:>3}–{hi:<3}  ({pct:5.1f}% of covered pixels)  → \"{lbl}\"")
        classes.append({"min": lo, "max": hi, "label": lbl, "pixel_pct": round(pct, 1)})
    print()
    return classes


def node_label(lo, hi, is_last):
    if lo == hi or lo + 1 == hi:
        n = lo
        return f"{n} node{'s' if n != 1 else ''} visible"
    if is_last:
        return f"{lo}+ nodes visible"
    return f"{lo}–{hi} nodes visible"


# --- Compute and print both options ---
q_breaks = quantile_breaks(valid, N_CLASSES)
l_breaks = log_breaks(valid, N_CLASSES)

q_classes = describe_breaks("Quantile Breaks (equal frequency)", q_breaks, valid)
l_classes = describe_breaks("Log-Scale Breaks (suits this distribution)", l_breaks, valid)

# --- Recommendation ---
print("RECOMMENDATION: Use log-scale breaks for this raster.")
print("  Quantile breaks will spread color evenly across pixels, which can")
print("  over-emphasize the very dense core and compress the tail.")
print("  Log-scale preserves perceptual contrast across the full 1–165 range.")
print()

# --- Write JSON for Leaflet ---
output = {
    "raster": RASTER_PATH,
    "stats": {
        "min": int(valid.min()),
        "max": int(valid.max()),
        "mean": round(float(valid.mean()), 1),
        "median": int(np.median(valid)),
        "p25": int(np.percentile(valid, 25)),
        "p75": int(np.percentile(valid, 75)),
        "p90": int(np.percentile(valid, 90)),
        "p95": int(np.percentile(valid, 95)),
    },
    "quantile_breaks": {
        "breaks": [int(b) for b in q_breaks],
        "classes": q_classes,
    },
    "log_breaks": {
        "breaks": [int(b) for b in l_breaks],
        "classes": l_classes,
    },
    "recommended": "log_breaks",
}

with open(OUTPUT_JSON, "w") as f:
    json.dump(output, f, indent=2)

print(f"Breaks written to: {OUTPUT_JSON}")
