"""GeoTIFF bytes to PNG bytes.

We deliberately avoid ``rasterio``/GDAL — the engine already emits the
GeoTIFF in EPSG:4326 with the payload we asked for, so the only thing we
need to do on the API side is re-encode to a PNG the browser can draw
inside a Leaflet ``imageOverlay``. Pillow handles this for baseline TIFFs;
for oddball SPLAT!/tifffile variants we fall back to ``tifffile``.
"""

from __future__ import annotations

import logging
from io import BytesIO

logger = logging.getLogger(__name__)


class TiffDecodeError(RuntimeError):
    """Raised when neither Pillow nor tifffile can decode the engine output."""


def geotiff_bytes_to_png(tiff_bytes: bytes) -> bytes:
    """Convert a GeoTIFF byte blob into a PNG byte blob (RGBA)."""

    if not tiff_bytes:
        raise TiffDecodeError("engine returned empty GeoTIFF bytes")

    try:
        return _pillow_convert(tiff_bytes)
    except Exception as exc:  # noqa: BLE001 — fallback path is the whole point
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


def _pillow_convert(tiff_bytes: bytes) -> bytes:
    from PIL import Image  # local import so test runners without Pillow can skip

    with Image.open(BytesIO(tiff_bytes)) as img:
        img.load()
        pil_img = img.convert("RGBA") if img.mode != "RGBA" else img.copy()
    return _png_bytes_from_rgba(pil_img)


def _tifffile_convert(tiff_bytes: bytes) -> bytes:
    import numpy as np
    import tifffile
    from PIL import Image

    arr = tifffile.imread(BytesIO(tiff_bytes))
    if arr.ndim == 2:
        img = Image.fromarray(arr).convert("RGBA")
    elif arr.ndim == 3 and arr.shape[2] in (3, 4):
        mode = "RGBA" if arr.shape[2] == 4 else "RGB"
        img = Image.fromarray(np.asarray(arr, dtype=arr.dtype), mode=mode).convert("RGBA")
    else:
        raise TiffDecodeError(f"unexpected TIFF shape: {arr.shape}")

    return _png_bytes_from_rgba(img)
