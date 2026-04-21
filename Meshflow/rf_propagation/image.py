"""GeoTIFF bytes to PNG bytes (+ true bounds).

We deliberately avoid ``rasterio``/GDAL \u2014 the engine already emits the
GeoTIFF in EPSG:4326 with the payload we asked for, so the only thing we
need to do on the API side is re-encode to a PNG the browser can draw
inside a Leaflet ``imageOverlay``. Pillow handles this for baseline TIFFs;
for oddball SPLAT!/tifffile variants we fall back to ``tifffile``.

We also read the GeoTIFF's georeferencing metadata (``ModelTiepointTag``
+ ``ModelPixelScaleTag``) to recover the true lat/lng bounds that the
engine actually rendered into. The request ``radius`` is only a hint;
SPLAT! snaps the output to its SRTM tile grid and the resulting KML
``LatLonBox`` can differ from our naive ``\u00b1radius/111320\u00b0`` bbox.
Using the GeoTIFF-embedded bounds is the only way to line the PNG up on
the map correctly.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from io import BytesIO

from .bounds import Bbox

logger = logging.getLogger(__name__)

# GeoTIFF tag IDs (see https://www.awaresystems.be/imaging/tiff/tifftags/modeltiepointtag.html).
_TAG_MODEL_TIEPOINT = 33922
_TAG_MODEL_PIXEL_SCALE = 33550


class TiffDecodeError(RuntimeError):
    """Raised when neither Pillow nor tifffile can decode the engine output."""


@dataclass(frozen=True)
class RenderImage:
    """PNG bytes for the browser + the true GeoTIFF bounds (if recoverable)."""

    png_bytes: bytes
    bounds: Bbox | None


def geotiff_bytes_to_png(tiff_bytes: bytes) -> bytes:
    """Convert a GeoTIFF byte blob into a PNG byte blob (RGBA).

    Kept for call sites that only need the PNG; prefer
    :func:`geotiff_to_render_image` when bounds are also required.
    """

    return geotiff_to_render_image(tiff_bytes).png_bytes


def geotiff_to_render_image(tiff_bytes: bytes) -> RenderImage:
    """Decode a GeoTIFF into (RGBA PNG bytes, bounds)."""

    if not tiff_bytes:
        raise TiffDecodeError("engine returned empty GeoTIFF bytes")

    try:
        return _pillow_convert(tiff_bytes)
    except Exception as exc:  # noqa: BLE001 \u2014 fallback path is the whole point
        logger.warning("rf_propagation.image: Pillow failed (%s); trying tifffile", exc)

    try:
        return _tifffile_convert(tiff_bytes)
    except Exception as exc:  # noqa: BLE001
        raise TiffDecodeError(f"could not decode GeoTIFF: {exc}") from exc


def _apply_nodata_alpha(img):
    """Set alpha to 0 for pixels within tolerance of the configured nodata RGB."""
    from django.conf import settings

    import numpy as np
    from PIL import Image

    if img.mode != "RGBA":
        img = img.convert("RGBA")
    nodata = settings.RF_PROPAGATION_NODATA_RGB
    tol = int(settings.RF_PROPAGATION_NODATA_TOLERANCE)
    r0, g0, b0 = (int(nodata[0]), int(nodata[1]), int(nodata[2]))
    arr = np.asarray(img, dtype=np.uint8)
    r = arr[:, :, 0].astype(np.int16)
    g = arr[:, :, 1].astype(np.int16)
    b = arr[:, :, 2].astype(np.int16)
    mask = (np.abs(r - r0) <= tol) & (np.abs(g - g0) <= tol) & (np.abs(b - b0) <= tol)
    out = arr.copy()
    out[mask, 3] = 0
    return Image.fromarray(out, mode="RGBA")


def _png_bytes_from_rgba(img) -> bytes:
    buf = BytesIO()
    _apply_nodata_alpha(img).save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _maybe_resample_pixel_aspect_for_web_mercator(img, bounds: Bbox | None, width: int, height: int):
    """Resample raster pixels so width/height matches Mercator screen aspect at bbox centre.

    SPLAT!/Site Planner tend to emit equal pixels-per-degree along lat/lng; Leaflet maps
    the PNG onto EPSG:4326 bounds using Web Mercator where horizontal scale varies with
    ``cos(latitude)``. Reconditioning pixel aspect avoids vertically squashed overlays.
    """

    from PIL import Image

    if bounds is None:
        return img
    lat_span = bounds.north - bounds.south
    lng_span = bounds.east - bounds.west
    if lat_span <= 0 or lng_span <= 0:
        return img
    lat_c = (bounds.north + bounds.south) / 2.0
    earth_aspect = (lng_span * math.cos(math.radians(lat_c))) / lat_span
    current_aspect = width / height
    rel_diff = abs(earth_aspect - current_aspect) / current_aspect if current_aspect else 0.0
    if rel_diff <= 0.02:
        return img

    try:
        resample = Image.Resampling.BILINEAR
    except AttributeError:
        resample = Image.BILINEAR

    if earth_aspect > current_aspect:
        new_w = max(1, int(round(height * earth_aspect)))
        new_h = height
    else:
        new_w = width
        new_h = max(1, int(round(width / earth_aspect)))
    return img.resize((new_w, new_h), resample)


def _pillow_convert(tiff_bytes: bytes) -> RenderImage:
    from PIL import Image  # local import so test runners without Pillow can skip

    with Image.open(BytesIO(tiff_bytes)) as img:
        img.load()
        width, height = img.size
        bounds = _bounds_from_pillow_tags(img, width, height)
        pil_img = img.convert("RGBA") if img.mode != "RGBA" else img.copy()
        pil_img = _maybe_resample_pixel_aspect_for_web_mercator(pil_img, bounds, width, height)

    return RenderImage(png_bytes=_png_bytes_from_rgba(pil_img), bounds=bounds)


def _tifffile_convert(tiff_bytes: bytes) -> RenderImage:
    import numpy as np
    import tifffile
    from PIL import Image

    with tifffile.TiffFile(BytesIO(tiff_bytes)) as tif:
        page = tif.pages[0]
        arr = page.asarray()
        height = int(page.shape[0])
        width = int(page.shape[1])
        bounds = _bounds_from_tifffile_tags(page, width, height)

    if arr.ndim == 2:
        img = Image.fromarray(arr).convert("RGBA")
    elif arr.ndim == 3 and arr.shape[2] in (3, 4):
        mode = "RGBA" if arr.shape[2] == 4 else "RGB"
        img = Image.fromarray(np.asarray(arr, dtype=arr.dtype), mode=mode).convert("RGBA")
    else:
        raise TiffDecodeError(f"unexpected TIFF shape: {arr.shape}")

    img = _maybe_resample_pixel_aspect_for_web_mercator(img, bounds, width, height)

    return RenderImage(png_bytes=_png_bytes_from_rgba(img), bounds=bounds)


def _bounds_from_pillow_tags(img, width: int, height: int) -> Bbox | None:
    """Extract bounds from Pillow's ``tag_v2`` (TIFF 6.0 + GeoTIFF tags)."""

    tag_v2 = getattr(img, "tag_v2", None)
    if tag_v2 is None:
        return None
    tiepoint = tag_v2.get(_TAG_MODEL_TIEPOINT)
    pixel_scale = tag_v2.get(_TAG_MODEL_PIXEL_SCALE)
    return _bounds_from_georef(tiepoint, pixel_scale, width, height)


