"""Unit tests for :mod:`rf_propagation.image`."""

from __future__ import annotations

from io import BytesIO

from django.test import override_settings

import pytest
from PIL import Image

from rf_propagation.image import TiffDecodeError, geotiff_bytes_to_png


def _synthetic_tiff_bytes(mode: str = "RGBA", size: tuple[int, int] = (8, 8)) -> bytes:
    img = Image.new(mode, size, color=(255, 128, 64, 200) if mode == "RGBA" else (255, 128, 64))
    buf = BytesIO()
    img.save(buf, format="TIFF")
    return buf.getvalue()


def test_roundtrip_rgba_tiff_to_png_produces_valid_png():
    png_bytes = geotiff_bytes_to_png(_synthetic_tiff_bytes())
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(BytesIO(png_bytes)) as img:
        assert img.format == "PNG"
        assert img.mode == "RGBA"
        assert img.size == (8, 8)


def test_converts_rgb_tiff_to_rgba_png():
    png_bytes = geotiff_bytes_to_png(_synthetic_tiff_bytes(mode="RGB"))
    with Image.open(BytesIO(png_bytes)) as img:
        assert img.mode == "RGBA"


def test_rejects_empty_payload():
    with pytest.raises(TiffDecodeError):
        geotiff_bytes_to_png(b"")


def test_rejects_unreadable_bytes():
    with pytest.raises(TiffDecodeError):
        geotiff_bytes_to_png(b"not-a-real-tiff")


def _rgb_tiff_mostly_black_with_one_red_pixel() -> bytes:
    img = Image.new("RGB", (4, 4), (0, 0, 0))
    px = img.load()
    px[3, 3] = (255, 0, 0)
    buf = BytesIO()
    img.save(buf, format="TIFF")
    return buf.getvalue()


@override_settings(RF_PROPAGATION_NODATA_RGB=(0, 0, 0), RF_PROPAGATION_NODATA_TOLERANCE=0)
def test_black_background_pixels_become_fully_transparent():
    png_bytes = geotiff_bytes_to_png(_rgb_tiff_mostly_black_with_one_red_pixel())
    with Image.open(BytesIO(png_bytes)) as img:
        assert img.mode == "RGBA"
        px = img.load()
        assert px[0, 0][3] == 0
        assert px[3, 3][3] == 255


@override_settings(RF_PROPAGATION_NODATA_RGB=(0, 0, 0), RF_PROPAGATION_NODATA_TOLERANCE=8)
def test_near_black_within_tolerance_becomes_transparent():
    img = Image.new("RGB", (2, 2), (0, 0, 0))
    px = img.load()
    px[1, 1] = (7, 0, 0)
    px[0, 1] = (20, 0, 0)
    buf = BytesIO()
    img.save(buf, format="TIFF")
    png_bytes = geotiff_bytes_to_png(buf.getvalue())
    with Image.open(BytesIO(png_bytes)) as out:
        opx = out.load()
        assert opx[1, 1][3] == 0
        assert opx[0, 1][3] == 255


@override_settings(RF_PROPAGATION_NODATA_RGB=(0, 0, 0), RF_PROPAGATION_NODATA_TOLERANCE=8)
def test_far_from_nodata_stays_opaque():
    img = Image.new("RGB", (2, 2), (0, 0, 0))
    px = img.load()
    px[0, 0] = (30, 0, 0)
    buf = BytesIO()
    img.save(buf, format="TIFF")
    png_bytes = geotiff_bytes_to_png(buf.getvalue())
    with Image.open(BytesIO(png_bytes)) as out:
        assert out.getpixel((0, 0))[3] == 255
