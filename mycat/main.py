#!/usr/bin/env python3
"""
Pixel Cat with GIF animation from ZIP archives, PySide6 transparent overlay
- Shows first frame of GIF from ZIP for 5 seconds, then plays GIF once, then back to first frame
- Shows a frameless, draggable, always-on-top transparent window.
- Right click → Quit.

Dependencies:
pip install PySide6
"""

import argparse
import logging
import os
import signal
import sys
import warnings
import zipfile
from pathlib import Path

# Allow running both as `python -m mycat` and `python mycat/main.py`
if __package__:
    from . import autostart, display, llm, reminder, secret_store, skin_catalog
    from .app_config import (
        CFG_DIR,
        CFG_FILE,
        DEFAULT_POSITION_OFFSET_X,
        DEFAULT_POSITION_OFFSET_Y,
        load_config,
        load_image_from_ini,
        load_wait_time_from_ini,
        read_config,
        save_config,
        save_image_to_ini,
        secure_write_config,
    )
    from .cat_image import (
        get_gif_duration,
        load_packaged_images,
        movie_from_gif_bytes,
        parse_gif_frame_delays,
        scale_pixmap_if_needed,
    )
    from .display import (
        ensure_virtual_monitor,
        randr_monitor_count,
        usable_screen_rect,
        x11_compositor_active,
        x11_screen_size,
    )
    from .tray import make_app_icon, setup_tray
else:
    import importlib
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    llm = importlib.import_module("mycat.llm")
    skin_catalog = importlib.import_module("mycat.skin_catalog")
    reminder = importlib.import_module("mycat.reminder")
    secret_store = importlib.import_module("mycat.secret_store")
    autostart = importlib.import_module("mycat.autostart")
    app_config = importlib.import_module("mycat.app_config")
    CFG_DIR = app_config.CFG_DIR
    CFG_FILE = app_config.CFG_FILE
    DEFAULT_POSITION_OFFSET_X = app_config.DEFAULT_POSITION_OFFSET_X
    DEFAULT_POSITION_OFFSET_Y = app_config.DEFAULT_POSITION_OFFSET_Y
    load_config = app_config.load_config
    load_image_from_ini = app_config.load_image_from_ini
    load_wait_time_from_ini = app_config.load_wait_time_from_ini
    read_config = app_config.read_config
    save_config = app_config.save_config
    save_image_to_ini = app_config.save_image_to_ini
    secure_write_config = app_config.secure_write_config
    cat_image = importlib.import_module("mycat.cat_image")
    get_gif_duration = cat_image.get_gif_duration
    load_packaged_images = cat_image.load_packaged_images
    movie_from_gif_bytes = cat_image.movie_from_gif_bytes
    parse_gif_frame_delays = cat_image.parse_gif_frame_delays
    scale_pixmap_if_needed = cat_image.scale_pixmap_if_needed
    display = importlib.import_module("mycat.display")
    ensure_virtual_monitor = display.ensure_virtual_monitor
    randr_monitor_count = display.randr_monitor_count
    usable_screen_rect = display.usable_screen_rect
    x11_compositor_active = display.x11_compositor_active
    x11_screen_size = display.x11_screen_size
    tray = importlib.import_module("mycat.tray")
    make_app_icon = tray.make_app_icon
    setup_tray = tray.setup_tray

from PySide6 import QtCore, QtGui, QtWidgets

# Make logs readable for non-ASCII text (Cyrillic, emoji): force UTF-8 on the
# console streams when the locale left them as ASCII (otherwise the logger
# escapes e.g. "Ты" to "Ты").
for console_stream in (sys.stdout, sys.stderr):
    try:
        console_stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# Configure logging
LOGGING = {
    "handlers": [logging.StreamHandler()],
    "format": "%(asctime)s.%(msecs)03d [%(levelname)s]: (%(name)s) %(message)s",
    "level": logging.INFO,
    "datefmt": "%Y-%m-%d %H:%M:%S",
}
logging.basicConfig(**LOGGING)
logger = logging.getLogger(__name__)
logger.debug("LLM integration module path: %s", getattr(llm, "__file__", "builtin"))

