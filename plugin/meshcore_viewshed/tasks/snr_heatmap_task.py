import os
import json
import traceback
import numpy as np
from qgis.core import QgsTask, QgsRasterLayer, QgsProject


# ---------------------------------------------------------------------------
# Packet parsing helpers
# ---------------------------------------------------------------------------

def _parse_advert_pubkey(raw_hex: str):
    """
    Extract the sender's 32-byte public key from a raw ADVERT packet.

    MeshCore packet layout:
        Byte 0          header  (bits 0-1 = route_type, bits 2-5 = payload_type)
        Bytes 1-4       transport codes (only for TRANSPORT_FLOOD=0x00 / TRANSPORT_DIRECT=0x03)
        Byte N          packed path-length byte
        Bytes N+1...    path bytes (hop_count * bytes_per_hop)
        Payload[0:32]   sender pubkey  (ADVERT type = 0x04)

    Returns lowercase hex string (64 chars) or None on any parse error.
    """
    try:
        b = bytes.fromhex(raw_hex)
        if len(b) < 2:
            return None
        header = b[0]
        route_type = header & 0x03
        payload_type = (header >> 2) & 0x0F
        if payload_type != 0x04:  # not ADVERT
            return None
        offset = 1
        if route_type in (0x00, 0x03):  # TRANSPORT_FLOOD / TRANSPORT_DIRECT
            offset += 4
        if offset >= len(b):
            return None
        path_len_byte = b[offset]
        offset += 1
        hop_count = path_len_byte & 0x3F
        bytes_per_hop = (path_len_byte >> 6) + 1
        # Mode-3 reserved: fall back to legacy single-byte interpretation
        path_byte_len = path_len_byte if bytes_per_hop == 4 else hop_count * bytes_per_hop
        offset += path_byte_len
        if offset + 32 > len(b):
            return None
        return b[offset:offset + 32].hex()
    except Exception:
        return None


def _idw(points, values, grid_x, grid_y, power=1.5):
    """
    Vectorised inverse-distance-weighting interpolation.

    points  : (N, 2) array of (lon, lat)
    values  : (N,)  array of SNR floats
    grid_x  : (rows, cols) meshgrid of longitudes
    grid_y  : (rows, cols) meshgrid of latitudes
    Returns : (rows, cols) array of interpolated SNR
    """
    gx = grid_x.ravel()
    gy = grid_y.ravel()
    dx = gx[:, None] - points[:, 0][None, :]
    dy = gy[:, None] - points[:, 1][None, :]
    dist2 = dx * dx + dy * dy
    dist2[dist2 < 1e-20] = 1e-20  # avoid division by zero at exact hits
    weights = 1.0 / dist2 ** (power / 2.0)
    result = (weights * values[None, :]).sum(axis=1) / weights.sum(axis=1)
    return result.reshape(grid_x.shape)


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

