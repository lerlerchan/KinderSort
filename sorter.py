"""
sorter.py — Face recognition logic for KinderSort.

PhotoSorter loads reference encodings and sorts event photos into per-student
output folders.  All processing is CPU-only (no GPU required).
"""

import logging
from math import isfinite
from collections.abc import Callable
from pathlib import Path

import face_recognition
import numpy as np
from PIL import Image, UnidentifiedImageError

from utils import (
    build_output_filename,
    collect_event_images,
    is_image_file,
    safe_copy,
    SourceReadError,
    validate_input_path,
)


class PhotoSorter:
    """Encapsulates the full sort pipeline from reference loading to file copying.

    Usage::

        sorter = PhotoSorter(reference_folder, events_folder, output_folder, logger)
        sorter.load_references()   # sync, raises ValueError for failed references
        summary = sorter.sort_all(progress_cb, cancelled_cb)
    """

    DISTANCE_THRESHOLD = 0.55
    """Maximum face distance to consider a match (lower = stricter)."""

    MAX_IMAGE_DIMENSION = 1000
    """Longest side in pixels after resizing for face detection (performance)."""

    def __init__(
        self,
        reference_folder: Path,
        events_folder: Path,
        output_folder: Path,
        logger: logging.Logger,
    ) -> None:
        """Store folder paths and logger; initialise empty encoding dict."""
        self.reference_folder = reference_folder
        self.events_folder = events_folder
        self.output_folder = output_folder
        self.logger = logger
        self._student_encodings: dict[str, np.ndarray] = {}
        self.error_details: list[dict[str, object]] = []

    # ------------------------------------------------------------------
    # Reference loading
    # ------------------------------------------------------------------

    def load_references(
        self,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> list[str]:
        """Encode every reference photo and store by student name.

        Iterates over image files in reference_folder.  The student name is the
        filename stem (e.g. ``Ali.jpg`` → ``"Ali"``).

        Args:
            progress_callback: Optional callable with ``(current, total, name)``
                called after each student is processed so the GUI can update.

        Returns:
            Empty list on success, retained for caller compatibility.

        Raises:
            ValueError: A student name is invalid or duplicated (case-insensitive),
                or any reference cannot be read or produce a usable encoding.
        """
        # Never expose stale or partially loaded references after a failed load.
        self._student_encodings.clear()
        pending_encodings: dict[str, np.ndarray] = {}
        failures: list[str] = []

        validate_input_path(self.reference_folder)
        reference_images = []
        for ref_path in sorted(self.reference_folder.iterdir()):
            validate_input_path(ref_path)
            if is_image_file(ref_path):
                reference_images.append(ref_path)

        # Validate the entire set before callbacks, image loading or encoding.
        # Keep this outside the per-image handler so invalid names abort loading.
        seen_names: dict[str, Path] = {}
        for ref_path in reference_images:
            student_name = ref_path.stem
            if student_name.casefold() in {"_unmatched", "kindersort_log.txt"}:
                raise ValueError(
                    f"Invalid reference image '{ref_path.name}': student name "
                    f"'{student_name}' is reserved for KinderSort output. "
                    "Please rename the reference image."
                )
            if student_name.endswith((".", " ")):
                raise ValueError(
                    f"Invalid reference image '{ref_path.name}': student name "
                    "must not end with a period or space. "
                    "Please rename the reference image."
                )

            name_key = student_name.casefold()
            if name_key in seen_names:
                raise ValueError(
                    f"Duplicate student name in reference images "
                    f"'{seen_names[name_key].name}' and '{ref_path.name}'. "
                    "Use one reference image per student; remove the extra image "
                    "or rename the files to distinct student names "
                    "(names are case-insensitive)."
                )
            seen_names[name_key] = ref_path

        if not reference_images:
            self.logger.warning("No reference images found in %s", self.reference_folder)
            return []

        total = len(reference_images)
        for current, ref_path in enumerate(reference_images, start=1):
            student_name = ref_path.stem
            if progress_callback:
                progress_callback(current, total, student_name)
            # Keep security failures outside the recoverable decoder handler.
            validate_input_path(ref_path)
            stage = "image reading"
            try:
                image = face_recognition.load_image_file(str(ref_path))
                stage = "face detection"
                locations = face_recognition.face_locations(image, model="cnn")
                stage = "face encoding"
                encodings = face_recognition.face_encodings(
                    image, known_face_locations=locations, num_jitters=10, model="large"
                )

                if not encodings:
                    raise ValueError("No usable face encoding; no face was detected")

                encoding = encodings[0]
                if len(encoding) != 128 or not all(isfinite(value) for value in encoding):
                    raise ValueError("No usable face encoding; expected 128 finite values")

                if len(encodings) > 1:
                    self.logger.warning(
                        "Multiple faces in reference photo for %s — using first face only",
                        student_name,
                    )

                pending_encodings[student_name] = encoding

            except Exception as exc:  # noqa: BLE001
                failure = f"'{ref_path.name}': {stage} failed ({type(exc).__name__}: {exc})"
                failures.append(failure)
                self.logger.error("Invalid reference photo %s", failure)

        if failures:
            raise ValueError(
                "Reference photo validation failed:\n" + "\n".join(failures)
                + "\nPlease replace or correct these reference photos and try again. "
                "Sorting has not started."
            )

        self._student_encodings = pending_encodings

        self.logger.info(
            "Loaded %d student reference(s)", len(self._student_encodings)
        )
        return []

    # ------------------------------------------------------------------
    # Main sort loop
    # ------------------------------------------------------------------

    def sort_all(
        self,
        progress_callback: Callable[[int, int, str], None],
        cancelled: Callable[[], bool],
    ) -> dict[str, int]:
        """Sort all event photos into per-student output subfolders.

        Processes one image at a time to keep RAM usage low.  For each detected
        face in a photo the nearest student is identified; the photo is copied
        to every matched student folder (allowing group shots).  Photos with no
        match or no face are copied to ``_unmatched/``.

        Args:
            progress_callback: Called with ``(current, total, filename)`` after
                each image so the GUI can update its progress bar.
            cancelled: Zero-arg callable; returns True if the user has cancelled.

        Returns:
            Integer counts: ``total``, ``matched``, ``unmatched``, ``errors``,
            and legacy ``skipped`` (the subset of errors not preserved).
            Errors never count as matched or normal unmatched. Per-photo
            details remain in ``error_details``, reset for each run.
        """
        self.error_details = []
        images = collect_event_images(self.events_folder)
        total = len(images)

        counts = {"total": total, "matched": 0, "unmatched": 0, "skipped": 0, "errors": 0}

        self.logger.info("Starting sort — %d images found", total)

        for current, (image_path, event_name) in enumerate(images, start=1):
            if cancelled():
                self.logger.info("Sort cancelled by user at image %d/%d", current, total)
                break

            progress_callback(current, total, image_path.name)
            validate_input_path(image_path)

            output_filename = build_output_filename(event_name, image_path.name)

            stage = "image reading"
            processing_error = None
            try:
                rgb_image = self._load_and_resize(image_path)
                stage = "HOG detection"
                face_locations = face_recognition.face_locations(rgb_image)  # HOG — fast
                if not face_locations:
                    stage = "CNN detection"
                    face_locations = face_recognition.face_locations(rgb_image, model="cnn")  # CNN fallback
                stage = "face encoding"
                face_encodings = face_recognition.face_encodings(
                    rgb_image, face_locations, num_jitters=3, model="large"
                )
                stage = "face matching"
                matched_students: set[str] = set()
                for encoding in face_encodings:
                    match = self._match_face(encoding)
                    if match:
                        matched_students.add(match)
            except Exception as exc:  # noqa: BLE001
                processing_error = exc

            completed_paths: list[str] = []
            if processing_error is None:
                # Only proven source errors are recoverable here. Output and
                # ambiguous errors propagate, even after some group copies.
                try:
                    for name in sorted(matched_students) if matched_students else ["_unmatched"]:
                        copied = safe_copy(image_path, self.output_folder / name, output_filename, self.logger)
                        completed_paths.append(str(copied))
                except SourceReadError as exc:
                    stage = "source copying"
                    processing_error = exc.original_error
                else:
                    counts["matched" if matched_students else "unmatched"] += 1
                    continue

            counts["errors"] += 1
            # External exception messages may contain images/encodings. Record
            # the stage and exception type rather than arbitrary payload text.
            detail: dict[str, object] = {
                "source": str(image_path), "stage": stage,
                "reason": f"{stage} failed ({type(processing_error).__name__})",
                "preserved": False, "preserved_path": None,
                "preservation_reason": None, "completed_output_paths": completed_paths,
            }
            self.error_details.append(detail)
            try:
                preserved = safe_copy(image_path, self.output_folder / "_unmatched", output_filename, self.logger)
            except SourceReadError as exc:
                counts["skipped"] += 1
                detail["preservation_reason"] = f"Source bytes unreadable ({type(exc.original_error).__name__})"
            except Exception as exc:
                detail["preservation_reason"] = f"Output preservation failed ({type(exc).__name__}); batch stopped"
                self.logger.error("Activity photo error: %s", detail)
                raise
            else:
                detail["preserved"] = True
                detail["preserved_path"] = str(preserved)
            self.logger.error("Activity photo error: %s", detail)

        self.logger.info(
            "Sort complete — total=%d matched=%d unmatched=%d skipped=%d errors=%d",
            counts["total"],
            counts["matched"],
            counts["unmatched"],
            counts["skipped"],
            counts["errors"],
        )
        return counts

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_and_resize(self, image_path: Path) -> np.ndarray:
        """Open image with Pillow, resize if needed, and return as RGB numpy array.

        Resizing large images to at most MAX_IMAGE_DIMENSION on the longest side
        dramatically reduces face_locations() time on CPU without meaningfully
        reducing recognition accuracy.

        Raises:
            UnidentifiedImageError: If Pillow cannot read the file format.
        """
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            width, height = img.size
            longest = max(width, height)
            if longest > self.MAX_IMAGE_DIMENSION:
                scale = self.MAX_IMAGE_DIMENSION / longest
                new_size = (int(width * scale), int(height * scale))
                img = img.resize(new_size, Image.LANCZOS)
            return np.array(img)

    def _match_face(self, encoding: np.ndarray) -> str | None:
        """Find the closest student encoding within DISTANCE_THRESHOLD.

        Uses face_distance() + argmin rather than compare_faces() booleans so
        each detected face always matches at most one student — the nearest one.

        Args:
            encoding: 128-d face encoding from face_recognition.

        Returns:
            Student name string if a match is found, otherwise None.
        """
        if not self._student_encodings:
            return None

        names = list(self._student_encodings.keys())
        known_encodings = np.array(list(self._student_encodings.values()))

        distances = face_recognition.face_distance(known_encodings, encoding)
        best_idx = int(np.argmin(distances))
        best_distance = distances[best_idx]

        if best_distance <= self.DISTANCE_THRESHOLD:
            self.logger.debug(
                "Face matched to %s (distance=%.4f)", names[best_idx], best_distance
            )
            return names[best_idx]

        self.logger.debug("No match — best distance=%.4f", best_distance)
        return None
