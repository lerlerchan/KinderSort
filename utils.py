"""
utils.py — File helpers, naming, and logging for KinderSort.

No face_recognition dependency — safe to import without dlib installed.
"""

import logging
import os
import shutil
import stat
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


def _reject_linked_output(folder: Path) -> None:
    """Reject links in the output path, including Windows reparse points."""
    absolute = folder.absolute()
    for directory in reversed((absolute, *absolute.parents)):
        try:
            info = directory.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or (
            getattr(info, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        ):
            raise ValueError(f"Output directory must not contain links: {directory}")


def safe_copy(src: Path, dest_folder: Path, filename: str, logger: logging.Logger) -> Path:
    """Copy src through an exclusively created destination, preserving metadata.

    If a file with the same name already exists in dest_folder, appends _2, _3,
    … before the extension until a free name is found.  Creates dest_folder if
    it does not exist.

    Returns the final destination path.
    """
    if (
        not filename
        or filename in (".", "..")
        or Path(filename).name != filename
        or (os.name == "nt" and ":" in filename)
    ):
        raise ValueError("Destination filename must be a single file name.")
    _reject_linked_output(dest_folder)
    dest_folder.mkdir(parents=True, exist_ok=True)
    _reject_linked_output(dest_folder)

    stem = Path(filename).stem
    suffix = Path(filename).suffix
    dest_path = dest_folder / filename

    counter = 2
    while True:
        _reject_linked_output(dest_folder)
        try:
            destination = dest_path.open("xb")
        except FileExistsError:
            dest_path = dest_folder / f"{stem}_{counter}{suffix}"
            counter += 1
        else:
            break

    created = None
    try:
        with destination:
            created = os.fstat(destination.fileno())
            with src.open("rb") as source:
                shutil.copyfileobj(source, destination)
        _reject_linked_output(dest_folder)
        if not os.path.samestat(created, dest_path.lstat()):
            raise OSError("Destination was replaced during copying.")
        shutil.copystat(src, dest_path)
    except BaseException:
        # Best-effort cleanup: verify file identity before unlinking.
	# Concurrent path replacement remains possible between check and unlink.
        try:
            _reject_linked_output(dest_folder)
            if created is not None and os.path.samestat(created, dest_path.lstat()):
                dest_path.unlink()
        except (OSError, ValueError):
            logger.warning("Could not safely remove incomplete copy: %s", dest_path)
        raise
    logger.debug("Copied %s → %s", src.name, dest_path)
    return dest_path
