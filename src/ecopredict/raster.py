
"""Export satellite-derived NDVI rasters as GeoTIFF files."""

import argparse
import json
import shutil
import urllib.request
from datetime import date
from pathlib import Path

import ee
import rasterio
NODATA_VALUE = -9999.0

from ecopredict.satellite import (
    COLLECTION,
    DEFAULT_BOUNDS,
    initialize_earth_engine,
    mask_clouds,
)
from ecopredict.validation import validate_bounds, validate_period


def build_ndvi(region, start_date, end_date):
    """Build a median NDVI composite and return its native CRS."""

    collection = (
        ee.ImageCollection(COLLECTION)
        .filterBounds(region)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 80))
    )

    scene_count = collection.size().getInfo()

    if scene_count == 0:
        raise ValueError(
            f"No Sentinel-2 scenes found for {start_date} to {end_date}."
        )

    first_image = ee.Image(collection.first())
    projection = first_image.select("B8").projection()
    crs = projection.crs().getInfo()

    composite = (
        collection
        .map(mask_clouds)
        .median()
        .setDefaultProjection(projection)
    )

    ndvi = (
        composite
        .normalizedDifference(["B8", "B4"])
        .rename("NDVI")
        .reproject(crs=crs, scale=10)
    )

    return ndvi, crs, int(scene_count)


def download_geotiff(image, region, output_path, crs, scale=10):
    """Download an Earth Engine image as a GeoTIFF with explicit NoData."""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = output_path.with_name(
        f"{output_path.stem}.tmp.tif"
    )

    # Replace masked pixels, including areas outside the image footprint.
    export_image = image.unmask(
        NODATA_VALUE,
        sameFootprint=False,
    )

    params = {
        "name": output_path.stem,
        "region": region,
        "crs": crs,
        "scale": scale,
        "format": "GEO_TIFF",
    }

    try:
        url = export_image.getDownloadURL(params)

        with urllib.request.urlopen(url, timeout=180) as response:
            with output_path.open("wb") as output:
                shutil.copyfileobj(response, output)

        if output_path.stat().st_size == 0:
            raise RuntimeError("Downloaded GeoTIFF is empty.")

        # Explicitly write the NoData metadata into the GeoTIFF.
        with rasterio.open(output_path) as src:
            profile = src.profile.copy()
            profile.update(
                driver="GTiff",
                nodata=NODATA_VALUE,
            )
            data = src.read()

        with rasterio.open(temporary_path, "w", **profile) as dst:
            dst.write(data)

        temporary_path.replace(output_path)

    except Exception:
        output_path.unlink(missing_ok=True)
        temporary_path.unlink(missing_ok=True)
        raise

    return output_path


def export_ndvi_rasters(bounds, periods, output_dir, scale=10):
    """Export before, after and NDVI difference GeoTIFFs."""

    validate_bounds(bounds)

    if len(periods) != 2:
        raise ValueError("Exactly two periods are required.")

    for start, end in periods:
        validate_period(start, end)

    before_start = date.fromisoformat(periods[0][0])
    before_end = date.fromisoformat(periods[0][1])
    after_start = date.fromisoformat(periods[1][0])

    if before_start >= after_start or before_end > after_start:
        raise ValueError(
            "The before period must end on or before the after period starts."
        )

    if scale <= 0:
        raise ValueError("Scale must be greater than zero.")

    west, south, east, north = bounds

    region = ee.Geometry.Rectangle(
        [west, south, east, north]
    )

    before_ndvi, crs, before_scenes = build_ndvi(
        region, periods[0][0], periods[0][1]
    )

    after_ndvi, _, after_scenes = build_ndvi(
        region, periods[1][0], periods[1][1]
    )

    # Use the same CRS and pixel scale for comparison.
    before_aligned = before_ndvi.reproject(crs=crs, scale=scale)
    after_aligned = after_ndvi.reproject(crs=crs, scale=scale)

    difference = (
        after_aligned
        .subtract(before_aligned)
        .rename("NDVI_difference")
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    before_path = download_geotiff(
        before_aligned,
        region,
        output_dir / "ndvi_before.tif",
        crs,
        scale,
    )

    after_path = download_geotiff(
        after_aligned,
        region,
        output_dir / "ndvi_after.tif",
        crs,
        scale,
    )

    difference_path = download_geotiff(
        difference,
        region,
        output_dir / "ndvi_difference.tif",
        crs,
        scale,
    )

    metadata = {
        "source_collection": COLLECTION,
        "bounds": list(bounds),
        "before_period": list(periods[0]),
        "after_period": list(periods[1]),
        "before_scene_count": before_scenes,
        "after_scene_count": after_scenes,
        "crs": crs,
        "requested_scale_m": scale,
        "difference_formula": "after_ndvi - before_ndvi",
        "outputs": [
            before_path.name,
            after_path.name,
            difference_path.name,
        ],
    }

    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=4),
        encoding="utf-8",
    )

    return [
        before_path,
        after_path,
        difference_path,
        metadata_path,
    ]


def main():
    parser = argparse.ArgumentParser(
        description="Export Sentinel-2 NDVI GeoTIFF rasters."
    )

    parser.add_argument("--west", type=float, default=DEFAULT_BOUNDS[0])
    parser.add_argument("--south", type=float, default=DEFAULT_BOUNDS[1])
    parser.add_argument("--east", type=float, default=DEFAULT_BOUNDS[2])
    parser.add_argument("--north", type=float, default=DEFAULT_BOUNDS[3])

    parser.add_argument("--before-start", default="2024-10-01")
    parser.add_argument("--before-end", default="2024-11-01")
    parser.add_argument("--after-start", default="2025-10-01")
    parser.add_argument("--after-end", default="2025-11-01")

    parser.add_argument(
        "--output-dir",
        default="data/processed/rasters",
    )

    args = parser.parse_args()

    bounds = (
        args.west,
        args.south,
        args.east,
        args.north,
    )

    periods = [
        (args.before_start, args.before_end),
        (args.after_start, args.after_end),
    ]

    validate_bounds(bounds)

    for start, end in periods:
        validate_period(start, end)

    initialize_earth_engine()

    outputs = export_ndvi_rasters(
        bounds,
        periods,
        args.output_dir,
    )

    print("\nNDVI raster export completed.")

    for path in outputs:
        print(f"Created: {path}")


if __name__ == "__main__":
    main()
