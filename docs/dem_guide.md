# DEM Guide — Getting Elevation Data for Viewshed Analysis

A Digital Elevation Model (DEM) is required for viewshed analysis. The pipeline
uses it to calculate which parts of terrain are visible from each repeater node.

---

## Quick Start (recommended for most users)

The included script downloads a DEM automatically from **OpenTopography**, which
provides free global datasets via REST API.

### 1. Get a free API key

Register at [portal.opentopography.org/newUser](https://portal.opentopography.org/newUser).
After confirming your email, go to **My Account → API Keys** to copy your key.

### 2. Store the key (optional but convenient)

Add to your `.env` file in the project root:
```
OPENTOPO_API_KEY=your_key_here
```

### 3. Download

If you've already fetched nodes (they're in `data/`), the script auto-detects
your area:
```
python scripts/fetch_dem.py --api-key YOUR_KEY
```

Or specify a bounding box manually (west south east north, decimal degrees):
```
python scripts/fetch_dem.py --api-key YOUR_KEY --bbox -123.5 45.2 -121.8 46.0
```

Output: `data/dem.tif` — ready to pass to the pipeline.

### Dataset options

| Flag | Name | Resolution | Notes |
|------|------|-----------|-------|
| `COP30` | Copernicus DEM | 30 m | **Default. Best global quality.** |
| `SRTMGL1` | NASA SRTM | 30 m | 2000 Space Shuttle mission |
| `NASADEM` | NASA DEM | 30 m | Reprocessed SRTM, often better void fill |
| `AW3D30` | JAXA AW3D | 30 m | Good urban/mountainous coverage |
| `SRTMGL3` | NASA SRTM | 90 m | Lower resolution, smaller download |

For repeater placement analysis, 30 m resolution is sufficient. Use `COP30` unless
you have a specific reason to prefer another dataset.

---

## For experienced GIS users

If you already have a DEM, just drop it in and point the pipeline at it:
```
python scripts/pipeline.py --dem /path/to/your/dem.tif
```

### Accepted formats

| Requirement | Details |
|-------------|---------|
| **Format** | GeoTIFF (`.tif` / `.tiff`) — any GDAL-readable raster also works |
| **Bands** | Single band, elevation values |
| **Units** | Metres (the viewshed tool assumes metres for observer/target heights) |
| **CRS** | Any projected or geographic CRS — GDAL reprojects internally |
| **Resolution** | Any; 30 m or finer recommended for useful viewsheds |
| **No-data** | Any standard no-data value is fine; GDAL reads it from metadata |

### Other free DEM sources

| Source | Resolution | Coverage | Format |
|--------|-----------|---------|--------|
| [USGS National Map](https://apps.nationalmap.gov/downloader/) | 1/3 arc-sec (~10 m) | USA | IMG / GeoTIFF |
| [OpenTopography](https://portal.opentopography.org) | 30 m global | Global | GeoTIFF |
| [Copernicus DEM](https://spacedata.copernicus.eu/collections/copernicus-digital-elevation-model) | 30 m / 90 m | Global | GeoTIFF tiles |
| [ALOS World 3D](https://www.eorc.jaxa.jp/ALOS/en/aw3d30/) | 30 m | Global | GeoTIFF |
| [EU-DEM](https://www.eea.europa.eu/en/datahub/datahubitem-view/d08852bc-7b5f-4835-a776-08362e2fbf4b) | 25 m | Europe | GeoTIFF |

### Pre-processing tips

- **Clip first**: A DEM clipped to your area of interest runs faster and produces
  smaller output files. Use `gdalwarp` or QGIS's Clip Raster by Extent tool.
- **Reproject if needed**: If your DEM is in a local CRS, viewshed results will
  still be correct — `gdal_viewshed` handles the reprojection. No manual step needed.
- **Merge tiles**: If your area spans multiple downloaded tiles, merge them first:
  ```
  gdal_merge.py -o data/dem.tif tile_*.tif
  ```

### Verifying your DEM

```
gdalinfo data/dem.tif
```

Look for:
- `Driver: GTiff/GeoTIFF`
- A valid `Coordinate System` (not "Unknown")
- `Band 1` with `Min`/`Max` values in a plausible elevation range (not all zeros)

---

## File location

The pipeline defaults to `data/dem.tif`. You can override this with `--dem`:
```
python scripts/pipeline.py --dem data/custom_dem.tif
```

DEM files are excluded from git (`.gitignore`) because they can be hundreds of
megabytes. Each user should download or provide their own DEM for their area.