class SnrHeatmapTask(QgsTask):
    def __init__(self, work_dir, packets_path, log_fn):
        super().__init__("MeshCore: SNR Heatmap", QgsTask.CanCancel)
        self.work_dir = work_dir
        self.packets_path = packets_path
        self.log = log_fn
        self.error = None
        self.output_path = os.path.join(work_dir, "data", "meshcore_snr_heatmap.tif")
        # Remove any existing layer now (main thread) to release the file lock
        for lyr in QgsProject.instance().mapLayersByName("Signal Quality (SNR dB)"):
            QgsProject.instance().removeMapLayer(lyr.id())

    def run(self):
        try:
            return self._run()
        except Exception:
            self.error = traceback.format_exc()
            return False

    def _run(self):
        from osgeo import gdal, osr

        # --- 1. Load node positions from GeoJSON ---
        nodes_path = os.path.join(self.work_dir, "data", "meshcore_nodes_plus.geojson")
        if not os.path.exists(nodes_path):
            nodes_path = os.path.join(self.work_dir, "data", "meshcore_nodes.geojson")
        if not os.path.exists(nodes_path):
            self.error = "No nodes GeoJSON found — run Fetch Nodes first."
            return False

        node_pos = {}  # pubkey_hex (lowercase) -> (lon, lat)
        with open(nodes_path, encoding="utf-8") as f:
            fc = json.load(f)
        for feat in fc.get("features", []):
            nid = (feat.get("properties") or {}).get("id")
            if not nid:
                continue
            coords = (feat.get("geometry") or {}).get("coordinates")
            if not coords or len(coords) < 2:
                continue
            node_pos[nid.lower()] = (float(coords[0]), float(coords[1]))

        self.log(f"[SNR] Loaded {len(node_pos)} node positions.")

        if not os.path.exists(self.packets_path):
            self.error = f"Packets file not found: {self.packets_path}"
            return False

        # --- 2. Parse packet log — collect best SNR per node from ADVERT packets ---
        # Supports both single-line NDJSON and pretty-printed multi-line JSON objects
        node_snr = {}   # pubkey_hex -> best float SNR
        total_read = advert_valid = matched = 0

        with open(self.packets_path, encoding="utf-8") as f:
            content = f.read()

        decoder = json.JSONDecoder()
        pos = 0
        while pos < len(content):
            while pos < len(content) and content[pos] in " \t\n\r":
                pos += 1
            if pos >= len(content):
                break
            try:
                pkt, end_pos = decoder.raw_decode(content, pos)
                pos = end_pos
            except json.JSONDecodeError:
                pos += 1
                continue
            total_read += 1

            if pkt.get("packet_type") != "4":   # ADVERT only
                continue
            snr_raw = pkt.get("SNR", "Unknown")
            if snr_raw == "Unknown":
                continue
            try:
                snr_val = float(snr_raw)
            except (ValueError, TypeError):
                continue

            raw_hex = pkt.get("raw", "")
            if not raw_hex:
                continue
            sender_key = _parse_advert_pubkey(raw_hex)
            if not sender_key:
                continue
            advert_valid += 1

            if sender_key not in node_pos:
                continue
            matched += 1
            # Keep the strongest (highest) SNR observation per node
            if sender_key not in node_snr or snr_val > node_snr[sender_key]:
                node_snr[sender_key] = snr_val

        self.log(
            f"[SNR] {total_read} packets read, "
            f"{advert_valid} valid ADVERT packets, "
            f"{matched} matched known nodes, "
            f"{len(node_snr)} unique node observations."
        )

        if len(node_snr) < 2:
            self.error = (
                f"Only {len(node_snr)} matched node observation(s) — "
                "need ≥2 for IDW interpolation. "
                "Collect more packets or wait for the next advert cycle (~11 min)."
            )
            return False

        # --- 3. Build IDW grid ---
        obs_keys = list(node_snr.keys())
        lons = np.array([node_pos[k][0] for k in obs_keys])
        lats = np.array([node_pos[k][1] for k in obs_keys])
        snrs = np.array([node_snr[k] for k in obs_keys])

        # Extent: node bounding box + 20% padding (minimum 0.01°)
        lon_span = max(lons.max() - lons.min(), 0.001)
        lat_span = max(lats.max() - lats.min(), 0.001)
        pad_lon = lon_span * 0.20 + 0.01
        pad_lat = lat_span * 0.20 + 0.01
        west  = lons.min() - pad_lon
        east  = lons.max() + pad_lon
        south = lats.min() - pad_lat
        north = lats.max() + pad_lat

        pixel = 0.002   # ~200 m at mid-latitudes
        ncols = max(int((east - west)  / pixel), 4)
        nrows = max(int((north - south) / pixel), 4)

        gx = np.linspace(west  + pixel / 2, east  - pixel / 2, ncols)
        gy = np.linspace(north - pixel / 2, south + pixel / 2, nrows)
        grid_x, grid_y = np.meshgrid(gx, gy)

        grid_snr = _idw(np.column_stack([lons, lats]), snrs, grid_x, grid_y)

        self.log(
            f"[SNR] Grid: {ncols}×{nrows} pixels, "
            f"SNR range {snrs.min():.1f} – {snrs.max():.1f} dB"
        )

        # --- 4. Write GeoTIFF ---
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        driver = gdal.GetDriverByName("GTiff")
        ds = driver.Create(self.output_path, ncols, nrows, 1, gdal.GDT_Float32)
        ds.SetGeoTransform([west, pixel, 0, north, 0, -pixel])
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        ds.SetProjection(srs.ExportToWkt())
        band = ds.GetRasterBand(1)
        band.WriteArray(grid_snr.astype(np.float32))
        band.SetNoDataValue(-9999.0)
        ds.FlushCache()
        ds = None

        return True

    def finished(self, result):
        if result:
            self.log("[SNR] Heatmap written.")
            self._load_layer()
        else:
            self.log(f"[SNR] Failed: {self.error}")

    def _load_layer(self):
        if not os.path.exists(self.output_path):
            return
        layer_name = "Signal Quality (SNR dB)"
        for lyr in QgsProject.instance().mapLayersByName(layer_name):
            QgsProject.instance().removeMapLayer(lyr.id())
        layer = QgsRasterLayer(self.output_path, layer_name)
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            from meshcore_viewshed.symbology import apply_snr_heatmap_symbology
            apply_snr_heatmap_symbology(layer)
            self.log("[SNR] Layer loaded.")
        else:
            self.log("[SNR] Layer invalid after write.")
