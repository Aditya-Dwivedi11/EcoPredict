"""Shared satellite-data utilities for EcoPredict environmental analysis."""

from datetime import date
import math

import ee

from ecopredict.satellite import initialize_earth_engine
from ecopredict.validation import (
    validate_bounds,
    validate_period,
    validate_study_area,
)


# Satellite datasets and their measurement definitions.
# These are environmental indicators, not validated risk predictions.

DATASET_CONFIG = {
    "air_pollution": {
        "collection": "COPERNICUS/S5P/OFFL/L3_NO2",
        "band": "tropospheric_NO2_column_number_density",
        "unit": "mol/m²",
        "description": "Tropospheric nitrogen dioxide column density",
        "scale": 1113.2,
    },
    "flood": {
        "collection": "COPERNICUS/S1_GRD",
        "band": "VV",
        "unit": "dB",
        "description": "Sentinel-1 VV backscatter",
        "scale": 10,
    },
    "heatwave": {
        "collection": "MODIS/061/MOD11A2",
        "band": "LST_Day_1km",
        "unit": "K",
        "description": "MODIS daytime land surface temperature",
        "scale": 1000,
        "multiplier": 0.02,
    },
    "deforestation": {
        "collection": "COPERNICUS/S2_SR_HARMONIZED",
        "band": "NDVI",
        "unit": "dimensionless",
        "description": "Sentinel-2 normalized difference vegetation index",
        "scale": 10,
    },
}


def get_region(bounds):
    """Create an Earth Engine rectangle from west, south, east, north."""
    validate_bounds(bounds)
    validate_study_area(bounds)

    west, south, east, north = bounds
    return ee.Geometry.Rectangle([west, south, east, north])


def get_date_interval(start_date, end_date):
    """Validate and return an Earth Engine-compatible date interval."""
    validate_period(start_date, end_date)
    return ee.Date(start_date), ee.Date(end_date)


def prepare_collection(hazard, bounds, start_date, end_date):
    """Load and spatially/temporally filter a configured image collection."""
    if hazard not in DATASET_CONFIG:
        raise ValueError(f"Unsupported environmental hazard: {hazard}")

    region = get_region(bounds)
    start, end = get_date_interval(start_date, end_date)
    config = DATASET_CONFIG[hazard]

    collection = (
        ee.ImageCollection(config["collection"])
        .filterBounds(region)
        .filterDate(start, end)
    )

    if hazard == "deforestation":
        collection = collection.filter(
            ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 80)
        )

    if hazard == "flood":
        collection = collection.filter(
            ee.Filter.eq("instrumentMode", "IW")
        ).filter(
            ee.Filter.listContains(
                "transmitterReceiverPolarisation", "VV"
            )
        )

    return collection, region



def mask_sentinel2_clouds(image):
    """Mask Sentinel-2 pixels classified as cloud, shadow or snow."""
    scl = image.select("SCL")

    clear_mask = (
        scl.eq(4)
        .Or(scl.eq(5))
        .Or(scl.eq(6))
    )

    return image.updateMask(clear_mask)




def mask_modis_lst_quality(image):
    """Retain MODIS daytime LST pixels with good QA and acceptable error."""
    qc = image.select("QC_Day")

    mandatory_qa = qc.bitwiseAnd(3).eq(0)
    data_quality = qc.rightShift(2).bitwiseAnd(3).eq(0)
    lst_error = qc.rightShift(6).bitwiseAnd(3).lte(1)

    return image.updateMask(
        mandatory_qa.And(data_quality).And(lst_error)
    )



def build_indicator_image(hazard, collection):
    """Create a single image representing the selected satellite indicator."""
    config = DATASET_CONFIG[hazard]

    if hazard == "deforestation":
        collection = collection.map(mask_sentinel2_clouds)
        image = collection.median()
        nir = image.select("B8")
        red = image.select("B4")
        return nir.subtract(red).divide(nir.add(red)).rename("NDVI")

    if hazard == "heatwave":
        collection = collection.map(mask_modis_lst_quality)

    image = collection.select(config["band"]).median()

    if hazard == "heatwave":
        image = image.multiply(config["multiplier"]).rename("LST_K")

    return image


def extract_regional_indicator(
    hazard,
    bounds,
    start_date,
    end_date,
):
    """Extract a regional mean and basic metadata for one satellite indicator.

    Earth Engine must be initialized before this function is called.
    """
    if hazard not in DATASET_CONFIG:
        raise ValueError(f"Unsupported environmental hazard: {hazard}")

    collection, region = prepare_collection(
        hazard, bounds, start_date, end_date
    )

    image_count = collection.size()
    count = image_count.getInfo()

    config = DATASET_CONFIG[hazard]

    result = {
        "hazard": hazard,
        "dataset": config["collection"],
        "indicator": config["description"],
        "unit": config["unit"],
        "start_date": start_date,
        "end_date": end_date,
        "image_count": count,
        "status": "no_data",
        "mean": None,
    }

    if count == 0:
        result["message"] = "No satellite images found for this period."
        return result

    image = build_indicator_image(hazard, collection)

    statistics = image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=region,
        scale=config["scale"],
        maxPixels=1e9,
        bestEffort=True,
    ).getInfo()

    band_name = image.bandNames().getInfo()[0]
    mean_value = statistics.get(band_name)

    if mean_value is None or not math.isfinite(float(mean_value)):
        result["message"] = "No valid pixels available for this region."
        return result

    result.update({
        "status": "ok",
        "mean": float(mean_value),
    })

    if hazard == "heatwave":
        result["mean_celsius"] = float(mean_value) - 273.15

    return result


def analyze_environmental_indicator(
    hazard,
    bounds,
    start_date,
    end_date,
):
    """Initialize Earth Engine and extract one environmental indicator."""
    initialize_earth_engine()

    return extract_regional_indicator(
        hazard=hazard,
        bounds=bounds,
        start_date=start_date,
        end_date=end_date,
    )
