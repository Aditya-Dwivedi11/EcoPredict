
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
