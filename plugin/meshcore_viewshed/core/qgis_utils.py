"""
qgis_utils.py — Auto-detect the QGIS installation and expose tool paths.

Used by viewshed_batch.py so scripts work regardless of whether QGIS tools are
on the system PATH. Run this file directly to print a diagnostics summary:

    python scripts/qgis_utils.py
"""

import glob
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Dict, Optional

# ---------------------------------------------------------------------------
# Platform-specific search roots
# ---------------------------------------------------------------------------

_WINDOWS_ROOTS = [
    # QGIS standalone installers (newest versions first via glob)
    r"C:\Program Files\QGIS *",
    r"C:\Program Files (x86)\QGIS *",
    # OSGeo4W
    r"C:\OSGeo4W64",
    r"C:\OSGeo4W",
]

_LINUX_ROOTS = [
    "/usr",
    "/usr/local",
    "/opt/qgis",
    "/opt/qgis-ltr",
]

_MACOS_ROOTS = [
    "/Applications/QGIS.app/Contents/MacOS",
    "/Applications/QGIS-LTR.app/Contents/MacOS",
]

# Subdirectories within a QGIS root that contain binaries
_BIN_SUBDIRS = ["bin", ""]


def _candidate_bin_dirs() -> list:
    """Return all directories to search for QGIS binaries, ordered by preference."""
    system = platform.system()
    candidates = []

    if system == "Windows":
        for pattern in _WINDOWS_ROOTS:
            # glob to handle version wildcards like "QGIS 3.38"
            for root in sorted(glob.glob(pattern), reverse=True):  # newest first
                for sub in _BIN_SUBDIRS:
                    p = Path(root) / sub if sub else Path(root)
                    if p.is_dir():
                        candidates.append(p)
    elif system == "Linux":
        for root in _LINUX_ROOTS:
            candidates.append(Path(root) / "bin")
    elif system == "Darwin":
        for root in _MACOS_ROOTS:
            candidates.append(Path(root) / "bin")

    return candidates


def find_qgis_bin() -> Optional[Path]:
    """Return the first directory containing a qgis_process variant."""
    # Covers: standalone installer (qgis_process-qgis.bat),
    #         LTR installer (qgis_process-qgis-ltr.bat),
    #         and bare executable names.
    target_names = [
        "qgis_process",
        "qgis_process.exe",
        "qgis_process-qgis.bat",
        "qgis_process-qgis-ltr.bat",
        "qgis_process-qgis-dev.bat",
    ]
    for d in _candidate_bin_dirs():
        for name in target_names:
            if (d / name).exists():
                return d
    return None


def find_qgis_process_bat() -> Optional[Path]:
    """Return the full path to the qgis_process batch/script file."""
    bin_dir = find_qgis_bin()
    if bin_dir is None:
        return None
    for name in [
        "qgis_process-qgis-ltr.bat",
        "qgis_process-qgis.bat",
        "qgis_process-qgis-dev.bat",
        "qgis_process.exe",
        "qgis_process",
    ]:
        p = bin_dir / name
        if p.exists():
            return p
    return None


def find_tool(name: str) -> str:
    """
    Return the absolute path to a CLI tool (e.g. 'gdal_viewshed', 'qgis_process').

    Search order:
    1. QGIS_BIN env variable (user override)
    2. System PATH (shutil.which)
    3. Auto-detected QGIS bin directory

    For 'qgis_process', also checks versioned bat names like
    qgis_process-qgis-ltr.bat used by QGIS standalone installers.

    Returns the bare tool name if nothing is found so the caller gets a clear
    FileNotFoundError rather than silently doing nothing.
    """
    # User override
    env_bin = os.environ.get("QGIS_BIN")
    if env_bin:
        for suffix in ["", ".exe", ".bat"]:
            candidate = Path(env_bin) / (name + suffix)
            if candidate.exists():
                return str(candidate)

    # Already on PATH
    found = shutil.which(name)
    if found:
        return found

    # Auto-detect QGIS installation
    bin_dir = find_qgis_bin()
    if bin_dir:
        if name == "qgis_process":
            qp = find_qgis_process_bat()
            if qp:
                return str(qp)
        for suffix in ["", ".exe", ".bat"]:
            candidate = bin_dir / (name + suffix)
            if candidate.exists():
                return str(candidate)

    return name


