
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from ecopredict.main import app

client = TestClient(app)


def valid_analysis_request():
    return {
        "west": 80.20,
        "south": 26.38,
        "east": 80.45,
        "north": 26.55,
        "before_start": "2024-10-01",
        "before_end": "2024-11-01",
        "after_start": "2025-10-01",
        "after_end": "2025-11-01",
    }


def test_root_endpoint():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["project"] == "EcoPredict"


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_ndvi_get_endpoint_returns_404_when_file_missing(
    monkeypatch,
    tmp_path,
):
    import ecopredict.main as main

    missing_file = tmp_path / "missing.csv"

    monkeypatch.setattr(
        main,
        "NDVI_RESULTS_FILE",
        missing_file,
    )

    response = client.get("/api/v1/ndvi-analysis")

    assert response.status_code == 404
    assert "No satellite analysis results found" in (
        response.json()["detail"]
    )


def test_ndvi_get_endpoint_returns_saved_results(
    monkeypatch,
    tmp_path,
):
    import ecopredict.main as main

    results_file = tmp_path / "ndvi_change.csv"

    pd.DataFrame(
        [
            {
                "start_date": "2024-10-01",
                "end_date": "2024-11-01",
                "mean_ndvi": 0.43,
                "status": "ok",
            }
        ]
    ).to_csv(results_file, index=False)

    monkeypatch.setattr(
        main,
        "NDVI_RESULTS_FILE",
        results_file,
    )

    response = client.get("/api/v1/ndvi-analysis")

    assert response.status_code == 200
    assert response.json()["record_count"] == 1
    assert response.json()["results"][0]["mean_ndvi"] == 0.43


def test_ndvi_post_rejects_invalid_longitude():
    payload = valid_analysis_request()
    payload["west"] = 200

    response = client.post(
        "/api/v1/ndvi-analysis",
        json=payload,
    )

    assert response.status_code == 422


def test_ndvi_post_rejects_invalid_latitude():
    payload = valid_analysis_request()
    payload["north"] = 95

    response = client.post(
        "/api/v1/ndvi-analysis",
        json=payload,
    )

    assert response.status_code == 422


def test_ndvi_post_rejects_invalid_date_range():
    payload = valid_analysis_request()
    payload["before_start"] = "2024-11-01"
    payload["before_end"] = "2024-10-01"

    response = client.post(
        "/api/v1/ndvi-analysis",
        json=payload,
    )

    assert response.status_code == 422


def test_ndvi_post_rejects_overlapping_periods():
    payload = valid_analysis_request()
    payload["after_start"] = "2024-10-20"
    payload["after_end"] = "2024-12-01"

    response = client.post(
        "/api/v1/ndvi-analysis",
        json=payload,
    )

    assert response.status_code == 422


def test_ndvi_post_rejects_missing_fields():
    payload = valid_analysis_request()
    del payload["before_start"]

    response = client.post(
        "/api/v1/ndvi-analysis",
        json=payload,
    )

    assert response.status_code == 422


@patch("ecopredict.main.run_analysis")
@patch("ecopredict.main.initialize_earth_engine")
def test_ndvi_post_runs_analysis(
    mock_initialize,
    mock_run_analysis,
    tmp_path,
    monkeypatch,
):
    import ecopredict.main as main

    output_file = tmp_path / "ndvi_change.csv"
    raster_directory = tmp_path / "rasters"

    monkeypatch.setattr(
        main,
        "NDVI_RESULTS_FILE",
        output_file,
    )

    monkeypatch.setattr(
        main,
        "RASTER_DIRECTORY",
        raster_directory,
    )

    # Mock raster export to avoid real Earth Engine requests.
    exported_files = [
        raster_directory / "ndvi_before.tif",
        raster_directory / "ndvi_after.tif",
        raster_directory / "ndvi_difference.tif",
        raster_directory / "metadata.json",
    ]

    monkeypatch.setattr(
        main,
        "export_ndvi_rasters",
        lambda **kwargs: exported_files,
    )

    def fake_analysis(bounds, periods, output_path):
        pd.DataFrame(
            [
                {
                    "start_date": "2024-10-01",
                    "end_date": "2024-11-01",
                    "mean_ndvi": 0.43,
                    "status": "ok",
                },
                {
                    "start_date": "2025-10-01",
                    "end_date": "2025-11-01",
                    "mean_ndvi": 0.41,
                    "status": "ok",
                },
            ]
        ).to_csv(output_path, index=False)

    mock_run_analysis.side_effect = fake_analysis

    response = client.post(
        "/api/v1/ndvi-analysis",
        json=valid_analysis_request(),
    )

    assert response.status_code == 200

    response_data = response.json()

    assert response_data["message"] == (
        "Satellite analysis and raster export completed."
    )

    assert response_data["record_count"] == 2

    assert response_data["raster_export"]["status"] == "completed"

    assert response_data["raster_export"]["layers"] == [
        "before",
        "after",
        "difference",
    ]

    assert response_data["raster_export"]["files"] == [
        "ndvi_before.tif",
        "ndvi_after.tif",
        "ndvi_difference.tif",
        "metadata.json",
    ]

    mock_initialize.assert_called_once()
    mock_run_analysis.assert_called_once()


@patch(
    "ecopredict.main.initialize_earth_engine",
    side_effect=RuntimeError("Earth Engine unavailable"),
)
def test_ndvi_post_handles_earth_engine_failure(
    mock_initialize,
):
    response = client.post(
        "/api/v1/ndvi-analysis",
        json=valid_analysis_request(),
    )

    assert response.status_code == 502

    assert "Satellite analysis could not be completed" in (
        response.json()["detail"]
    )

    mock_initialize.assert_called_once()
