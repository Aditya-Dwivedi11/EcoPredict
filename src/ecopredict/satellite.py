
"""Sentinel-2 vegetation-change analysis using Google Earth Engine."""

import argparse
import os
from datetime import date
from pathlib import Path

import ee
import pandas as pd


COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"

# Illustrative Kanpur-area bounding box; replace with your study area.
DEFAULT_BOUNDS = (80.20, 26.38, 80.45, 26.55)


def initialize_earth_engine():
    """Initialize Earth Engine using an explicitly configured Cloud project."""
    project_id = os.getenv("EE_PROJECT_ID")

    if not project_id:
        raise RuntimeError(
            "Set EE_PROJECT_ID to your registered Google Cloud project ID."
        )

    ee.Initialize(project=project_id)


def mask_clouds(image):
    """Keep Sentinel-2 scene-classification pixels suitable for analysis."""
    scl = image.select("SCL")

    # Retain vegetation, bare ground and water; exclude clouds, shadows,
    # cirrus, snow/ice and other scene classes.
    valid = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6))

    return (
        image.updateMask(valid)
        .select(["B4", "B8"])
        .multiply(0.0001)
        .copyProperties(image, ["system:time_start"])
    )


def analyze_period(region, start_date, end_date):
    """Return summary statistics for one half-open date interval."""
    collection = (
        ee.ImageCollection(COLLECTION)
        .filterBounds(region)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 80))
    )

    scene_count = collection.size().getInfo()

    if scene_count == 0:
        return {
            "start_date": start_date,
            "end_date": end_date,
            "scene_count": 0,
            "mean_ndvi": None,
            "valid_pixel_count": 0,
            "status": "no_scenes",
        }

    composite = collection.map(mask_clouds).median()

    ndvi = composite.normalizedDifference(["B8", "B4"]).rename("NDVI")

    stats = ndvi.reduceRegion(
        reducer=ee.Reducer.mean().combine(
            reducer2=ee.Reducer.count(),
            sharedInputs=True,
        ),
        geometry=region,
        scale=10,
        maxPixels=10_000_000,
        bestEffort=True,
    ).getInfo()

    mean_ndvi = stats.get("NDVI_mean")
    valid_pixel_count = stats.get("NDVI_count", 0)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "scene_count": scene_count,
        "mean_ndvi": mean_ndvi,
        "valid_pixel_count": valid_pixel_count,
        "status": "ok" if mean_ndvi is not None else "no_valid_pixels",
    }


def run_analysis(bounds, periods, output_path):
    """Analyze two periods and save a CSV with provenance metadata."""
    west, south, east, north = bounds

    if not (west < east and south < north):
        raise ValueError("Bounds must satisfy west < east and south < north.")

    region = ee.Geometry.Rectangle([west, south, east, north])

    rows = []
    for start_date, end_date in periods:
        rows.append(analyze_period(region, start_date, end_date))

    before, after = rows

    comparable = (
        before["status"] == "ok"
        and after["status"] == "ok"
    )

    for row in rows:
        row.update({
            "source_collection": COLLECTION,
            "west": west,
            "south": south,
            "east": east,
            "north": north,
            "nominal_scale_m": 10,
        })

    change = None
    if comparable:
        change = after["mean_ndvi"] - before["mean_ndvi"]

    for row in rows:
        row["ndvi_change_after_minus_before"] = change

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output, index=False)

    print(f"Saved results: {output}")
    print(pd.DataFrame(rows).to_string(index=False))


def valid_date(value):
    """Validate an ISO-format date supplied on the command line."""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Use a date in YYYY-MM-DD format."
        ) from exc


def main():
    parser = argparse.ArgumentParser(
        description="Compare vegetation indices from Sentinel-2 imagery."
    )
    parser.add_argument("--west", type=float, default=DEFAULT_BOUNDS[0])
    parser.add_argument("--south", type=float, default=DEFAULT_BOUNDS[1])
    parser.add_argument("--east", type=float, default=DEFAULT_BOUNDS[2])
    parser.add_argument("--north", type=float, default=DEFAULT_BOUNDS[3])
    parser.add_argument("--before-start", type=valid_date,
                        default="2024-10-01")
    parser.add_argument("--before-end", type=valid_date,
                        default="2024-11-01")
    parser.add_argument("--after-start", type=valid_date,
                        default="2025-10-01")
    parser.add_argument("--after-end", type=valid_date,
                        default="2025-11-01")
    parser.add_argument("--output", default="data/processed/ndvi_change.csv")
    args = parser.parse_args()

    periods = [
        (args.before_start, args.before_end),
        (args.after_start, args.after_end),
    ]

    for start, end in periods:
        if start >= end:
            parser.error("Each period's start date must be before its end date.")

    initialize_earth_engine()
    run_analysis(
        (args.west, args.south, args.east, args.north),
        periods,
        args.output,
    )


if __name__ == "__main__":
    main()
