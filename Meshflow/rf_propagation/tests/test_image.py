"""Unit tests for :mod:`rf_propagation.image`."""

from __future__ import annotations

from io import BytesIO

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