# Image scaling settings
IMAGE_WIDTH_MAX = 300  # Maximum width for images in pixels (images will be scaled down if larger)
IMAGE_HEIGHT_MAX = 500  # Maximum height for images in pixels (images will be scaled down if larger)
STATIC_TIME = 5.0  # Seconds to show static first frame before playing GIF

# Window position settings
# (DEFAULT_POSITION_OFFSET_X and DEFAULT_POSITION_OFFSET_Y imported from app_config)


def scan_images_directory() -> list[str]:
    """Return sorted unique skin ids from bundled + user-installed locations."""
    return skin_catalog.scan_all()


class PixelCatWindow(QtWidgets.QWidget):
    """Main cat window widget with PNG/GIF animation and dragging."""
    
    def __init__(
        self,
        png_pixmap: QtGui.QPixmap,
        gif_movie: QtGui.QMovie,
        wait_time: float,
        file_name: str = "cat",
        available_images: list[str] = None,
        gif_data: bytes = b"",
    ) -> None:
        platform_name = ""
        app_instance = QtWidgets.QApplication.instance()
        if app_instance is not None:
            platform_name = (app_instance.platformName() or "").lower()
        
        # Window flags for transparent, frameless, always-on-top window
        # Qt.Window (not Qt.Tool) so the cat gets an entry in the taskbar /
        # program list at startup — Tool windows are hidden from it.
        flags = (
            QtCore.Qt.WindowType.FramelessWindowHint |
            QtCore.Qt.WindowType.Window
        )
        if platform_name != "offscreen":
            flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)

        # Setup transparency
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("mycat")
        self.setWindowIcon(make_app_icon())
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        # On X11 without a compositor, per-pixel alpha renders as a black box.
        # Fall back to clipping the window to the image silhouette (setMask) so
        # transparency works without a compositor — important for remote desktops
        # where enabling compositing adds noticeable latency. Edges are hard
        # (1-bit), which suits the pixel-art cat. MYCAT_SHAPE_MASK=1/0 forces it.
        self.shape_mask_key = None
        force_mask = os.environ.get("MYCAT_SHAPE_MASK")
        if force_mask in ("0", "1"):
            self.shape_mask_enabled = force_mask == "1"
        else:
            self.shape_mask_enabled = platform_name == "xcb" and x11_compositor_active() is False
        if self.shape_mask_enabled:
            logger.warning(
                "No X11 compositor detected — switching to alternative transparency mode "
                "(shape mask: window clipped to the image silhouette, hard 1-bit edges, no smooth alpha). "
                "Enable display compositing for smooth edges, or force this mode with MYCAT_SHAPE_MASK=1."
            )

        # Store images
        self.png_pixmap = png_pixmap
        self.gif_movie = gif_movie
        self.gif_data = gif_data  # raw GIF bytes, used to rebuild the movie in memory
        self.current_pixmap = self.png_pixmap
        self.wait_time = wait_time
        self.file_name = file_name
        self.available_images = available_images or []

        # Get original size before scaling
        self.gif_movie.jumpToFrame(0)
        original_size = self.gif_movie.currentPixmap().size()
        self.original_size = original_size

        # Calculate GIF duration from the in-memory GIF and get frame delays
        self.gif_duration, self.frame_delays = get_gif_duration(self.gif_movie, self.gif_data)
        
        # Fallback if no delays
        if not self.frame_delays:
            frame_count = self.gif_movie.frameCount()
            if frame_count > 0 and self.gif_duration > 0:
                self.frame_delays = [int((self.gif_duration / frame_count) * 1000)] * frame_count
            else:
                self.frame_delays = [100]  # Default 100ms per frame
        
        # Save first frame permanently (use the already scaled png_pixmap)
        self.first_frame_pixmap = self.png_pixmap.copy()
        
        # Animation state: 'png' -> show PNG, 'gif' -> play GIF
        self.state = 'png'

        # Setup GIF movie - play once (no looping)
        self.gif_movie.setCacheMode(QtGui.QMovie.CacheMode.CacheAll)
        # Set speed to normal (100%) - uses native GIF frame delays
        self.gif_movie.setSpeed(100)

        # Manual frame timing
        self.animation_timer = QtCore.QTimer(self)
        self.animation_timer.timeout.connect(self._on_animation_frame)
        self.current_frame = 0

        # Log GIF info
        frame_count = self.gif_movie.frameCount()
        gif_size = self.gif_movie.scaledSize()
        logger.debug(f"GIF info: {frame_count} frames, duration: {self.gif_duration:.2f}s")
        logger.info(
            f"Playing {self.file_name}.zip {original_size.width()}x{original_size.height()} > "
            f"{gif_size.width()}x{gif_size.height()} (first_frame, {self.wait_time:.1f}s static)"
        )

        # Dragging state
        self.dragging = False
        self.drag_start_pos = QtCore.QPoint()

        # Set window size to pixmap size
        pixmap_size = self.current_pixmap.size()
        self.resize(pixmap_size)

        # Position window - defaults to top-left area
        self._load_position()

        # Setup context menu
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Schedule first animation pass
        self._schedule_next_animation()

        # Save current image to INI on startup
        save_image_to_ini(self.file_name)

        # Reminder scheduler (cat-on-a-plane flyby). Loads any saved reminder
        # and re-arms it; the flyby UI is imported lazily on first use.
        self.reminder_controller = reminder.ReminderController(self)
    
    def _load_position(self) -> None:
        """Load window position from config; default to the bottom-right corner."""
        rect = usable_screen_rect()
        window_width = self.width()
        window_height = self.height()

        config = load_config(rect.width(), rect.height(), window_width, window_height)
        default_x, default_y = self.bottom_right_position(window_width, window_height)
        x = config.get("x", default_x)
        y = config.get("y", default_y)
        x, y = self._clamp_to_screens(x, y, window_width, window_height)
        self.move(x, y)

    def bottom_right_position(self, width: int, height: int) -> tuple[int, int]:
        """Bottom-right corner of the usable screen area (robust to a 0x0 Qt screen)."""
        rect = usable_screen_rect()
        x = rect.x() + rect.width() - width - DEFAULT_POSITION_OFFSET_X
        y = rect.y() + rect.height() - height - DEFAULT_POSITION_OFFSET_Y
        return x, y

    def _clamp_to_screens(self, x: int, y: int, width: int, height: int) -> tuple[int, int]:
        """Keep the window visible; robust to Qt reporting empty screen geometry."""
        rect = usable_screen_rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return x, y  # screen size unknown — trust the requested position

        window_rect = QtCore.QRect(x, y, width, height)
        union = QtCore.QRect(rect)
        app = QtWidgets.QApplication.instance()
        for screen in (app.screens() if app is not None else []):
            geo = screen.availableGeometry()
            if geo.width() > 0 and geo.height() > 0:
                union = union.united(geo)
        if union.intersects(window_rect):
            return x, y

        fallback_x = rect.x() + rect.width() - width - DEFAULT_POSITION_OFFSET_X
        fallback_y = rect.y() + rect.height() - height - DEFAULT_POSITION_OFFSET_Y
        logger.warning(
            "Saved position (%d, %d) is off-screen (usable=%s); resetting to (%d, %d)",
            x, y, union, fallback_x, fallback_y,
        )
        return fallback_x, fallback_y
    
    def _save_position(self) -> None:
        """Save current window position to config."""
        pos = self.pos()
        config = {"x": pos.x(), "y": pos.y()}
        save_config(config)
    
    def _load_image(self, image_name: str) -> None:
        """Load a different GIF from ZIP and extract first frame."""
        try:
            zip_path = skin_catalog.find_skin_zip(image_name)
            if zip_path is None:
                logger.error(f"ZIP file not found for skin: {image_name}")
                return
            
            # Extract first GIF from ZIP
            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                gif_files = [f for f in zip_file.namelist() if f.lower().endswith('.gif')]
                if not gif_files:
                    logger.error(f"No GIF file found in ZIP: {image_name}.zip")
                    return
                
                gif_data = zip_file.read(gif_files[0])
                logger.info(f"Extracted {gif_files[0]} from {zip_path.name}")
            
            # Build the new movie from the GIF bytes in memory (no temp files).
            new_movie = movie_from_gif_bytes(gif_data)
            new_movie.jumpToFrame(0)
            first_frame = new_movie.currentPixmap()
            if first_frame.isNull():
                logger.error(f"Failed to extract first frame from {image_name}.zip")
                return

            # Scale if needed
            original_size = first_frame.size()
            new_pixmap = scale_pixmap_if_needed(first_frame, IMAGE_WIDTH_MAX, IMAGE_HEIGHT_MAX)
            if original_size != new_pixmap.size():
                logger.info(
                    f"Resized {image_name}.zip: "
                    f"{original_size.width()}x{original_size.height()} -> "
                    f"{new_pixmap.width()}x{new_pixmap.height()}"
                )
            if new_pixmap.isNull():
                logger.error(f"Failed to render first frame from {image_name}.zip")
                return

            # Configure movie
            new_movie.setScaledSize(new_pixmap.size())
            new_movie.setSpeed(100)
            new_movie.jumpToFrame(0)

            # Update current images
            self.png_pixmap = new_pixmap
            self.gif_movie = new_movie
            self.gif_data = gif_data
            self.file_name = image_name

            # Update original size
            new_movie.jumpToFrame(0)
            self.original_size = new_movie.currentPixmap().size()

            # Calculate GIF duration and frame delays for new movie
            self.gif_duration, self.frame_delays = get_gif_duration(new_movie, gif_data)
            
            # Fallback if no delays
            if not self.frame_delays:
                frame_count = new_movie.frameCount()
                if frame_count > 0 and self.gif_duration > 0:
                    self.frame_delays = [int((self.gif_duration / frame_count) * 1000)] * frame_count
                else:
                    self.frame_delays = [100]  # Default 100ms per frame
            
            # Save first frame (use the already scaled new_pixmap)
            self.first_frame_pixmap = new_pixmap.copy()
            
            # Reset to PNG state
            self.current_pixmap = self.png_pixmap
            self.state = 'png'
            self.animation_timer.stop()
            self._schedule_next_animation()

            # Save bottom-right corner position before resize
            old_size = self.size()
            top_left = self.pos()
            bottom_right_x = top_left.x() + old_size.width()
            bottom_right_y = top_left.y() + old_size.height()

            # Resize window
            self.resize(self.png_pixmap.size())

            # Restore position to keep bottom-right corner in same place
            new_size = self.png_pixmap.size()
            new_x = bottom_right_x - new_size.width()
            new_y = bottom_right_y - new_size.height()
            self.move(new_x, new_y)

            # Save to INI
            save_image_to_ini(image_name)
            
            # Save new position
            self._save_position()
            
            logger.info(f"Switched to {image_name}.zip {self.png_pixmap.width()}x{self.png_pixmap.height()}")
            self.update()
            
        except Exception as e:
            logger.error(f"Error loading {image_name}: {e}")
    
    def _show_context_menu(self, pos: QtCore.QPoint) -> None:
        """Show context menu at the given position."""
        menu = QtWidgets.QMenu(self)

        # "Chat" appears only once Ollama is configured (a controller exists),
        # and is greyed out while the LLM is disabled.
        toggle_chat = getattr(self, "_toggle_llm_chat", None)
        if callable(toggle_chat):
            chat_action = menu.addAction("Chat")
            chat_action.triggered.connect(toggle_chat)
            llm_is_enabled = getattr(self, "_is_llm_enabled", None)
            if callable(llm_is_enabled):
                chat_action.setEnabled(bool(llm_is_enabled()))
            menu.addSeparator()

        # "LLM…" — pick the chat vendor (Ollama / OpenAI / Grok / custom …) and
        # model. Always available so the backend can be configured from scratch.
        llm_action = menu.addAction("LLM…")
        llm_action.triggered.connect(self.open_llm_settings)

        # Shop temporarily hidden from the menu (work in progress). The dialog
        # and its handler stay in the codebase; re-enable by uncommenting:
        # shop_action = menu.addAction("Open Shop…")
        # shop_action.triggered.connect(self._open_shop)

        reminder_action = menu.addAction("Reminder…")
        reminder_action.triggered.connect(self._open_reminder)
        
        settings_action = menu.addAction("Settings…")
        settings_action.triggered.connect(self._open_settings)
        menu.addSeparator()

        # Rebuild the list every time so freshly-installed skins appear without restart.
        self.available_images = skin_catalog.scan_all()
        if len(self.available_images) > 0:
            images_menu = menu.addMenu("Images")
            for img_name in self.available_images:
                action = images_menu.addAction(img_name)
                if img_name == self.file_name:
                    action.setCheckable(True)
                    action.setChecked(True)
                action.triggered.connect(lambda checked, name=img_name: self._load_image(name))
            menu.addSeparator()

        if autostart.is_supported():
            login_action = menu.addAction("Autostart")
            login_action.setCheckable(True)
            login_action.setChecked(autostart.is_enabled())
            login_action.toggled.connect(autostart.set_enabled)

        menu.addSeparator()
        reset_pos_action = menu.addAction("Reset Position")
        reset_pos_action.triggered.connect(self._reset_position)

        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(QtWidgets.QApplication.quit)
        menu.exec(self.mapToGlobal(pos))

    def _open_settings(self) -> None:
        """Open the Settings dialog."""
        try:
            if __package__:
                from .settings_ui import SettingsDialog
            else:
                import importlib
                SettingsDialog = importlib.import_module("mycat.settings_ui").SettingsDialog
        except Exception:
            logger.exception("Failed to import settings dialog")
            return
        dialog = SettingsDialog(parent=self, config_path=CFG_FILE, main_window=self)
        dialog.exec()

    def _reset_position(self) -> None:
        """Reset the cat's position to the bottom right."""
        window_width = self.width()
        window_height = self.height()
        default_x, default_y = self.bottom_right_position(window_width, window_height)
        self.move(default_x, default_y)
        self._save_position()

    def open_llm_settings(self) -> None:
        """Open the LLM vendor settings dialog (vendor, model, test, save)."""
        try:
            if __package__:
                from .llm_settings_ui import LLMSettingsDialog
            else:
                import importlib

                LLMSettingsDialog = importlib.import_module(
                    "mycat.llm_settings_ui"
                ).LLMSettingsDialog
        except Exception:
            logger.exception("Failed to import LLM settings dialog")
            return
        dialog = LLMSettingsDialog(self, parent=self)
        dialog.exec()

    def _open_shop(self) -> None:
        """Lazily import and show the shop dialog."""
        existing = getattr(self, "_shop_dialog", None)
        if existing is not None:
            try:
                existing.show()
                existing.raise_()
                existing.activateWindow()
                return
            except RuntimeError:
                self._shop_dialog = None  # Qt object was deleted

        try:
            if __package__:
                from .shop_ui import ShopDialog
            else:
                import importlib
                ShopDialog = importlib.import_module("mycat.shop_ui").ShopDialog
        except Exception:
            logger.exception("Failed to import shop UI")
            return

        dialog = ShopDialog(self, config_path=CFG_FILE)
        dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.destroyed.connect(lambda _=None: setattr(self, "_shop_dialog", None))
        dialog.skin_installed.connect(self._on_skin_installed)
        dialog.skin_uninstalled.connect(self._on_skin_uninstalled)
        self._shop_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _open_reminder(self) -> None:
        """Open the reminder settings dialog."""
        controller = getattr(self, "reminder_controller", None)
        if controller is not None:
            controller.open_dialog()

    def _on_skin_installed(self, _skin_id: str) -> None:
        self.available_images = skin_catalog.scan_all()

    def _on_skin_uninstalled(self, skin_id: str) -> None:
        self.available_images = skin_catalog.scan_all()
        if self.file_name == skin_id and self.available_images:
            self._load_image(self.available_images[0])
    
    def _schedule_next_animation(self) -> None:
        """Schedule the next PNG -> GIF transition with a single-shot timer."""
        delay_ms = max(0, int(self.wait_time * 1000))
        QtCore.QTimer.singleShot(delay_ms, self._start_animation)

    def _start_animation(self) -> None:
        """Switch from static PNG to one-shot GIF playback."""
        if self.state != 'png':
            return

        gif_size = self.gif_movie.scaledSize()
        logger.debug(
            f"Playing {self.file_name}.zip {self.original_size.width()}x{self.original_size.height()} > "
            f"{gif_size.width()}x{gif_size.height()} (animation, {self.gif_duration:.2f}s)"
        )
        self.state = 'gif'

        # Reset to the in-memory first frame for a fresh start
        if not self.png_pixmap.isNull():
            self.current_pixmap = self.png_pixmap
            self.update()

        # Recreate the movie from the in-memory GIF bytes for a fresh start
        self.gif_movie = movie_from_gif_bytes(self.gif_data)
        self.gif_movie.setScaledSize(self.current_pixmap.size())
        self.gif_movie.setCacheMode(QtGui.QMovie.CacheMode.CacheAll)
        self.gif_movie.setSpeed(100)
        self.gif_movie.jumpToFrame(0)

        # Start manual frame-by-frame animation with per-frame delays
        self.current_frame = 0
        self.animation_timer.stop()
        if self.frame_delays:
            self.animation_timer.start(self.frame_delays[0])
        else:
            self.animation_timer.start(100)

    def _on_animation_frame(self) -> None:
        """Manually advance to next frame at controlled speed."""
        frame_count = self.gif_movie.frameCount()

        # Check if we've completed the animation
        if self.current_frame >= frame_count:
            self.animation_timer.stop()
            logger.debug(f"Animation complete for {self.file_name} ({frame_count} frames)")
            QtCore.QTimer.singleShot(50, self._complete_switch_to_png)
            return

        # Jump to current frame and display it
        self.gif_movie.jumpToFrame(self.current_frame)
        pixmap = self.gif_movie.currentPixmap()
        if not pixmap.isNull():
            self.current_pixmap = pixmap
            self.update()

        # Move to next frame
        self.current_frame += 1

        # If not done, stop current timer and restart with next frame's delay
        if self.current_frame < frame_count and self.frame_delays and self.current_frame < len(self.frame_delays):
            delay = self.frame_delays[self.current_frame]
            self.animation_timer.stop()
            self.animation_timer.start(delay)

    def _complete_switch_to_png(self) -> None:
        """Complete the switch from GIF to PNG state."""
        if self.state == 'gif':
            # Switch to PNG state
            self.state = 'png'

            # Reuse the in-memory first frame
            static_pixmap = self.png_pixmap
            if not static_pixmap.isNull():
                self.current_pixmap = static_pixmap
                self.first_frame_pixmap = static_pixmap

            logger.debug(
                f"Playing {self.file_name}.zip {self.original_size.width()}x{self.original_size.height()} > "
                f"{self.png_pixmap.width()}x{self.png_pixmap.height()} (first_frame, {self.wait_time:.1f}s static)"
            )
            self.update()
            self._schedule_next_animation()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """Paint the current pixmap."""
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        # Draw pixmap centered in widget
        widget_rect = self.rect()
        pixmap_rect = self.current_pixmap.rect()
        x = (widget_rect.width() - pixmap_rect.width()) // 2
        y = (widget_rect.height() - pixmap_rect.height()) // 2
        painter.drawPixmap(x, y, self.current_pixmap)
        painter.end()

        if self.shape_mask_enabled:
            self.refresh_shape_mask(x, y)

    def refresh_shape_mask(self, x: int, y: int) -> None:
        """Clip the window to the current pixmap's alpha silhouette (no-compositor path).

        Recomputed only when the frame/position actually changes (cache key guard),
        so the setMask never triggers a repaint loop.
        """
        pixmap = self.current_pixmap
        key = (pixmap.cacheKey(), x, y, self.width(), self.height())
        if key == self.shape_mask_key:
            return
        self.shape_mask_key = key

        bitmap = pixmap.mask()
        if bitmap.isNull():
            self.clearMask()
            return
        region = QtGui.QRegion(bitmap)
        if x or y:
            region.translate(x, y)
        self.setMask(region)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse press for dragging."""
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse move for dragging."""
        if self.dragging and event.buttons() == QtCore.Qt.MouseButton.LeftButton:
            new_pos = event.globalPosition().toPoint() - self.drag_start_pos
            self.move(new_pos)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse release to stop dragging and save position."""
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self.dragging:
            self.dragging = False
            self._save_position()

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Pixel cat overlay with GIF animation (first frame used as static image)."
    )
    parser.add_argument(
        "-i", "--image",
        type=str,
        default=None,
        help="Path to ZIP file containing GIF (default: images/cat.zip). First frame used as static image.",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=None,
        help="Seconds to show first frame before playing GIF (default: 5.0)",
    )

    parser.add_argument(
        "--pos",
        nargs=2,
        type=int,
        metavar=("X", "Y"),
        help="Start position (overrides remembered position)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose DEBUG logging (per-frame animation cycle, GIF timing, etc.)",
    )
    llm.add_arguments(parser)
    return parser.parse_args()


def main() -> None:
    """Main entry point."""
    args = parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load wait time from config if not explicitly overridden by args
    wait_time = args.wait if args.wait is not None else load_wait_time_from_ini(STATIC_TIME)

    llm_context = llm.initialize(args)
    
    # Suppress Qt D-Bus warnings on Linux
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.theme.gnome=false")
    os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", "")
    os.environ.setdefault("QT_QPA_NO_NATIVE_MENUBAR", "1")

    # Suppress additional Qt warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    # Headless/VNC X servers may expose a framebuffer with no RANDR monitor,
    # which makes Qt see a 0x0 screen (breaks positioning and menu popups).
    # Register a virtual monitor before the QApplication reads screen geometry.
    ensure_virtual_monitor()

    # WM_CLASS instance name (read by Qt at QApplication construction). Without
    # this the taskbar uses the script name ("main.py") and groups mycat with
    # other python apps launched the same way.
    os.environ.setdefault("RESOURCE_NAME", "mycat")

    # Initialize Qt application with error handling
    try:
        app = QtWidgets.QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(True)
        app.setWindowIcon(make_app_icon())  # 😽 — used for the taskbar entry and dialogs
        # Give the window a distinct WM_CLASS so the taskbar doesn't group it with
        # other python "main.py" apps. setDesktopFileName drives the X11 class.
        app.setApplicationName("mycat")
        app.setDesktopFileName("mycat")
        platform_name = (app.platformName() or "").lower()
    except Exception as e:
        logger.error(f"Failed to initialize Qt application: {e}")
        sys.exit(1)
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        """Handle Ctrl+C gracefully."""
        logger.info("\nReceived interrupt signal, shutting down...")
        app.quit()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Allow signal handling during Qt event loop
    timer = QtCore.QTimer()
    timer.timeout.connect(lambda: None)  # Allow Python signal handlers to run
    timer.start(100)  # Check every 100ms
    
    # Scan for available ZIP files
    available_images = scan_images_directory()
    logger.info(f"Found {len(available_images)} ZIP archive(s): {', '.join(available_images)}")
    
    # Load default image from INI if no image path provided
    default_image = None
    if not args.image:
        default_image = load_image_from_ini()
        if default_image and default_image not in available_images:
            logger.warning(f"Image '{default_image}' from INI not found in available images, using default: cat")
            default_image = None
    
    # Load images
    try:
        png_pixmap, gif_movie, file_name, gif_data = load_packaged_images(
            args.image, default_image, IMAGE_WIDTH_MAX, IMAGE_HEIGHT_MAX
        )
        logger.info(
            f"Playing {file_name}.zip (first frame) "
            f"{png_pixmap.width()}x{png_pixmap.height()} for {wait_time:.1f}s"
        )
    except Exception as e:
        logger.error(f"Error loading images: {e}")
        sys.exit(2)

    # Create and show window
    window = PixelCatWindow(png_pixmap, gif_movie, wait_time, file_name, available_images, gif_data)
    if llm_context:
        llm.attach(window, llm_context)
    
    if args.pos:
        window.move(args.pos[0], args.pos[1])

    if platform_name == "offscreen":
        logger.info("Offscreen platform detected: skipping window display.")
        QtCore.QTimer.singleShot(0, app.quit)
    else:
        window.show()
        # Persistent cat tray icon (kept on the window so it isn't GC'd).
        window.tray_icon = setup_tray(app, window, png_pixmap)

    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        logger.info("\nShutdown requested by user")
        sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\nShutdown requested by user")
        sys.exit(0)
