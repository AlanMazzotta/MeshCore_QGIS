"""
radar_charts.py — Generic radar chart generator.

Produces one PNG radar chart per data group from either a CSV file or
manually supplied values. Works for any number of axes (3+).

Requirements
------------
  pip install matplotlib numpy

Data input — choose one mode in CONFIG:

  CSV mode:    Set CSV_FILE to a path. One column holds group names;
               remaining numeric columns become radar axes.
               Multiple rows sharing a group name are averaged.

  Manual mode: Set CSV_FILE = None and supply MANUAL_DATA and MANUAL_AXES.

Output
------
  One PNG per group, written to OUTPUT_DIR.
  File names are derived from group names (e.g. "Group A" -> group_a.png).

Usage
-----
  1. Fill in the CONFIG section below.
  2. python radar_charts.py
"""

import csv
import re
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm


# =============================================================================
# CONFIG
# =============================================================================

# --- Data source --------------------------------------------------------------

# Path to a CSV file, or None to use MANUAL_DATA below.
CSV_FILE = None   # e.g. r"path/to/data.csv"

# CSV only: name of the column that identifies each group.
GROUP_COL = "group"

# CSV only: columns to use as axes, mapped to display labels.
# Format: {"csv_column_name": "Axis Label"}
# Leave as {} to auto-detect all numeric columns (excluding GROUP_COL).
AXES_COLS = {}

# Manual mode: supply data when CSV_FILE is None.
# Each key is a group name; each value is a list of raw values,
# one per axis in the same order as MANUAL_AXES.
MANUAL_DATA = {
    "Group A": [80, 35, 90, 60, 45],
    "Group B": [45, 70, 55, 80, 30],
    "Group C": [60, 50, 70, 40, 80],
}

# Axis labels for manual mode (must match the length of each group's list).
MANUAL_AXES = ["Metric 1", "Metric 2", "Metric 3", "Metric 4", "Metric 5"]

# --- Normalization ------------------------------------------------------------

# 'auto'   — each axis is normalised to its maximum value across all groups.
# 'manual' — supply a max value per axis in MAX_VALUES (same order as axes).
NORMALIZE = 'auto'
MAX_VALUES = []   # e.g. [100, 50, 200, 1.0, 500] — only used when NORMALIZE = 'manual'

# --- Colors ------------------------------------------------------------------

# Hex color per group name. Groups not listed here get auto-assigned colors.
COLORS = {
    "Group A": "#D7191C",
    "Group B": "#2C7BB6",
    "Group C": "#1A9641",
}

# --- Output ------------------------------------------------------------------

# Directory to write PNGs (created automatically if it does not exist).
OUTPUT_DIR = r"path/to/your/output/directory"

# Background: 'none' = transparent PNG  |  'black' = dark solid background.
BG = 'none'

# Optional: path to a .ttf font file, or None for matplotlib's default.
# Example (Windows): r"C:\Windows\Fonts\CascadiaCode.ttf"
# Example (Mac/Linux): "/path/to/font.ttf"
FONT_FILE = None

# =============================================================================
# END CONFIG
# =============================================================================

# Fallback color palette for unlisted groups
_AUTO_COLORS = [
    '#F28E2B', '#E15759', '#76B7B2', '#59A14F',
    '#EDC948', '#B07AA1', '#FF9DA7', '#9C755F',
]


def load_csv(path, group_col, axes_cols):
    """Read CSV and return (axes_labels, groups_data, row_counts).

    groups_data:  {group_name: [mean_val_per_axis, ...]}
    row_counts:   {group_name: int}  — actual number of rows per group
    """
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise ValueError(f"No data in {path}")

    all_cols = list(rows[0].keys())

    if not axes_cols:
        # Auto-detect: all columns that look numeric, excluding group_col
        axes_cols = {}
        for col in all_cols:
            if col == group_col:
                continue
            try:
                float(rows[0][col])
                axes_cols[col] = col
            except (ValueError, TypeError):
                pass

    if not axes_cols:
        raise ValueError("No numeric columns found. Set AXES_COLS explicitly.")

    # Accumulate raw values per group per axis column; count rows per group
    raw = {}
    row_counts = {}
    for row in rows:
        grp = row.get(group_col, '').strip()
        if not grp:
            continue
        if grp not in raw:
            raw[grp] = {col: [] for col in axes_cols}
            row_counts[grp] = 0
        row_counts[grp] += 1
        for col in axes_cols:
            try:
                raw[grp][col].append(float(row[col]))
            except (ValueError, TypeError):
                pass

    # Average multiple rows per group
    groups_data = {
        grp: [
            sum(vals) / len(vals) if vals else 0.0
            for vals in col_lists.values()
        ]
        for grp, col_lists in raw.items()
    }

    return list(axes_cols.values()), groups_data, row_counts


