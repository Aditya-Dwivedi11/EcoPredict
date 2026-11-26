
"""Render optimized satellite-derived NDVI GeoTIFF PNG overlays."""

from functools import lru_cache
from io import BytesIO
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds


NODATA_VALUE = -9999.0

SUPPORTED_LAYERS = {
    "before",
    "after",
    "difference",
}

RASTER_FILES = {
    "before": "ndvi_before.tif",
    "after": "ndvi_after.tif",
    "difference": "ndvi_difference.tif",
}

# Maximum width or height of the web visualization.
# Original GeoTIFFs retain their full resolution.
MAX_IMAGE_DIMENSION = 1500


def get_raster_path(layer, raster_dir):
    """Resolve a supported raster layer to its file path."""

    if layer not in SUPPORTED_LAYERS:
        raise ValueError(
            f"Unsupported layer: {layer}. "
            f"Choose from {sorted(SUPPORTED_LAYERS)}."
        )

    return Path(raster_dir) / RASTER_FILES[layer]


def _get_geographic_bounds(src):
    """Convert raster bounds into WGS84 geographic coordinates."""

    if src.crs is None:
        raise ValueError(
            "Raster has no coordinate reference system."
        )

    west, south, east, north = transform_bounds(
        src.crs,
        "EPSG:4326",
        *src.bounds,
        densify_pts=21,
    )

    return {
        "west": west,
        "south": south,
        "east": east,
        "north": north,
    }


def get_raster_metadata(layer, raster_dir):
    """Return raster dimensions, geographic bounds and statistics."""

    path = get_raster_path(layer, raster_dir)

    if not path.is_file():
        raise FileNotFoundError(
            f"Raster not found: {path.name}"
        )

    with rasterio.open(path) as src:

        if src.crs is None:
            raise ValueError(
                "Raster has no coordinate reference system."
            )

        data = src.read(1, masked=True)
        valid = data.compressed()

        if valid.size == 0:
            raise ValueError(
                "Raster contains no valid pixels."
            )

        bounds = _get_geographic_bounds(src)

        return {
            "layer": layer,
            "filename": path.name,
            "crs": str(src.crs),
            "width": src.width,
            "height": src.height,
            "bounds": bounds,
            "nodata": src.nodata,
            "valid_pixel_count": int(valid.size),
            "minimum": float(valid.min()),
            "maximum": float(valid.max()),
            "mean": float(valid.mean()),
        }


def _colorize(values, layer):
    """Convert raster values into RGB colours."""

    if layer == "difference":

        # Red = vegetation decrease.
        # Green = vegetation increase.

        scale = np.clip(
            values,
            -0.5,
            0.5,
        )

        normalized = (scale + 0.5) / 1.0

        red = np.clip(
            255 * (1 - normalized),
            0,
            255,
        )

        green = np.clip(
            255 * normalized,
            0,
            255,
        )

        blue = np.full(
            values.shape,
            40.0,
        )

    else:

        # NDVI colour ramp:
        # Red -> Yellow -> Light green -> Dark green.

        positions = np.array([
            -1.0,
            -0.2,
            0.0,
            0.4,
            1.0,
        ])

        colors = np.array([
            [165, 0, 38],
            [244, 109, 67],
            [255, 255, 191],
            [166, 217, 106],
            [0, 104, 55],
        ])

        clipped = np.clip(
            values,
            -1.0,
            1.0,
        )

        red = np.interp(
            clipped,
            positions,
            colors[:, 0],
        )

        green = np.interp(
            clipped,
            positions,
            colors[:, 1],
        )

        blue = np.interp(
            clipped,
            positions,
            colors[:, 2],
        )

    return np.stack(
        [red, green, blue],
        axis=-1,
    ).astype(np.uint8)


@lru_cache(maxsize=6)
def _render_cached(
    layer,
    raster_path,
    modified_time_ns,
    file_size,
    max_dimension,
):
    """
    Render and cache a downsampled raster PNG.

    File modification time and size are part of the cache key.
    If a GeoTIFF changes, a new rendering is generated.
    """

    path = Path(raster_path)

    with rasterio.open(path) as src:

        if src.crs is None:
            raise ValueError(
                "Raster has no coordinate reference system."
            )

        # Preserve the original aspect ratio.
        scale = min(
            1.0,
            max_dimension / max(src.width, src.height),
        )

        output_width = max(
            1,
            round(src.width * scale),
        )

        output_height = max(
            1,
            round(src.height * scale),
        )

        # Read a reduced raster instead of loading full resolution.
        data = src.read(
            1,
            out_shape=(
                output_height,
                output_width,
            ),
            masked=True,
            resampling=Resampling.average,
        )

        values = data.filled(0).astype(
            np.float32
        )

        # Preserve NoData transparency.
        valid_mask = (
            ~np.ma.getmaskarray(data)
            & np.isfinite(values)
        )

        if not np.any(valid_mask):
            raise ValueError(
                "Raster contains no valid pixels."
            )

        # Generate RGB image.
        rgb = _colorize(
            values,
            layer,
        )

        # Alpha channel: 0 for NoData, 255 for valid pixels.
        alpha = np.where(
            valid_mask,
            255,
            0,
        ).astype(np.uint8)

        rgba = np.dstack([
            rgb,
            alpha,
        ])

        image = Image.fromarray(rgba)

        # Geographic bounds remain those of the original raster.
        bounds = _get_geographic_bounds(src)

    # Encode PNG.
    buffer = BytesIO()

    image.save(
        buffer,
        format="PNG",
        optimize=True,
    )

    return buffer.getvalue(), bounds


def render_raster_png(layer, raster_dir):
    """
    Return an optimized RGBA PNG and geographic bounds.

    The source GeoTIFF is never modified.
    """

    path = get_raster_path(
        layer,
        raster_dir,
    )

    if not path.is_file():
        raise FileNotFoundError(
            f"Raster not found: {path.name}"
        )

    # File information invalidates the cache when the raster changes.
    stat = path.stat()

    return _render_cached(
        layer,
        str(path.resolve()),
        stat.st_mtime_ns,
        stat.st_size,
        MAX_IMAGE_DIMENSION,
    )


def clear_raster_cache():
    """Clear cached PNG renderings."""

    _render_cached.cache_clear()
