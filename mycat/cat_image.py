"""GIF/cat-image helpers extracted from main.py (zero logic change).

The scale caps (``IMAGE_WIDTH_MAX``/``IMAGE_HEIGHT_MAX``) stay defined in
``main.py`` and are passed in as arguments; see :func:`load_packaged_images`.
"""

import io
import logging
import zipfile
from pathlib import Path

from PySide6 import QtCore, QtGui

from . import skin_catalog

logger = logging.getLogger(__name__)


def movie_from_gif_bytes(gif_data: bytes) -> QtGui.QMovie:
    """A QMovie that reads the GIF from memory (a QBuffer), not a temp file.

    The QBuffer is parented to the movie so it lives exactly as long as the
    movie does — no dangling device, no /tmp file.
    """
    movie = QtGui.QMovie()
    buffer = QtCore.QBuffer(movie)
    buffer.setData(gif_data)
    buffer.open(QtCore.QIODevice.OpenModeFlag.ReadOnly)
    movie.setDevice(buffer)
    movie.setFormat(b"GIF")
    movie.setCacheMode(QtGui.QMovie.CacheMode.CacheAll)
    return movie


def parse_gif_frame_delays(gif_data: bytes) -> list[int]:
    """
    Parse GIF bytes using Pillow to extract frame delays.
    Returns list of delays in milliseconds.
    """
    try:
        try:
            from PIL import Image
        except ImportError:
            logger.warning("Pillow not available, falling back to manual parsing")
            return []

        img = Image.open(io.BytesIO(gif_data))
        if not hasattr(img, 'n_frames'):
            return []

        delays = []
        for i in range(img.n_frames):
            img.seek(i)
            # Get duration in milliseconds, default to 100ms if not specified
            duration_ms = img.info.get('duration', 100)
            delays.append(duration_ms)

        img.close()
        logger.info(f"Calculated GIF duration: {sum(delays)/1000:.2f}s from {len(delays)} frames")
        return delays

    except Exception as e:
        logger.debug(f"Could not parse GIF frame delays with Pillow: {e}")
        return []


def get_gif_duration(movie: QtGui.QMovie, gif_data: bytes) -> tuple[float, list[int]]:
    """
    Calculate total duration of GIF animation in seconds and get frame delays.
    Returns: (total_duration_seconds, list_of_frame_delays_ms)
    """
    try:
        # Parse actual delays from the in-memory GIF bytes
        delays = parse_gif_frame_delays(gif_data)
        if delays:
            total_duration = sum(delays) / 1000.0
            return total_duration, delays

        # Fallback: estimate based on frame count
        frame_count = movie.frameCount()
        if frame_count > 0:
            estimated_duration = frame_count * 0.1  # Default 100ms per frame
            estimated_delays = [100] * frame_count
            logger.debug(f"Using estimated duration: {frame_count} frames * 0.1s = {estimated_duration:.2f}s")
            return estimated_duration, estimated_delays

        return 0.0, []
    except Exception as e:
        logger.debug(f"Could not calculate GIF duration: {e}")
        return 0.0, []


def scale_pixmap_if_needed(pixmap: QtGui.QPixmap, max_width: int, max_height: int) -> QtGui.QPixmap:
    """
    Scale pixmap down if needed, maintaining aspect ratio.
    If image is larger than max_width or max_height, scale it down.
    Does not scale up smaller images.
    Returns the scaled pixmap.
    """
    original_width = pixmap.width()
    original_height = pixmap.height()

    # Calculate scale factors for both dimensions
    width_scale = 1.0
    height_scale = 1.0

    if original_width > max_width:
        width_scale = max_width / original_width
    if original_height > max_height:
        height_scale = max_height / original_height

    # Use the smaller scale factor to ensure both constraints are met
    scale_factor = min(width_scale, height_scale)

    # Only scale if needed
    if scale_factor < 1.0:
        new_width = int(original_width * scale_factor)
        new_height = int(original_height * scale_factor)

        return pixmap.scaled(
            new_width, new_height,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation
        )

    return pixmap


def load_packaged_images(
    image_path: str | None = None,
    default_image: str | None = None,
    max_width: int = 300,
    max_height: int = 500,
) -> tuple[QtGui.QPixmap, QtGui.QMovie, str, bytes]:
    """
    Load the GIF from a ZIP archive entirely in memory (no temp files).
    If image_path is provided, use it (should point to a ZIP file).
    Returns: (first_frame_pixmap, gif_movie, base_name, gif_bytes)
    """
    if image_path:
        # User provided ZIP path
        zip_path = Path(image_path)
        if not zip_path.exists():
            raise FileNotFoundError(f"ZIP not found: {zip_path}")
        base_name = zip_path.stem
    else:
        # Use default_image if provided, otherwise default to "cat"
        if default_image:
            base_name = default_image
        else:
            base_name = "cat"

        resolved = skin_catalog.find_skin_zip(base_name)
        if resolved is None:
            raise FileNotFoundError(
                f"ZIP not found for skin '{base_name}' in bundled or user skins dir"
            )
        zip_path = resolved

    if not zip_path.exists():
        raise FileNotFoundError(f"ZIP not found: {zip_path}")

    # Extract first GIF from ZIP
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_file:
            # Find first GIF file in the archive
            gif_files = [f for f in zip_file.namelist() if f.lower().endswith('.gif')]
            if not gif_files:
                raise ValueError(f"No GIF file found in ZIP: {zip_path}")

            # Get first GIF file
            gif_file_name = gif_files[0]
            gif_data = zip_file.read(gif_file_name)
            logger.info(f"Extracted {gif_file_name} from {zip_path.name}")
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Invalid ZIP file: {zip_path}") from exc

    # Build the animated movie straight from the GIF bytes in memory.
    movie = movie_from_gif_bytes(gif_data)
    movie.jumpToFrame(0)
    first_frame = movie.currentPixmap()
    if first_frame.isNull():
        raise ValueError(f"Failed to extract first frame from GIF in ZIP: {zip_path}")

    # Scale if needed
    original_size = first_frame.size()
    pixmap = scale_pixmap_if_needed(first_frame, max_width, max_height)
    if original_size != pixmap.size():
        logger.info(
            f"Resized {Path(zip_path).name}: "
            f"{original_size.width()}x{original_size.height()} -> "
            f"{pixmap.width()}x{pixmap.height()}"
        )
    if pixmap.isNull():
        raise ValueError(f"Failed to render first frame from GIF in ZIP: {zip_path}")

    # Scale GIF movie to same size as the first frame
    movie.setScaledSize(pixmap.size())
    movie.jumpToFrame(0)

    return pixmap, movie, base_name, gif_data


__all__ = [
    "movie_from_gif_bytes",
    "parse_gif_frame_delays",
    "get_gif_duration",
    "scale_pixmap_if_needed",
    "load_packaged_images",
]