def slug(name):
    """Convert a group name to a safe filename stem."""
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')


# --- Load data ----------------------------------------------------------------
if CSV_FILE:
    axes_labels, groups_data, row_counts = load_csv(CSV_FILE, GROUP_COL, AXES_COLS)
else:
    axes_labels, groups_data = MANUAL_AXES, dict(MANUAL_DATA)
    row_counts = {grp: len(vals) for grp, vals in groups_data.items()}

n_axes = len(axes_labels)
if n_axes < 3:
    raise ValueError("Need at least 3 axes for a radar chart.")

# --- Normalization ------------------------------------------------------------
raw_vals = list(groups_data.values())

if NORMALIZE == 'manual':
    if len(MAX_VALUES) != n_axes:
        raise ValueError(f"MAX_VALUES must have {n_axes} entries (one per axis).")
    maxes = list(MAX_VALUES)
else:
    maxes = [
        max(grp[i] for grp in raw_vals) or 1.0
        for i in range(n_axes)
    ]

norm_data = {
    grp: [v / m for v, m in zip(vals, maxes)]
    for grp, vals in groups_data.items()
}

# --- Font --------------------------------------------------------------------
if FONT_FILE and Path(FONT_FILE).exists():
    FONT = fm.FontProperties(fname=FONT_FILE, weight='light')
else:
    FONT = fm.FontProperties()

Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

# --- Axis geometry -----------------------------------------------------------
angles = [np.pi / 2 + k * (2 * np.pi / n_axes) for k in range(n_axes)]

# --- Generate charts ---------------------------------------------------------
auto_color_idx = 0
theta = np.linspace(0, 2 * np.pi, 300)

for grp, vals in norm_data.items():
    color = COLORS.get(grp)
    if color is None:
        color = _AUTO_COLORS[auto_color_idx % len(_AUTO_COLORS)]
        auto_color_idx += 1

    angles_c = np.append(angles, angles[0])
    vals_c   = np.append(vals, vals[0])

    fig = plt.figure(figsize=(2.4, 1.94), facecolor=BG)
    ax  = fig.add_axes((0.12, 0.14, 0.76, 0.60), polar=True)
    ax.set_facecolor(BG)

    # Grid circles
    for r in [0.25, 0.5, 0.75, 1.0]:
        ax.plot(theta, [r] * 300, color='#959595', linewidth=0.5, zorder=1)

    # Axis spokes
    for angle in angles:
        ax.plot([angle, angle], [0, 1], color='#959595', linewidth=0.5, zorder=1)

    # Data polygon
    ax.fill(angles, vals, color=color, alpha=0.15, zorder=2)
    ax.plot(angles_c, vals_c, color=color, linewidth=1.5, zorder=3)
    ax.scatter(angles, vals, color=color, s=20, zorder=4)

    ax.set_ylim(0, 1.0)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.spines['polar'].set_visible(False)
    ax.grid(False)

    # Axis labels
    for angle, label in zip(angles, axes_labels):
        ax.text(angle, 1.3, label, ha='center', va='center',
                fontproperties=FONT, fontsize=7, color='#959595',
                clip_on=False)

    # Title
    title = ax.set_title(f'{grp}   n={row_counts.get(grp, len(groups_data[grp]))}', color=color, pad=24)
    title.set_fontproperties(FONT)
    title.set_fontsize(7)

    out = Path(OUTPUT_DIR) / f'{slug(grp)}_radar.png'
    fig.savefig(str(out), dpi=300, transparent=(BG == 'none'))
    plt.close(fig)
    print(f'Saved: {out}')

print('Done.')
