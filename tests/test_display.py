"""Tests for display and X11 platform logic."""

import subprocess
from unittest.mock import MagicMock

from PySide6 import QtCore, QtWidgets

import mycat.display as display
import mycat.main as main


def test_main_reexports():
    """mycat.main re-exports all functions from mycat.display."""
    for name in display.__all__:
        assert hasattr(main, name)
        assert getattr(main, name) is getattr(display, name)


def test_usable_screen_rect_returns_qrect(qapp):
    """usable_screen_rect returns a valid QtCore.QRect in headless/offscreen env."""
    rect = display.usable_screen_rect()
    assert isinstance(rect, QtCore.QRect)


def test_usable_screen_rect_fallback(monkeypatch):
    """Fallback to x11_screen_size and (0,0,0,0) when Qt primaryScreen is empty."""
    monkeypatch.setattr(QtWidgets.QApplication, "primaryScreen", staticmethod(lambda: None))
    monkeypatch.setattr(display, "x11_screen_size", lambda: (1920, 1080))
    rect = display.usable_screen_rect()
    assert rect == QtCore.QRect(0, 0, 1920, 1080)

    monkeypatch.setattr(display, "x11_screen_size", lambda: None)
    rect_empty = display.usable_screen_rect()
    assert rect_empty == QtCore.QRect(0, 0, 0, 0)


def test_x11_compositor_active_platforms(monkeypatch):
    """x11_compositor_active returns None on non-X11 platforms or missing DISPLAY."""
    monkeypatch.setattr("sys.platform", "win32")
    assert display.x11_compositor_active() is None

    monkeypatch.setattr("sys.platform", "darwin")
    assert display.x11_compositor_active() is None

    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    assert display.x11_compositor_active() is None


def test_x11_compositor_active_no_libx11(monkeypatch):
    """x11_compositor_active handles missing libX11.so.6 gracefully."""
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr("ctypes.CDLL", MagicMock(side_effect=OSError("not found")))
    assert display.x11_compositor_active() is None


def test_x11_screen_size_platforms(monkeypatch):
    """x11_screen_size returns None on non-X11 platforms or missing DISPLAY."""
    monkeypatch.setattr("sys.platform", "win32")
    assert display.x11_screen_size() is None

    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    assert display.x11_screen_size() is None


def test_x11_screen_size_no_libx11(monkeypatch):
    """x11_screen_size handles missing libX11.so.6 gracefully."""
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr("ctypes.CDLL", MagicMock(side_effect=OSError("not found")))
    assert display.x11_screen_size() is None


def test_randr_monitor_count(monkeypatch):
    """randr_monitor_count parses xrandr output or handles missing tool."""
    monkeypatch.setattr("shutil.which", lambda _: None)
    assert display.randr_monitor_count() is None

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/xrandr")
    output = "Monitors: 2\n 0: +*eDP-1 1920/344x1080/194+0+0\n 1: +HDMI-1 1920/527x1080/296+1920+0\n"
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(a[0], 0, stdout=output, stderr=""),
    )
    assert display.randr_monitor_count() == 2

    monkeypatch.setattr(
        subprocess,
        "run",
        MagicMock(side_effect=subprocess.SubprocessError("timeout")),
    )
    assert display.randr_monitor_count() is None


def test_ensure_virtual_monitor(monkeypatch):
    """ensure_virtual_monitor registers virtual monitor when count is 0 and size known."""
    # Guard: offscreen platform skips
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    display.ensure_virtual_monitor()

    # Active run
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setattr(display, "randr_monitor_count", lambda: 0)
    monkeypatch.setattr(display, "x11_screen_size", lambda: (1920, 1080))
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/xrandr")

    calls = []

    def mock_run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_run)
    display.ensure_virtual_monitor()
    assert len(calls) == 1
    assert calls[0][0] == "/usr/bin/xrandr"
    assert calls[0][1] == "--setmonitor"
    assert calls[0][2] == "mycat-virtual"
