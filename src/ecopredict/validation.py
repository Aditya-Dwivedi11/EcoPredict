
"""Validation helpers for EcoPredict satellite analysis."""

from datetime import date
import math


def validate_bounds(bounds):
    """Validate a bounding box in west, south, east, north order."""
    if len(bounds) != 4:
        raise ValueError("Bounds must contain west, south, east, north.")

    west, south, east, north = bounds

    if not all(math.isfinite(v) for v in bounds):
        raise ValueError("Bounds must contain finite numbers.")

    if not (-180 <= west < east <= 180):
        raise ValueError("Longitude bounds must satisfy -180 <= west < east <= 180.")

    if not (-90 <= south < north <= 90):
        raise ValueError("Latitude bounds must satisfy -90 <= south < north <= 90.")


def validate_period(start_date, end_date):
    """Validate a half-open ISO date interval [start, end)."""
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except (TypeError, ValueError) as exc:
        raise ValueError("Dates must use YYYY-MM-DD format.") from exc

    if start.isoformat() != start_date or end.isoformat() != end_date:
        raise ValueError("Dates must use YYYY-MM-DD format.")

    if start >= end:
        raise ValueError("Start date must be earlier than end date.")


def validate_ndvi(value):
    """Check that an NDVI summary is finite and within [-1, 1]."""
    if value is None:
        raise ValueError("NDVI cannot be missing.")

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("NDVI must be numeric.")

    if not math.isfinite(value) or not -1 <= value <= 1:
        raise ValueError("NDVI must be finite and between -1 and 1.")

# Maximum study area: 5,000 km².
# At 10 m resolution, this is approximately 50 million pixels.
MAX_STUDY_AREA_KM2 = 5000
EARTH_RADIUS_KM = 6371.0088


def calculate_bounds_area_km2(bounds):
    """Calculate the approximate spherical area of a geographic bounding box."""
    validate_bounds(bounds)

    west, south, east, north = bounds

    west_rad = math.radians(west)
    east_rad = math.radians(east)
    south_rad = math.radians(south)
    north_rad = math.radians(north)

    area = (
        EARTH_RADIUS_KM**2
        * (east_rad - west_rad)
        * (math.sin(north_rad) - math.sin(south_rad))
    )

    return area


def validate_study_area(bounds, max_area_km2=MAX_STUDY_AREA_KM2):
    """Reject study areas that are too large for the configured analysis limit."""
    area_km2 = calculate_bounds_area_km2(bounds)

    if area_km2 > max_area_km2:
        raise ValueError(
            f"Study area is too large ({area_km2:,.1f} km²). "
            f"Maximum allowed area is {max_area_km2:,.0f} km². "
            "Please draw a smaller study area."
        )

    return area_km2