"""FastAPI application entry point."""

from fastapi import FastAPI

app = FastAPI(
    title="Geospatial Measurement API",
    description="Upload Shapefiles or KML, get area/length measurements in projected CRS",
    version="0.1.0",
)


@app.get("/health")
def health():
    """Liveness probe."""
    return {"status": "ok"}
