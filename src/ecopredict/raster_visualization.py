
"""Render satellite-derived NDVI GeoTIFFs as geographic PNG overlays."""

from io import BytesIO
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.warp import transform_bounds


NODATA_VALUE = -9999.0
SUPPORTED_LAYERS = {"before", "after", "difference"}

RASTER_FILES = {
    "before": "ndvi_before.tif",
    "after": "ndvi_after.tif",
    "difference": "ndvi_difference.tif",
}


def get_raster_path(layer, raster_dir):
    """Resolve a supported raster layer to its file path."""

    if layer not in SUPPORTED_LAYERS:
        raise ValueError(
            f"Unsupported layer: {layer}. "
            f"Choose from {sorted(SUPPORTED_LAYERS)}."
        )

    return Path(raster_dir) / RASTER_FILES[layer]


def get_raster_metadata(layer, raster_dir):
    """Return raster dimensions, geographic bounds and statistics."""

    path = get_raster_path(layer, raster_dir)

    if not path.is_file():
        raise FileNotFoundError(f"Raster not found: {path.name}")

    with rasterio.open(path) as src:
        if src.crs is None:
            raise ValueError("Raster has no coordinate reference system.")

        data = src.read(1, masked=True)
        valid = data.compressed()

        if valid.size == 0:
            raise ValueError("Raster contains no valid pixels.")

        west, south, east, north = transform_bounds(
            src.crs,
            "EPSG:4326",
            *src.bounds,
            densify_pts=21,
        )

        return {
            "layer": layer,
            "filename": path.name,
            "crs": str(src.crs),
            "width": src.width,
            "height": src.height,
            "bounds": {
                "west": west,
                "south": south,
                "east": east,
                "north": north,
            },
            "nodata": src.nodata,
            "valid_pixel_count": int(valid.size),
            "minimum": float(valid.min()),
            "maximum": float(valid.max()),
            "mean": float(valid.mean()),
        }


def _colorize(values, layer):
    """Convert raster values into RGB colours."""

    if layer == "difference":
        # Red = vegetation decrease; green = vegetation increase.
        scale = np.clip(values, -0.5, 0.5)
        normalized = (scale + 0.5) / 1.0

        red = np.clip(255 * (1 - normalized), 0, 255)
        green = np.clip(255 * normalized, 0, 255)
        blue = np.full(values.shape, 40.0)

    else:
        # NDVI colour ramp: red -> yellow -> light green -> dark green.
        positions = np.array([-1.0, -0.2, 0.0, 0.4, 1.0])

        colors = np.array([
            [165, 0, 38],
            [244, 109, 67],
            [255, 255, 191],
            [166, 217, 106],
            [0, 104, 55],
        ])

        clipped = np.clip(values, -1.0, 1.0)

        red = np.interp(clipped, positions, colors[:, 0])
        green = np.interp(clipped, positions, colors[:, 1])
        blue = np.interp(clipped, positions, colors[:, 2])

    return np.stack(
        [red, green, blue],
        axis=-1,
    ).astype(np.uint8)


def render_raster_png(layer, raster_dir):
    """Render a GeoTIFF as an RGBA PNG and return geographic bounds."""

    path = get_raster_path(layer, raster_dir)

    if not path.is_file():
        raise FileNotFoundError(f"Raster not found: {path.name}")

    with rasterio.open(path) as src:
        if src.crs is None:
            raise ValueError("Raster has no coordinate reference system.")

        data = src.read(1, masked=True)
        values = data.filled(0).astype(np.float32)

        valid_mask = (
            ~np.ma.getmaskarray(data)
            & np.isfinite(values)
        )

        if not np.any(valid_mask):
            raise ValueError("Raster contains no valid pixels.")

        rgb = _colorize(values, layer)

        # Transparent pixels represent NoData.
        alpha = np.where(valid_mask, 255, 0).astype(np.uint8)

        rgba = np.dstack([rgb, alpha])

        image = Image.fromarray(rgba, mode="RGBA")

        west, south, east, north = transform_bounds(
            src.crs,
            "EPSG:4326",
            *src.bounds,
            densify_pts=21,
        )

        bounds = {
            "west": west,
            "south": south,
            "east": east,
            "north": north,
        }

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)

    return buffer.getvalue(), bounds
