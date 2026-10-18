"""System tray icon and application icon management."""

from PySide6 import QtCore, QtGui, QtWidgets

try:
    from . import autostart
except ImportError:
    import autostart

__all__ = ["make_app_icon", "setup_tray"]


def make_app_icon() -> QtGui.QIcon:
    """A 😽 cat icon, used for the tray, the app icon and the splash."""
    pixmap = QtGui.QPixmap(64, 64)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    font = QtGui.QFont()
    font.setPointSize(40)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, "😽")
    painter.end()
    return QtGui.QIcon(pixmap)


def setup_tray(app, window, icon_pixmap):
    """A persistent cat icon in the system tray with a quick-action menu.

    Returns the tray icon (kept alive by the caller), or None when no system
    tray is available.
    """
    if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
        return None
    icon = QtGui.QIcon(icon_pixmap) if icon_pixmap and not icon_pixmap.isNull() else make_app_icon()
    tray = QtWidgets.QSystemTrayIcon(icon, app)
    tray.setToolTip("mycat 🐱")

    menu = QtWidgets.QMenu(window)
    toggle_chat = getattr(window, "_toggle_llm_chat", None)
    if callable(toggle_chat):
        menu.addAction("Chat", toggle_chat)
    menu.addAction("Reminder…", window._open_reminder)
    menu.addAction("LLM…", window.open_llm_settings)
    if autostart.is_supported():
        menu.addSeparator()
        login_action = menu.addAction("Autostart")
        login_action.setCheckable(True)
        login_action.setChecked(autostart.is_enabled())
        login_action.toggled.connect(autostart.set_enabled)
    menu.addSeparator()
    menu.addAction("Settings…", window._open_settings)
    menu.addAction("Reset Position", window._reset_position)
    menu.addAction("Quit", QtWidgets.QApplication.quit)
    tray.setContextMenu(menu)

    def on_activated(reason):
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick:
            window.show()
            window.raise_()

    tray.activated.connect(on_activated)
    tray.show()
    return tray
