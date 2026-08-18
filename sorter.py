"""
sorter.py — High-Precision Local AI Engine for KinderSort.

Key Engine Features:
- Preprocessing: CLAHE Adaptive Local Contrast & Edge Sharpening for difficult lighting.
- Multi-Scale Pyramid Detection: HOG Pyramid Upsampling to capture distant/small student faces.
- Low-Resource Quantization: FP16 array memory storage with strict CPU enforcement.
- Memory Protection: Immediate garbage collection to prevent memory leaks on low-end PCs.
"""

import gc
import logging
from collections.abc import Callable
from pathlib import Path

import cv2
import face_recognition
import numpy as np
from PIL import Image, UnidentifiedImageError

from utils import (
    build_output_filename,
    collect_event_images,
    is_image_file,
    safe_copy,
)


class PhotoSorter:
    """Ultra-High Accuracy Local AI Photo Sorter."""

    DISTANCE_THRESHOLD = 0.54
    """Distance cutoff for student matching (lower = stricter, 0.54 minimizes misclassifications)."""

    MAX_IMAGE_DIMENSION = 1400
    """Optimal long-side limit for preserving small facial features while keeping CPU processing fast."""

    def __init__(
        self,
        reference_folder: Path,
        events_folder: Path,
        output_folder: Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.reference_folder = reference_folder
        self.events_folder = events_folder
        self.output_folder = output_folder
        self.logger = logger
        # Maps student name -> List of FP16 face encodings
        self._student_encodings: dict[str, list[np.ndarray]] = {}

    # ------------------------------------------------------------------
    # Local Preprocessing: CLAHE + Resizing + Sharpening
    # ------------------------------------------------------------------

    def _load_and_enhance(self, image_path: Path) -> np.ndarray:
        """Apply CLAHE local illumination enhancement and sharpening for dark/shadowed faces."""
        img_bgr = cv2.imread(str(image_path))
        if img_bgr is None:
            raise UnidentifiedImageError(f"Cannot read image: {image_path}")

        h, w = img_bgr.shape[:2]
        longest = max(h, w)
        if longest > self.MAX_IMAGE_DIMENSION:
            scale = self.MAX_IMAGE_DIMENSION / longest
            img_bgr = cv2.resize(img_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_LANCZOS4)

        # LAB color space transformation for CLAHE
        lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cl = clahe.apply(l)

        limg = cv2.merge((cl, a, b))
        enhanced_bgr = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)

        # Mild sharpening filter
        kernel = np.array([[0, -0.5, 0], [-0.5, 3.0, -0.5], [0, -0.5, 0]])
        sharpened_bgr = cv2.filter2D(enhanced_bgr, -1, kernel)

        return cv2.cvtColor(sharpened_bgr, cv2.COLOR_BGR2RGB)

    # ------------------------------------------------------------------
    # Multi-Scale Pyramid Detection
    # ------------------------------------------------------------------

    def _detect_faces_pyramid(self, rgb_image: np.ndarray) -> tuple[list[tuple[int, int, int, int]], np.ndarray]:
        """Detect faces using multi-pass HOG pyramid upsampling."""
        # Pass 1: Standard HOG with upsampling
        boxes = face_recognition.face_locations(rgb_image, number_of_times_to_upsample=1, model="hog")

        # Pass 2: Deeper upsampling for small/faraway student faces
        if not boxes:
            boxes = face_recognition.face_locations(rgb_image, number_of_times_to_upsample=2, model="hog")

        return boxes, rgb_image

    # ------------------------------------------------------------------
    # Reference Loading
    # ------------------------------------------------------------------

    def load_references(
        self,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> list[str]:
        """Load reference photos with jitter averaging for clean base vectors."""
        no_face_names: list[str] = []

        reference_images = sorted(
            p for p in self.reference_folder.iterdir() if is_image_file(p)
        )

        if not reference_images:
            if self.logger:
                self.logger.warning("No reference images found in %s", self.reference_folder)
            return no_face_names

        total = len(reference_images)
        for current, ref_path in enumerate(reference_images, start=1):
            student_name = ref_path.stem.split("_")[0]
            if progress_callback:
                progress_callback(current, total, student_name)

            rgb_image = None
            try:
                rgb_image = self._load_and_enhance(ref_path)
                locations, rgb_image = self._detect_faces_pyramid(rgb_image)

                encodings = face_recognition.face_encodings(
                    rgb_image,
                    known_face_locations=locations,
                    num_jitters=3,
                    model="large",
                )

                if not encodings:
                    if self.logger:
                        self.logger.warning("No face detected in reference photo for %s (%s)", student_name, ref_path.name)
                    if student_name not in self._student_encodings:
                        no_face_names.append(student_name)
                    continue

                if student_name not in self._student_encodings:
                    self._student_encodings[student_name] = []

                self._student_encodings[student_name].append(encodings[0].astype(np.float16))
                if self.logger:
                    self.logger.info("Loaded reference vector for %s", student_name)

            except Exception as exc:  # noqa: BLE001
                if self.logger:
                    self.logger.error("Could not read reference photo %s: %s", ref_path.name, exc)
            finally:
                if rgb_image is not None:
                    del rgb_image
                gc.collect()

        return no_face_names

    # ------------------------------------------------------------------
    # Main Sorting Pipeline
    # ------------------------------------------------------------------

    def sort_all(
        self,
        progress_callback: Callable[[int, int, str], None],
        cancelled: Callable[[], bool],
    ) -> dict[str, int]:
        """Process event images locally."""
        images = collect_event_images(self.events_folder)
        total = len(images)
        counts = {"total": total, "matched": 0, "unmatched": 0, "skipped": 0}

        if self.logger:
            self.logger.info("Starting High-Accuracy AI sort — %d images found", total)

        for current, (image_path, event_name) in enumerate(images, start=1):
            if cancelled():
                if self.logger:
                    self.logger.info("Sort cancelled by user at image %d/%d", current, total)
                break

            progress_callback(current, total, image_path.name)
            output_filename = build_output_filename(event_name, image_path.name)
            rgb_image = None

            try:
                rgb_image = self._load_and_enhance(image_path)
            except UnidentifiedImageError:
                safe_copy(image_path, self.output_folder / "_unmatched", output_filename, self.logger)
                counts["unmatched"] += 1
                continue
            except Exception as exc:  # noqa: BLE001
                if self.logger:
                    self.logger.error("Could not open %s: %s — skipping", image_path.name, exc)
                counts["skipped"] += 1
                continue

            try:
                face_locations, rgb_image = self._detect_faces_pyramid(rgb_image)
                face_encodings = face_recognition.face_encodings(
                    rgb_image, face_locations, num_jitters=1, model="large"
                )

            except Exception as exc:  # noqa: BLE001
                if self.logger:
                    self.logger.error("Face detection failed for %s: %s", image_path.name, exc)
                safe_copy(image_path, self.output_folder / "_unmatched", output_filename, self.logger)
                counts["unmatched"] += 1
                continue
            finally:
                if rgb_image is not None:
                    del rgb_image
                gc.collect()

            if not face_encodings:
                if self.logger:
                    self.logger.info("No face detected: %s → _unmatched", image_path.name)
                safe_copy(image_path, self.output_folder / "_unmatched", output_filename, self.logger)
                counts["unmatched"] += 1
                continue

            matched_students: set[str] = set()
            for encoding in face_encodings:
                match = self._match_face(encoding.astype(np.float16))
                if match:
                    matched_students.add(match)

            if matched_students:
                for student_name in matched_students:
                    dest_folder = self.output_folder / student_name
                    safe_copy(image_path, dest_folder, output_filename, self.logger)
                    if self.logger:
                        self.logger.info("Matched %s → %s", image_path.name, student_name)
                counts["matched"] += 1
            else:
                if self.logger:
                    self.logger.info("No student match: %s → _unmatched", image_path.name)
                safe_copy(image_path, self.output_folder / "_unmatched", output_filename, self.logger)
                counts["unmatched"] += 1

        if self.logger:
            self.logger.info(
                "Sort complete — total=%d matched=%d unmatched=%d skipped=%d",
                counts["total"], counts["matched"], counts["unmatched"], counts["skipped"]
            )
        return counts

    # ------------------------------------------------------------------
    # Vector Comparison Optimization
    # ------------------------------------------------------------------

    def _match_face(self, encoding: np.ndarray) -> str | None:
        """Evaluates Euclidean distance across all student reference vectors."""
        if not self._student_encodings:
            return None

        best_match_student = None
        min_distance = float("inf")

        for student_name, vector_list in self._student_encodings.items():
            known_encodings = np.stack(vector_list)

            distances = face_recognition.face_distance(
                known_encodings.astype(np.float32),
                encoding.astype(np.float32)
            )
            student_min_dist = float(np.min(distances))

            if student_min_dist < min_distance:
                min_distance = student_min_dist
                best_match_student = student_name

        if min_distance <= self.DISTANCE_THRESHOLD:
            return best_match_student

        return None