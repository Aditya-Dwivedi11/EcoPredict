
"""FastAPI application for EcoPredict."""

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from ecopredict.raster import export_ndvi_rasters
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
    validate_study_area,
)


logger = logging.getLogger(__name__)


# --------------------------------------------------
# Application configuration
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

NDVI_RESULTS_FILE = (
    PROJECT_ROOT / "data" / "processed" / "ndvi_change.csv"
)

RASTER_DIRECTORY = (
    PROJECT_ROOT / "data" / "processed" / "rasters"
)

FRONTEND_DIRECTORY = PROJECT_ROOT / "frontend"


app = FastAPI(
    title="EcoPredict API",
    description=(
        "Environmental risk intelligence using "
        "scientific and satellite-derived data."
    ),
    version="0.1.0",
)


# --------------------------------------------------
# Background analysis job storage
# --------------------------------------------------

# In-memory storage for the current single-process application.
analysis_jobs = {}


# --------------------------------------------------
# Frontend static files
# --------------------------------------------------

if not FRONTEND_DIRECTORY.is_dir():
    raise RuntimeError(
        f"Frontend directory not found: {FRONTEND_DIRECTORY}"
    )

app.mount(
    "/static",
    StaticFiles(directory=FRONTEND_DIRECTORY),
    name="static",
)


# --------------------------------------------------
# Request validation
# --------------------------------------------------

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

            before_end = date.fromisoformat(
                self.before_end
            )

            after_start = date.fromisoformat(
                self.after_start
            )

            if before_end > after_start:
                raise ValueError(
                    "The before period must end on or before "
                    "the after period starts."
                )

        except ValueError as exc:
            raise ValueError(str(exc)) from exc

        return self


# --------------------------------------------------
# Root and dashboard endpoints
# --------------------------------------------------

@app.get("/")
def root():

    return {
        "project": "EcoPredict",
        "status": "running",
        "message": "Environmental risk prediction backend",
        "version": "0.1.0",
    }


@app.get("/dashboard", include_in_schema=False)
def dashboard():

    return FileResponse(
        FRONTEND_DIRECTORY / "index.html"
    )


@app.get("/health")
def health():

    return {
        "status": "healthy",
        "timestamp_utc": datetime.now(
            timezone.utc
        ).isoformat(),
    }


# --------------------------------------------------
# NDVI analysis endpoints
# --------------------------------------------------

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

        results = pd.read_csv(
            NDVI_RESULTS_FILE
        )

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

    except (
        OSError,
        ValueError,
        pd.errors.ParserError,
    ) as exc:

        logger.exception(
            "Could not read saved NDVI results."
        )

        raise HTTPException(
            status_code=500,
            detail="Could not read the satellite results file.",
        ) from exc


# --------------------------------------------------
# Background satellite processing
# --------------------------------------------------

def process_ndvi_analysis(job_id, bounds, periods):
    """Execute satellite analysis and raster export in the background."""

    try:

        analysis_jobs[job_id]["status"] = "running"

        logger.info(
            "Starting background NDVI analysis: %s",
            job_id,
        )

        # Step 1: Initialize Google Earth Engine.
        initialize_earth_engine()

        # Step 2: Run statistical NDVI analysis.
        run_analysis(
            bounds,
            periods,
            NDVI_RESULTS_FILE,
        )

        # Step 3: Export Before, After and Difference rasters.
        exported_files = export_ndvi_rasters(
            bounds=bounds,
            periods=periods,
            output_dir=RASTER_DIRECTORY,
            scale=10,
        )

        # Step 4: Read the latest statistical results.
        results = pd.read_csv(
            NDVI_RESULTS_FILE
        )

        if results.empty:
            raise ValueError(
                "Satellite analysis produced no result records."
            )

        records = json.loads(
            results.to_json(orient="records")
        )

        result_data = {
            "project": "EcoPredict",
            "message": (
                "Satellite analysis and raster export completed."
            ),
            "source": "COPERNICUS/S2_SR_HARMONIZED",
            "indicator": "NDVI",
            "description": (
                "Satellite-derived vegetation greenness. "
                "NDVI change alone does not establish an environmental hazard."
            ),
            "record_count": len(records),
            "results": records,
            "raster_export": {
                "status": "completed",
                "layers": [
                    "before",
                    "after",
                    "difference",
                ],
                "files": [
                    path.name for path in exported_files
                ],
            },
        }

        analysis_jobs[job_id].update({
            "status": "completed",
            "result": result_data,
            "error": None,
        })

        logger.info(
            "Background NDVI analysis completed: %s",
            job_id,
        )

    except Exception as exc:

        logger.exception(
            "Background satellite analysis failed: %s",
            job_id,
        )

        analysis_jobs[job_id].update({
            "status": "failed",
            "result": None,
            "error": str(exc),
        })


