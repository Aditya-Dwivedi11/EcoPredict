
import pytest

from ecopredict.validation import (
    validate_bounds,
    validate_period,
    validate_ndvi,
)


def test_valid_kanpur_bounds():
    validate_bounds((80.20, 26.38, 80.45, 26.55))


@pytest.mark.parametrize(
    "bounds",
    [
        (80.45, 26.38, 80.20, 26.55),
        (80.20, 26.55, 80.45, 26.38),
        (181, 0, 182, 1),
        (80, -91, 81, -90),
        (float("nan"), 0, 1, 1),
        (80, 0, 1),
    ],
)
def test_invalid_bounds(bounds):
    with pytest.raises(ValueError):
        validate_bounds(bounds)


def test_valid_period():
    validate_period("2024-10-01", "2024-11-01")


@pytest.mark.parametrize(
    "start,end",
    [
        ("2024-11-01", "2024-10-01"),
        ("2024-10-01", "2024-10-01"),
        ("2024-02-30", "2024-03-01"),
        ("01-10-2024", "2024-11-01"),
    ],
)
def test_invalid_period(start, end):
    with pytest.raises(ValueError):
        validate_period(start, end)


@pytest.mark.parametrize("value", [-1, -0.2, 0, 0.43, 1])
def test_valid_ndvi(value):
    validate_ndvi(value)


@pytest.mark.parametrize("value", [None, -1.1, 1.1, float("nan"), float("inf"), True])
def test_invalid_ndvi(value):
    with pytest.raises(ValueError):
        validate_ndvi(value)

        # PYTHONPATH=src python -m ecopredict.satellite   export EE_PROJECT_ID="ecopredict-512404"