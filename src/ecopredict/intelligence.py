"""Evidence-based interpretation of satellite-derived environmental indicators."""

from typing import Any


HAZARD_GUIDANCE = {
    "air_pollution": {
        "headline": "Atmospheric nitrogen dioxide measurement",
        "meaning": (
            "The satellite measured the amount of nitrogen dioxide in the "
            "atmospheric column above the selected region."
        ),
        "why_it_matters": (
            "Nitrogen dioxide is an air-pollution indicator associated with "
            "combustion sources such as vehicles and industrial activity."
        ),
        "what_to_watch": (
            "Compare measurements across multiple dates and equivalent seasons "
            "to identify persistent changes."
        ),
        "suggested_action": (
            "Investigate sustained increases using additional air-quality "
            "measurements and local monitoring data."
        ),
        "limitation": (
            "This is a satellite column-density measurement, not ground-level "
            "AQI, PM2.5 concentration, or a direct measure of human exposure."
        ),
    },
    "flood": {
        "headline": "Radar surface-backscatter measurement",
        "meaning": (
            "The satellite radar measured how strongly the selected surface "
            "region reflected its radar signal."
        ),
        "why_it_matters": (
            "Changes in radar backscatter can help investigate changes in "
            "surface conditions, including possible water expansion."
        ),
        "what_to_watch": (
            "Compare pre-event and post-event radar images and examine the "
            "spatial distribution of possible water-related changes."
        ),
        "suggested_action": (
            "Use before-and-after imagery and independent geographic evidence "
            "to investigate possible inundation."
        ),
        "limitation": (
            "A regional mean VV backscatter value alone cannot confirm flooding. "
            "Surface type, vegetation, moisture and radar geometry can affect it."
        ),
    },
    "heatwave": {
        "headline": "Daytime land-surface temperature measurement",
        "meaning": (
            "The satellite estimated the average daytime land-surface "
            "temperature over the selected region."
        ),
        "why_it_matters": (
            "Land-surface temperature helps study surface heating and its "
            "variation across locations and observation periods."
        ),
        "what_to_watch": (
            "Compare the measurement with a suitable historical baseline "
            "for the same season and region."
        ),
        "suggested_action": (
            "Investigate persistent unusually high surface temperatures using "
            "historical comparisons and additional local observations."
        ),
        "limitation": (
            "Land-surface temperature is not air temperature. A single "
            "measurement cannot establish that a heatwave occurred."
        ),
    },
    "deforestation": {
        "headline": "Vegetation greenness measurement",
        "meaning": (
            "The satellite-derived NDVI measurement represents vegetation "
            "greenness across the selected region."
        ),
        "why_it_matters": (
            "Changes in vegetation greenness can help identify areas that "
            "may need further investigation for vegetation degradation."
        ),
        "what_to_watch": (
            "Compare NDVI over time and inspect the locations and persistence "
            "of any vegetation decline."
        ),
        "suggested_action": (
            "Investigate persistent declines using spatial change maps, "
            "multi-date imagery and land-cover context."
        ),
        "limitation": (
            "A single regional NDVI average cannot confirm deforestation. "
            "Seasonality, agriculture, clouds and other land-cover changes "
            "can influence NDVI."
        ),
    },
}


def build_environmental_interpretation(
    result: dict[str, Any],
) -> dict[str, Any]:
    """Convert an extracted satellite indicator into a cautious interpretation."""

    hazard = result.get("hazard")
    guidance = HAZARD_GUIDANCE.get(hazard)

    if guidance is None:
        raise ValueError(f"Unsupported environmental hazard: {hazard}")

    value = result.get("mean")
    image_count = result.get("image_count", 0)
    status = result.get("status", "unknown")

    if value is None or image_count == 0:
        evidence_status = "no_data"
        headline = "Insufficient satellite observations"
        plain_language = (
            "There were not enough usable satellite observations to report "
            "a regional measurement for this analysis."
        )
    else:
        evidence_status = "measurement_only"
        headline = guidance["headline"]
        plain_language = guidance["meaning"]

    return {
        "headline": headline,
        "plain_language": plain_language,
        "why_it_matters": guidance["why_it_matters"],
        "what_to_watch": guidance["what_to_watch"],
        "suggested_action": guidance["suggested_action"],
        "evidence_status": evidence_status,
        "source_status": status,
        "scientific": {
            "hazard": hazard,
            "dataset": result.get("dataset"),
            "indicator": result.get("indicator"),
            "value": value,
            "unit": result.get("unit"),
            "image_count": image_count,
            "start_date": result.get("start_date"),
            "end_date": result.get("end_date"),
        },
        "limitations": guidance["limitation"],
    }
