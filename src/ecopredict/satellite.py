
"""Sentinel-2 vegetation-change analysis using Google Earth Engine."""

import argparse
import os
from datetime import date
from pathlib import Path

import ee
import pandas as pd

from ecopredict.validation import (
    validate_bounds,
    validate_period,
    validate_ndvi,
)


COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"

# Illustrative Kanpur-area bounding box.
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
    """Mask clouds, shadows, cirrus and unsuitable Sentinel-2 pixels."""
    scl = image.select("SCL")

    # Retain vegetation, bare ground and water.
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
    total_area_m2 = float(region.area(maxError=1).getInfo())

    if scene_count == 0:
        return {
            "start_date": start_date,
            "end_date": end_date,
            "scene_count": 0,
            "mean_ndvi": None,
            "valid_pixel_count": 0,
            "valid_area_m2": 0.0,
            "total_area_m2": total_area_m2,
            "coverage_pct": 0.0,
            "status": "no_scenes",
            "requested_scale_m": 10,
            "best_effort": False,
        }

    composite = collection.map(mask_clouds).median()

    ndvi = composite.normalizedDifference(
        ["B8", "B4"]
    ).rename("NDVI")

    stats = ndvi.reduceRegion(
        reducer=ee.Reducer.mean().combine(
            reducer2=ee.Reducer.count(),
            sharedInputs=True,
        ),
        geometry=region,
        scale=10,
        maxPixels=100_000_000,
        bestEffort=False,
    ).getInfo()

    valid_area_stats = (
        ee.Image.pixelArea()
        .updateMask(ndvi.mask())
        .rename("valid_area_m2")
        .reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=region,
            scale=10,
            maxPixels=100_000_000,
            bestEffort=False,
        )
        .getInfo()
    )

    valid_area_m2 = (
        valid_area_stats.get("valid_area_m2", 0) or 0
    )

    coverage_pct = (
        100.0 * valid_area_m2 / total_area_m2
        if total_area_m2 > 0
        else 0.0
    )

    mean_ndvi = stats.get("NDVI_mean")

    if mean_ndvi is not None:
        validate_ndvi(mean_ndvi)

    valid_pixel_count = stats.get("NDVI_count")

    if valid_pixel_count is None:
        valid_pixel_count = 0
    else:
        valid_pixel_count = int(valid_pixel_count)

    if valid_pixel_count < 0:
        raise ValueError("Valid pixel count cannot be negative.")

    return {
        "start_date": start_date,
        "end_date": end_date,
        "scene_count": int(scene_count),
        "mean_ndvi": mean_ndvi,
        "valid_pixel_count": valid_pixel_count,
        "valid_area_m2": float(valid_area_m2),
        "total_area_m2": total_area_m2,
        "coverage_pct": float(coverage_pct),
        "status": (
            "ok" if mean_ndvi is not None else "no_valid_pixels"
        ),
        "requested_scale_m": 10,
        "best_effort": False,
    }


def run_analysis(bounds, periods, output_path):
    """Analyze two chronological periods and save a CSV."""
    validate_bounds(bounds)

    if len(periods) != 2:
        raise ValueError(
            "Exactly two periods are required: before and after."
        )

    for start_date, end_date in periods:
        validate_period(start_date, end_date)

    before_start = date.fromisoformat(periods[0][0])
    after_start = date.fromisoformat(periods[1][0])
    before_end = date.fromisoformat(periods[0][1])

    if before_start >= after_start or before_end > after_start:
        raise ValueError(
            "The before period must end on or before the after period starts."
        )

    west, south, east, north = bounds

    region = ee.Geometry.Rectangle(
        [west, south, east, north]
    )

    rows = []

    for start_date, end_date in periods:
        rows.append(
            analyze_period(region, start_date, end_date)
        )

    before, after = rows

    comparable = (
        before["status"] == "ok"
        and after["status"] == "ok"
    )

    change = None

    if comparable:
        change = after["mean_ndvi"] - before["mean_ndvi"]

    for row in rows:
        row.update({
            "source_collection": COLLECTION,
            "west": west,
            "south": south,
            "east": east,
            "north": north,
            "requested_scale_m": 10,
            "best_effort": False,
            "ndvi_change_after_minus_before": change,
        })

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    results = pd.DataFrame(rows)
    results.to_csv(output, index=False)

    print(f"Saved results: {output}")
    print(results.to_string(index=False))


def valid_date(value):
    """Validate a strict YYYY-MM-DD command-line date."""
    try:
        parsed = date.fromisoformat(value)

        if parsed.isoformat() != value:
            raise ValueError("Non-canonical date format.")

        return value

    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(
            "Use a date in YYYY-MM-DD format."
        ) from exc


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Compare vegetation indices from Sentinel-2 imagery."
        )
    )

    parser.add_argument(
        "--west",
        type=float,
        default=DEFAULT_BOUNDS[0],
    )
    parser.add_argument(
        "--south",
        type=float,
        default=DEFAULT_BOUNDS[1],
    )
    parser.add_argument(
        "--east",
        type=float,
        default=DEFAULT_BOUNDS[2],
    )
    parser.add_argument(
        "--north",
        type=float,
        default=DEFAULT_BOUNDS[3],
    )

    parser.add_argument(
        "--before-start",
        type=valid_date,
        default="2024-10-01",
    )
    parser.add_argument(
        "--before-end",
        type=valid_date,
        default="2024-11-01",
    )
    parser.add_argument(
        "--after-start",
        type=valid_date,
        default="2025-10-01",
    )
    parser.add_argument(
        "--after-end",
        type=valid_date,
        default="2025-11-01",
    )

    parser.add_argument(
        "--output",
        default="data/processed/ndvi_change.csv",
    )

    args = parser.parse_args()

    periods = [
        (args.before_start, args.before_end),
        (args.after_start, args.after_end),
    ]

    try:
        validate_bounds(
            (args.west, args.south, args.east, args.north)
        )

        for start, end in periods:
            validate_period(start, end)

        if (
            date.fromisoformat(periods[0][1])
            > date.fromisoformat(periods[1][0])
        ):
            raise ValueError(
                "The before period must end on or before "
                "the after period starts."
            )

    except ValueError as exc:
        parser.error(str(exc))

    initialize_earth_engine()

    run_analysis(
        (
            args.west,
            args.south,
            args.east,
            args.north,
        ),
        periods,
        args.output,
    )


if __name__ == "__main__":
    main()
