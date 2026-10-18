"""Tests for system tray and app icon management in mycat.tray."""

from unittest.mock import MagicMock, patch

from PySide6 import QtGui, QtWidgets

from mycat import main, tray


def test_tray_exports():
    assert tray.__all__ == ["make_app_icon", "setup_tray"]
    assert main.make_app_icon is tray.make_app_icon
    assert main.setup_tray is tray.setup_tray


def test_make_app_icon(qapp):
    icon = tray.make_app_icon()
    assert isinstance(icon, QtGui.QIcon)
    assert not icon.isNull()
    pixmap = icon.pixmap(64, 64)
    assert not pixmap.isNull()
    assert pixmap.width() == 64
    assert pixmap.height() == 64


def test_setup_tray_when_unavailable(qapp):
    with patch.object(QtWidgets.QSystemTrayIcon, "isSystemTrayAvailable", return_value=False):
        window = MagicMock()
        result = tray.setup_tray(qapp, window, None)
        assert result is None


def test_setup_tray_when_available(qapp):
    with patch.object(QtWidgets.QSystemTrayIcon, "isSystemTrayAvailable", return_value=True):
        window = QtWidgets.QWidget()
        window._open_reminder = MagicMock()
        window.open_llm_settings = MagicMock()
        window._open_settings = MagicMock()
        window._reset_position = MagicMock()
        window._toggle_llm_chat = MagicMock()

        custom_pixmap = QtGui.QPixmap(32, 32)
        custom_pixmap.fill()

        tray_icon = tray.setup_tray(qapp, window, custom_pixmap)
        assert isinstance(tray_icon, QtWidgets.QSystemTrayIcon)
        assert tray_icon.toolTip() == "mycat 🐱"
        menu = tray_icon.contextMenu()
        assert menu is not None
        actions = [a.text() for a in menu.actions()]
        assert "Chat" in actions
        assert "Reminder…" in actions
        assert "LLM…" in actions
        assert "Settings…" in actions
        assert "Reset Position" in actions
        assert "Quit" in actions