def _bounds_from_tifffile_tags(page, width: int, height: int) -> Bbox | None:
    """Extract bounds from a ``tifffile`` page's ``tags`` collection."""

    tags = getattr(page, "tags", None)
    if tags is None:
        return None

    def _value(name: str, tag_id: int):
        # tifffile indexes by both name and id; try both defensively.
        entry = tags.get(name) if hasattr(tags, "get") else None
        if entry is None and hasattr(tags, "get"):
            entry = tags.get(tag_id)
        return getattr(entry, "value", None) if entry is not None else None

    tiepoint = _value("ModelTiepointTag", _TAG_MODEL_TIEPOINT)
    pixel_scale = _value("ModelPixelScaleTag", _TAG_MODEL_PIXEL_SCALE)
    return _bounds_from_georef(tiepoint, pixel_scale, width, height)


def _bounds_from_georef(tiepoint, pixel_scale, width: int, height: int) -> Bbox | None:
    """Compute a ``Bbox`` from raw GeoTIFF tag values.

    ``ModelTiepointTag`` is ``[I, J, K, X, Y, Z]`` mapping raster pixel
    ``(I, J)`` to world coord ``(X, Y)``. For the common ``north-up`` /
    SPLAT! case ``(I, J)`` is ``(0, 0)`` so ``(X, Y)`` is the north-west
    corner in degrees.

    ``ModelPixelScaleTag`` is ``[scale_x, scale_y, scale_z]`` in world
    units per pixel; ``scale_y`` is given as a positive value even though
    the raster's Y axis grows downward.

    Returns ``None`` if either tag is absent or the values don't look
    like a valid WGS84 bbox (caller falls back to ``bbox_from_center``).
    """

    if tiepoint is None or pixel_scale is None:
        return None
    try:
        tp = list(tiepoint)
        ps = list(pixel_scale)
        if len(tp) < 6 or len(ps) < 2:
            return None
        i, j = float(tp[0]), float(tp[1])
        tx, ty = float(tp[3]), float(tp[4])
        sx, sy = float(ps[0]), float(ps[1])
    except (TypeError, ValueError) as exc:
        logger.warning("rf_propagation.image: bad georef tag values (%s)", exc)
        return None

    if sx <= 0 or sy <= 0 or width <= 0 or height <= 0:
        return None

    # World coords at raster origin (pixel 0,0), adjusting if the tiepoint
    # is not at the origin. SPLAT! always emits (0,0) but we stay generic.
    west = tx - i * sx
    north = ty + j * sy
    east = west + width * sx
    south = north - height * sy

    if not (-180.0 <= west < east <= 180.0):
        logger.warning(
            "rf_propagation.image: bounds lng out of range west=%.6f east=%.6f",
            west,
            east,
        )
        return None
    if not (-90.0 <= south < north <= 90.0):
        logger.warning(
            "rf_propagation.image: bounds lat out of range south=%.6f north=%.6f",
            south,
            north,
        )
        return None

    return Bbox(west=west, south=south, east=east, north=north)
