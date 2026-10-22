from datetime import datetime, timezone

from fastapi import FastAPI

app = FastAPI(
    title="EcoPredict API",
    description=(
        "Environmental risk intelligence using "
        "scientific and satellite-derived data."
    ),
    version="0.1.0",
)


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
