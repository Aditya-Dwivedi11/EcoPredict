
"""FastAPI application for EcoPredict."""

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator

from ecopredict.raster_visualization import (
    get_raster_metadata,
    render_raster_png,
)
from ecopredict.satellite import (
    initialize_earth_engine,
    run_analysis,
)
from ecopredict.validation import (
    validate_bounds,
    validate_period,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="EcoPredict API",
    description=(
        "Environmental risk intelligence using "
        "scientific and satellite-derived data."
    ),
    version="0.1.0",
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


NDVI_RESULTS_FILE = (
    PROJECT_ROOT / "data" / "processed" / "ndvi_change.csv"
)

RASTER_DIRECTORY = (
    PROJECT_ROOT / "data" / "processed" / "rasters"
)


class NDVIAnalysisRequest(BaseModel):
    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)

    before_start: str
    before_end: str
    after_start: str
    after_end: str

    @model_validator(mode="after")
    def validate_analysis_inputs(self):
        try:
            validate_bounds(
                (
                    self.west,
                    self.south,
                    self.east,
                    self.north,
                )
            )

            validate_period(
                self.before_start,
                self.before_end,
            )

            validate_period(
                self.after_start,
                self.after_end,
            )

            before_end = date.fromisoformat(self.before_end)
            after_start = date.fromisoformat(self.after_start)

            if before_end > after_start:
                raise ValueError(
                    "The before period must end on or before "
                    "the after period starts."
                )

        except ValueError as exc:
            raise ValueError(str(exc)) from exc

        return self


@app.get("/")
def root():
    return {
        "project": "EcoPredict",
        "status": "running",
        "message": "Environmental risk prediction backend",
        "version": "0.1.0",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/ndvi-analysis")
def get_ndvi_analysis():
    """Return the latest saved satellite NDVI analysis."""

    if not NDVI_RESULTS_FILE.is_file():
        raise HTTPException(
            status_code=404,
            detail=(
                "No satellite analysis results found. "
                "Run the satellite analysis first."
            ),
        )

    try:
        results = pd.read_csv(NDVI_RESULTS_FILE)

        if results.empty:
            raise HTTPException(
                status_code=404,
                detail="The satellite results file contains no records.",
            )

        records = json.loads(
            results.to_json(orient="records")
        )

        return {
            "project": "EcoPredict",
            "source": "COPERNICUS/S2_SR_HARMONIZED",
            "indicator": "NDVI",
            "description": (
                "Satellite-derived vegetation greenness. "
                "Changes alone do not establish the cause "
                "or confirm an environmental hazard."
            ),
            "record_count": len(records),
            "results": records,
        }

    except HTTPException:
        raise

    except (OSError, ValueError, pd.errors.ParserError) as exc:
        logger.exception("Could not read saved NDVI results.")

        raise HTTPException(
            status_code=500,
            detail="Could not read the satellite results file.",
        ) from exc


@app.post("/api/v1/ndvi-analysis")
def create_ndvi_analysis(request: NDVIAnalysisRequest):
    """Run satellite NDVI analysis for a requested area and two periods."""

    bounds = (
        request.west,
        request.south,
        request.east,
        request.north,
    )

    periods = [
        (request.before_start, request.before_end),
        (request.after_start, request.after_end),
    ]

    try:
        initialize_earth_engine()

        run_analysis(
            bounds,
            periods,
            NDVI_RESULTS_FILE,
        )

        results = pd.read_csv(NDVI_RESULTS_FILE)

        if results.empty:
            raise HTTPException(
                status_code=422,
                detail="Satellite analysis produced no result records.",
            )

        records = json.loads(
            results.to_json(orient="records")
        )

        return {
            "project": "EcoPredict",
            "message": "Satellite analysis completed.",
            "source": "COPERNICUS/S2_SR_HARMONIZED",
            "indicator": "NDVI",
            "description": (
                "Satellite-derived vegetation greenness. "
                "NDVI change alone does not establish an environmental hazard."
            ),
            "record_count": len(records),
            "results": records,
        }

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception("Satellite analysis failed.")

        raise HTTPException(
            status_code=502,
            detail=(
                "Satellite analysis could not be completed. "
                "Check Earth Engine authentication, project configuration, "
                "permissions, and data availability."
            ),
        ) from exc


@app.get("/api/v1/ndvi-rasters/metadata")
def get_ndvi_raster_metadata():
    """Return metadata and statistics for all NDVI raster layers."""

    metadata_file = RASTER_DIRECTORY / "metadata.json"

    if not metadata_file.is_file():
        raise HTTPException(
            status_code=404,
            detail="NDVI raster metadata not found. Run raster export first.",
        )

    try:
        export_metadata = json.loads(
            metadata_file.read_text(encoding="utf-8")
        )

        layers = {}

        for layer in ["before", "after", "difference"]:
            layers[layer] = get_raster_metadata(
                layer,
                RASTER_DIRECTORY,
            )

        return {
            "project": "EcoPredict",
            "indicator": "NDVI",
            "source": export_metadata["source_collection"],
            "before_period": export_metadata["before_period"],
            "after_period": export_metadata["after_period"],
            "layers": layers,
        }

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except (OSError, ValueError, KeyError) as exc:
        logger.exception("Could not read raster metadata.")

        raise HTTPException(
            status_code=500,
            detail="Could not read NDVI raster metadata.",
        ) from exc


@app.get("/api/v1/ndvi-rasters/{layer}.png")
def get_ndvi_raster_image(layer: str):
    """Return a rendered PNG overlay for an NDVI raster layer."""

    if layer not in {"before", "after", "difference"}:
        raise HTTPException(
            status_code=404,
            detail="Unknown raster layer. Choose before, after, or difference.",
        )

    try:
        png_data, bounds = render_raster_png(
            layer,
            RASTER_DIRECTORY,
        )

        return Response(
            content=png_data,
            media_type="image/png",
            headers={
                "X-Raster-West": str(bounds["west"]),
                "X-Raster-South": str(bounds["south"]),
                "X-Raster-East": str(bounds["east"]),
                "X-Raster-North": str(bounds["north"]),
                "Cache-Control": "no-cache",
            },
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Raster layer '{layer}' is not available.",
        ) from exc

    except (OSError, ValueError) as exc:
        logger.exception("Could not render raster layer: %s", layer)

        raise HTTPException(
            status_code=500,
            detail="Could not render the requested raster layer.",
        ) from exc
