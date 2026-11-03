# EcoPredict

**Satellite-based environmental monitoring and vegetation-change analysis.**

EcoPredict is a Python-based environmental analysis project that uses satellite imagery and geospatial data to investigate changes in vegetation over a selected geographical area.

The current implementation uses Google Earth Engine and Sentinel-2 Surface Reflectance imagery to calculate the Normalized Difference Vegetation Index (NDVI) for two time periods.

## Current Features

- Sentinel-2 satellite imagery analysis.
- Google Earth Engine integration.
- NDVI calculation and comparison between two periods.
- Cloud and unsuitable-pixel masking using the Sentinel-2 Scene Classification Layer.
- Geographic bounding-box validation.
- Date-range validation.
- Satellite analysis results saved as CSV.
- FastAPI backend.
- API endpoints for health checks and NDVI results.
- API endpoint for requesting a new satellite analysis.
- Automated tests using pytest.

## Technology Stack

- Python
- FastAPI
- Uvicorn
- Google Earth Engine
- Sentinel-2 Surface Reflectance Harmonized
- Pandas
- NumPy
- Pydantic
- Pytest

## Project Structure

```text
EcoPredict/
├── data/
│   ├── raw/
│   └── processed/
│       └── ndvi_change.csv
├── docs/
├── scripts/
│   └── earthengine_setup.py
├── src/
│   └── ecopredict/
│       ├── __init__.py
│       ├── main.py
│       ├── satellite.py
│       └── validation.py
├── tests/
│   ├── test_api.py
│   └── test_validation.py
├── .gitignore
├── README.md
├── requirements.txt
└── requirements-lock.txt
```

## Installation

Clone the repository:

```bash
git clone https://github.com/Aditya-Dwivedi11/EcoPredict.git
cd EcoPredict
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Google Earth Engine Configuration

EcoPredict requires an authenticated Google Earth Engine account and a registered Google Cloud project.

Set your project ID:

```bash
export EE_PROJECT_ID="YOUR_GOOGLE_CLOUD_PROJECT_ID"
```

Authenticate using the project's setup script:

```bash
PYTHONPATH=src python scripts/earthengine_setup.py
```

Do not commit authentication credentials, access tokens, or secret configuration files to GitHub.

## Run Satellite Analysis

The default analysis uses an illustrative Kanpur-area bounding box.

Run:

```bash
PYTHONPATH=src python -m ecopredict.satellite
```

You can provide a custom bounding box and date periods:

```bash
PYTHONPATH=src python -m ecopredict.satellite \
  --west 80.20 \
  --south 26.38 \
  --east 80.45 \
  --north 26.55 \
  --before-start 2024-10-01 \
  --before-end 2024-11-01 \
  --after-start 2025-10-01 \
  --after-end 2025-11-01
```

Results are saved to:

```text
data/processed/ndvi_change.csv
```

## Run the API

Start the development server:

```bash
PYTHONPATH=src python -m uvicorn ecopredict.main:app --host 0.0.0.0 --port 8000
```

API documentation:

```text
/docs
```

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | Project information |
| GET | `/health` | API health status |
| GET | `/api/v1/ndvi-analysis` | Retrieve saved NDVI analysis |
| POST | `/api/v1/ndvi-analysis` | Run analysis for supplied coordinates and periods |

The POST endpoint accepts west, south, east and north coordinates, together with before and after date ranges.

## Run Tests

Run the test suite:

```bash
PYTHONPATH=src pytest -q
```

## Understanding NDVI

NDVI is calculated using near-infrared and red reflectance:

\[
NDVI = \frac{NIR - Red}{NIR + Red}
\]

NDVI values generally range from -1 to +1.

A change in NDVI can indicate a change in vegetation greenness. It does not, by itself, establish the cause of the change or confirm an environmental hazard.

## Current Limitations

- The default geographical area is illustrative and must be replaced with the intended study area.
- Analysis currently compares two time periods.
- Results are summary statistics rather than detailed pixel-level maps.
- The current CSV output stores the latest analysis rather than maintaining a historical database.
- NDVI alone is not a complete environmental hazard prediction model.

## Project Status

EcoPredict currently has a working satellite-analysis module, a FastAPI backend, and automated validation and API tests.

Further development can extend the project with additional satellite-derived indicators, environmental risk assessment, geospatial visualization, and predictive modelling.
