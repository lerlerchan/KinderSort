"""
utils.py — File helpers, naming, and logging for KinderSort.
"""

import logging
import shutil
from pathlib import Path

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def setup_logger(output_folder: Path) -> logging.Logger:
    log_path = output_folder / "kindersort_log.txt"
    logger = logging.getLogger("kindersort")
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        logger.handlers.clear()

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def is_image_file(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def collect_event_images(events_folder: Path) -> list[tuple[Path, str]]:
    results = []
    for item in sorted(events_folder.iterdir()):
        if not item.is_dir():
            continue
        event_name = item.name
        for image_path in sorted(item.rglob("*")):
            if image_path.is_file() and is_image_file(image_path):
                results.append((image_path, event_name))

    if not results:
        event_name = events_folder.name
        for image_path in sorted(events_folder.iterdir()):
            if image_path.is_file() and is_image_file(image_path):
                results.append((image_path, event_name))
    return results


def build_output_filename(event_name: str, original_filename: str) -> str:
    return f"{event_name}__{original_filename}"


def safe_copy(src: Path, dest_folder: Path, filename: str, logger: logging.Logger) -> Path:
    dest_folder.mkdir(parents=True, exist_ok=True)
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    dest_path = dest_folder / filename
    counter = 2
    while dest_path.exists():
        dest_path = dest_folder / f"{stem}_{counter}{suffix}"
        counter += 1
    shutil.copy2(src, dest_path)
    logger.debug(f"Copied {src.name} → {dest_path}")
    return dest_path