def find_qgis_python() -> Optional[Path]:
    """
    Return the path to QGIS's bundled Python interpreter.

    This is the Python that has access to qgis.core, qgis.gui, etc.
    """
    system = platform.system()
    bin_dir = find_qgis_bin()
    if bin_dir is None:
        return None

    qgis_root = bin_dir.parent

    if system == "Windows":
        # Standalone installer: <QGIS root>\apps\Python3xx\python.exe
        for apps_python in sorted(
            (qgis_root / "apps").glob("Python3*"), reverse=True
        ):
            py = apps_python / "python.exe"
            if py.exists():
                return py
        # OSGeo4W: <root>\bin\python3.exe
        py = bin_dir / "python3.exe"
        if py.exists():
            return py
        py = bin_dir / "python.exe"
        if py.exists():
            return py

    elif system == "Linux":
        for name in ["python3", "python"]:
            found = shutil.which(name)
            if found:
                return Path(found)

    elif system == "Darwin":
        py = qgis_root / "bin" / "python3"
        if py.exists():
            return py

    return None


def qgis_pythonpath_entries() -> list:
    """
    Return a list of directories to add to PYTHONPATH for PyQGIS imports.

    Useful for populating .vscode/settings.json python.analysis.extraPaths.
    """
    bin_dir = find_qgis_bin()
    if bin_dir is None:
        return []

    qgis_root = bin_dir.parent
    candidates = [
        qgis_root / "apps" / "qgis" / "python",
        qgis_root / "apps" / "qgis" / "python" / "plugins",
        qgis_root / "apps" / "qgis-ltr" / "python",
        qgis_root / "apps" / "qgis-ltr" / "python" / "plugins",
    ]
    return [str(p) for p in candidates if p.is_dir()]


def describe_env() -> Dict[str, str]:
    """Return a dict describing the detected QGIS environment for diagnostics."""
    return {
        "platform": platform.system(),
        "qgis_bin_dir": str(find_qgis_bin() or "NOT FOUND"),
        "qgis_python": str(find_qgis_python() or "NOT FOUND"),
        "gdal_viewshed": find_tool("gdal_viewshed"),
        "qgis_process": find_tool("qgis_process"),
        "pythonpath_entries": ", ".join(qgis_pythonpath_entries()) or "none",
        "QGIS_BIN env override": os.environ.get("QGIS_BIN", "(not set)"),
    }


def generate_vscode_settings(output_path: str = ".vscode/settings.json") -> bool:
    """
    Write a .vscode/settings.json pointing at the detected QGIS Python interpreter.

    Returns True if written, False if QGIS could not be detected.
    """
    import json

    py = find_qgis_python()
    extra_paths = qgis_pythonpath_entries()

    if py is None:
        print("WARNING: QGIS Python not detected — .vscode/settings.json not written.")
        print("  Set the QGIS_BIN environment variable to your QGIS bin directory and retry.")
        return False

    settings = {
        "python.defaultInterpreterPath": str(py),
        "python.analysis.extraPaths": extra_paths,
        "python.envFile": "${workspaceFolder}/.env",
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Preserve any existing keys we don't manage
    existing = {}
    if out.exists():
        try:
            with open(out) as f:
                existing = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    existing.update(settings)

    with open(out, "w") as f:
        json.dump(existing, f, indent=2)

    print(f"Written: {output_path}")
    print(f"  Interpreter : {py}")
    print(f"  Extra paths : {extra_paths}")
    return True


if __name__ == "__main__":
    print("=== QGIS Environment Diagnostics ===\n")
    env = describe_env()
    for key, val in env.items():
        print(f"  {key:<28} {val}")
    print()

    import argparse
    parser = argparse.ArgumentParser(description="QGIS environment utilities")
    parser.add_argument(
        "--write-vscode",
        nargs="?",
        const=".vscode/settings.json",
        metavar="PATH",
        help="Write .vscode/settings.json for detected QGIS Python (default path if flag given)",
    )
    args = parser.parse_args()

    if args.write_vscode:
        generate_vscode_settings(args.write_vscode)
