"""Unit tests for :mod:`rf_propagation.image`."""

from __future__ import annotations

from io import BytesIO

from django.test import override_settings

import pytest
from PIL import Image

from rf_propagation.image import TiffDecodeError, geotiff_bytes_to_png, geotiff_to_render_image


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


def _georeferenced_tiff_bytes(
    *,
    size: tuple[int, int] = (10, 5),
    tiepoint: tuple[float, float, float, float, float, float] = (
        0.0,
        0.0,
        0.0,
        -5.0,
        56.0,
        0.0,
    ),
    pixel_scale: tuple[float, float, float] = (0.1, 0.2, 0.0),
) -> bytes:
    img = Image.new("RGBA", size, color=(10, 20, 30, 255))
    buf = BytesIO()
    img.save(
        buf,
        format="TIFF",
        tiffinfo={33922: tiepoint, 33550: pixel_scale},
    )
    return buf.getvalue()


def test_extracts_bounds_from_pillow_geotiff_tags():
    result = geotiff_to_render_image(_georeferenced_tiff_bytes())
    assert result.bounds is not None
    # west = tiepoint.X - I*scale_x = -5.0; east = west + width*scale_x
    assert result.bounds.west == pytest.approx(-5.0)
    assert result.bounds.east == pytest.approx(-4.0)
    # north = tiepoint.Y = 56.0; south = north - height*scale_y
    assert result.bounds.north == pytest.approx(56.0)
    assert result.bounds.south == pytest.approx(55.0)


def test_extracts_bounds_with_nonzero_tiepoint_pixel():
    """SPLAT! uses (0,0) but the maths must still work for other tiepoints."""
    result = geotiff_to_render_image(
        _georeferenced_tiff_bytes(
            size=(4, 3),
            tiepoint=(1.0, 1.0, 0.0, -3.0, 52.0, 0.0),
            pixel_scale=(0.5, 0.25, 0.0),
        )
    )
    assert result.bounds is not None
    assert result.bounds.west == pytest.approx(-3.5)
    assert result.bounds.east == pytest.approx(-1.5)
    assert result.bounds.north == pytest.approx(52.25)
    assert result.bounds.south == pytest.approx(51.5)


def test_returns_none_bounds_when_georef_tags_absent():
    result = geotiff_to_render_image(_synthetic_tiff_bytes())
    assert result.bounds is None
    assert result.png_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_ignores_bounds_outside_valid_lat_lng_range():
    tiff = _georeferenced_tiff_bytes(
        tiepoint=(0.0, 0.0, 0.0, -200.0, 95.0, 0.0),
        pixel_scale=(0.1, 0.2, 0.0),
    )
    result = geotiff_to_render_image(tiff)
    assert result.bounds is None


def test_resamples_pixel_aspect_for_web_mercator():
    """SPLAT-style equal pixels-per-degree yields a wide raster; rescale toward Mercator aspect."""
    buf = BytesIO()
    img = Image.new("RGBA", (240, 120), color=(128, 128, 128, 255))
    img.save(
        buf,
        format="TIFF",
        tiffinfo={
            33922: (0.0, 0.0, 0.0, -5.0, 60.5, 0.0),
            33550: (2.0 / 240.0, 1.0 / 120.0, 0.0),
        },
    )
    result = geotiff_to_render_image(buf.getvalue())
    assert result.bounds is not None
    with Image.open(BytesIO(result.png_bytes)) as out:
        assert out.size[0] == pytest.approx(240, abs=2)
        assert out.size[1] == pytest.approx(240, abs=2)


def test_aspect_correction_skips_near_square_equatorial_case():
    buf = BytesIO()
    img = Image.new("RGBA", (100, 100), color=(128, 128, 128, 255))
    img.save(
        buf,
        format="TIFF",
        tiffinfo={
            33922: (0.0, 0.0, 0.0, -10.0, 0.5, 0.0),
            33550: (1.0 / 100.0, 1.0 / 100.0, 0.0),
        },
    )
    result = geotiff_to_render_image(buf.getvalue())
    assert result.bounds is not None
    with Image.open(BytesIO(result.png_bytes)) as out:
        assert out.size == (100, 100)
