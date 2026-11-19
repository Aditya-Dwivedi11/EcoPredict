import pytest

from ecopredict.environmental import (
    DATASET_CONFIG,
    prepare_collection,
)


def test_all_four_hazards_are_configured():
    assert set(DATASET_CONFIG) == {
        "air_pollution",
        "flood",
        "heatwave",
        "deforestation",
    }


@pytest.mark.parametrize(
    "hazard",
    ["air_pollution", "flood", "heatwave", "deforestation"],
)
def test_hazard_configuration_has_required_fields(hazard):
    config = DATASET_CONFIG[hazard]

    assert config["collection"]
    assert config["band"]
    assert config["unit"]
    assert config["description"]
    assert config["scale"] > 0


def test_unsupported_hazard_is_rejected():
    with pytest.raises(ValueError, match="Unsupported environmental hazard"):
        prepare_collection(
            "wildfire",
            [80.20, 26.38, 80.45, 26.55],
            "2024-10-01",
            "2024-11-01",
        )