# --------------------------------------------------
# Submit NDVI analysis
# --------------------------------------------------

@app.post(
    "/api/v1/ndvi-analysis",
    status_code=202,
)
def create_ndvi_analysis(
    request: NDVIAnalysisRequest,
    background_tasks: BackgroundTasks,
):
    """Submit satellite NDVI analysis as a background job."""

    bounds = (
        request.west,
        request.south,
        request.east,
        request.north,
    )

    periods = [
        (
            request.before_start,
            request.before_end,
        ),
        (
            request.after_start,
            request.after_end,
        ),
    ]

    # Validate study area before starting the background task.
    try:

        validate_study_area(bounds)

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    # Generate a unique job identifier.
    job_id = str(uuid4())

    analysis_jobs[job_id] = {
        "status": "queued",
        "result": None,
        "error": None,
    }

    # Submit the satellite processing task.
    background_tasks.add_task(
        process_ndvi_analysis,
        job_id,
        bounds,
        periods,
    )

    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Satellite analysis has been submitted.",
    }


# --------------------------------------------------
# Check background analysis status
# --------------------------------------------------

@app.get("/api/v1/ndvi-analysis/{job_id}")
def get_analysis_status(job_id: str):
    """Return the current status of a background analysis job."""

    job = analysis_jobs.get(job_id)

    if job is None:

        raise HTTPException(
            status_code=404,
            detail="Analysis job not found.",
        )

    return job


# --------------------------------------------------
# NDVI raster metadata endpoint
# --------------------------------------------------

@app.get("/api/v1/ndvi-rasters/metadata")
def get_ndvi_raster_metadata():
    """Return metadata and statistics for all NDVI raster layers."""

    metadata_file = (
        RASTER_DIRECTORY / "metadata.json"
    )

    if not metadata_file.is_file():

        raise HTTPException(
            status_code=404,
            detail=(
                "NDVI raster metadata not found. "
                "Run raster export first."
            ),
        )

    try:

        export_metadata = json.loads(
            metadata_file.read_text(
                encoding="utf-8"
            )
        )

        layers = {}

        for layer in [
            "before",
            "after",
            "difference",
        ]:

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

    except (
        OSError,
        ValueError,
        KeyError,
    ) as exc:

        logger.exception(
            "Could not read raster metadata."
        )

        raise HTTPException(
            status_code=500,
            detail="Could not read NDVI raster metadata.",
        ) from exc


# --------------------------------------------------
# NDVI raster PNG endpoint
# --------------------------------------------------

@app.get("/api/v1/ndvi-rasters/{layer}.png")
def get_ndvi_raster_image(
    layer: str,
):
    """Return a rendered PNG overlay for an NDVI raster layer."""

    supported_layers = {
        "before",
        "after",
        "difference",
    }

    if layer not in supported_layers:

        raise HTTPException(
            status_code=404,
            detail=(
                "Unknown raster layer. "
                "Choose before, after, or difference."
            ),
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
                "X-Raster-West": str(
                    bounds["west"]
                ),
                "X-Raster-South": str(
                    bounds["south"]
                ),
                "X-Raster-East": str(
                    bounds["east"]
                ),
                "X-Raster-North": str(
                    bounds["north"]
                ),
                "Cache-Control": "no-cache",
            },
        )

    except FileNotFoundError as exc:

        raise HTTPException(
            status_code=404,
            detail=(
                f"Raster layer '{layer}' is not available."
            ),
        ) from exc

    except (
        OSError,
        ValueError,
    ) as exc:

        logger.exception(
            "Could not render raster layer: %s",
            layer,
        )

        raise HTTPException(
            status_code=500,
            detail="Could not render the requested raster layer.",
        ) from exc
