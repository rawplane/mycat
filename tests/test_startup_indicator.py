"""Tests for the app icon helper used for the taskbar entry."""

from mycat import main


def test_app_icon_not_null(qapp):
    icon = main.make_app_icon()
    assert not icon.isNull()
    assert not icon.pixmap(64, 64).isNull()


def test_gif_delay_fallback_empty():
    from mycat.cat_image import parse_gif_frame_delays
    assert parse_gif_frame_delays(b"not-a-gif") == []
