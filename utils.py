"""
utils.py — File helpers, naming, and logging for KinderSort.

No face_recognition dependency — safe to import without dlib installed.
"""

import logging
import shutil
from pathlib import Path

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

def validate_folder_separation(
    reference_folder: Path,
    events_folder: Path,
    output_folder: Path,
) -> None:
    """
    Validate that the output folder does not overlap with
    the reference or events folders.

    Raises:
        ValueError: If the output folder overlaps with an input folder.
    """
    output = output_folder.resolve()

    for name, source in (
        ("Reference", reference_folder),
        ("Events", events_folder),
    ):
        resolved_source = source.resolve()

        if (
            output == resolved_source
            or output in resolved_source.parents
            or resolved_source in output.parents
        ):
            raise ValueError(
                f"Output folder must be separate from {name} folder."
            )

def setup_logger(output_folder: Path) -> logging.Logger:
    """Create and return a logger that writes to output_folder/kindersort_log.txt.

    Also attaches a StreamHandler so messages appear in the terminal during
    development. Safe to call multiple times — duplicate handlers are avoided.
    """
    log_path = output_folder / "kindersort_log.txt"
    logger = logging.getLogger("kindersort")
    logger.setLevel(logging.DEBUG)

    # Avoid adding duplicate handlers when called multiple times
    if logger.handlers:
        logger.handlers.clear()

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    return logger


def is_image_file(path: Path) -> bool:
    """Return True if path has a supported image extension (case-insensitive)."""
    return path.suffix.lower() in SUPPORTED_EXTENSIONS
    
def collect_event_images(events_folder: Path) -> list[tuple[Path, str]]:
    """Collect images from the Events root and its subfolders.

    Images directly inside events_folder use the root folder name
    as their event name.

    Images inside subfolders use the name of their immediate
    child folder under events_folder as their event name.

    Both root-level and nested images are always collected.
    Each image is included only once.
    """
    results: list[tuple[Path, str]] = []

    for item in sorted(events_folder.iterdir()):

        # Collect images directly inside the Events root.
        if item.is_file() and is_image_file(item):
            results.append((item, events_folder.name))

        # Collect images inside event subfolders.
        elif item.is_dir():
            event_name = item.name

            for image_path in sorted(item.rglob("*")):
                if image_path.is_file() and is_image_file(image_path):
                    results.append((image_path, event_name))

    return results
    
def build_output_filename(event_name: str, original_filename: str) -> str:
    """Build a destination filename prefixed with the event folder name.

    Format: ``{event_name}__{original_filename}``

    The double underscore acts as a separator so event names and filenames
    remain visually distinct even when both contain single underscores.

    Example:
        >>> build_output_filename("Sports_Day", "IMG_001.jpg")
        'Sports_Day__IMG_001.jpg'
    """
    return f"{event_name}__{original_filename}"


def safe_copy(src: Path, dest_folder: Path, filename: str, logger: logging.Logger) -> Path:
    """Copy src to dest_folder/filename using shutil.copy2 (preserves metadata).

    If a file with the same name already exists in dest_folder, appends _2, _3,
    … before the extension until a free name is found.  Creates dest_folder if
    it does not exist.

    Returns the final destination path.
    """
    dest_folder.mkdir(parents=True, exist_ok=True)

    stem = Path(filename).stem
    suffix = Path(filename).suffix
    dest_path = dest_folder / filename

    counter = 2
    while dest_path.exists():
        dest_path = dest_folder / f"{stem}_{counter}{suffix}"
        counter += 1

    shutil.copy2(src, dest_path)
    logger.debug("Copied %s → %s", src.name, dest_path)
    return dest_path
