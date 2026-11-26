import pytest

from ecopredict.intelligence import build_environmental_interpretation


@pytest.fixture
def sample_result():
    return {
        "hazard": "heatwave",
        "dataset": "MODIS/061/MOD11A2",
        "indicator": "LST_Day_1km",
        "mean": 30.23,
        "unit": "°C",
        "image_count": 4,
        "start_date": "2024-10-01",
        "end_date": "2024-11-01",
        "status": "completed",
    }


def test_interpretation_preserves_scientific_measurement(sample_result):
    result = build_environmental_interpretation(sample_result)

    assert result["evidence_status"] == "measurement_only"
    assert result["scientific"]["value"] == 30.23
    assert result["scientific"]["unit"] == "°C"
    assert result["scientific"]["image_count"] == 4
    assert result["scientific"]["dataset"] == "MODIS/061/MOD11A2"


def test_heatwave_interpretation_explains_temperature_limitation(sample_result):
    result = build_environmental_interpretation(sample_result)

    assert "not air temperature" in result["limitations"]
    assert "cannot establish that a heatwave occurred" in result["limitations"]


@pytest.mark.parametrize(
    "hazard",
    ["air_pollution", "flood", "heatwave", "deforestation"],
)
def test_all_four_hazards_have_interpretations(sample_result, hazard):
    sample_result["hazard"] = hazard

    result = build_environmental_interpretation(sample_result)

    assert result["headline"]
    assert result["plain_language"]
    assert result["why_it_matters"]
    assert result["what_to_watch"]
    assert result["suggested_action"]
    assert result["limitations"]


def test_missing_observations_are_not_reported_as_measurements(sample_result):
    sample_result["mean"] = None
    sample_result["image_count"] = 0

    result = build_environmental_interpretation(sample_result)

    assert result["evidence_status"] == "no_data"
    assert result["scientific"]["value"] is None
    assert "Insufficient" in result["headline"]


def test_unsupported_hazard_is_rejected(sample_result):
    sample_result["hazard"] = "earthquake"

    with pytest.raises(ValueError):
        build_environmental_interpretation(sample_result)
