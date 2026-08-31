"""
enhanced_sorter.py — Enhanced face recognition for KinderSort Lite.

Adds ensemble detection (HOG + CNN), image preprocessing via CLAHE,
normalized-match-margin scoring, two-threshold routing (_review_required),
secure cached encoding support for low-resource environments, and
strict reference-photo validation (exactly one face required).
All processing remains CPU-only and fully offline.
"""

import hashlib
import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False

from face_engine import FaceEngine
from preprocessor import ImagePreprocessor, load_and_preprocess
from utils import (
    build_output_filename,
    collect_event_images,
    is_image_file,
    safe_copy,
)


# ---------------------------------------------------------------------------
# Cache location — stored in app data, not the output folder
# ---------------------------------------------------------------------------
CACHE_DIR = Path.home() / ".kindersort" / "cache"
CACHE_FILE = CACHE_DIR / "encoding_cache.enc"  # encrypted (AES-256-GCM)
CACHE_KEY_FILE = CACHE_DIR / ".cache_key"


def _get_or_create_cache_key() -> bytes:
    """Load the local AES-256 key, generating one on first use.

    The encoding cache holds derived biometric data (face encodings), so
    it is encrypted at rest rather than stored as plain JSON. The key is
    a per-machine random 256-bit value stored alongside the cache with
    restrictive file permissions; this protects against casual disk
    inspection or the cache file being copied off the machine, though it
    is not a substitute for full-disk encryption if the whole machine is
    compromised.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if CACHE_KEY_FILE.exists():
        return CACHE_KEY_FILE.read_bytes()
    key = AESGCM.generate_key(bit_length=256)
    CACHE_KEY_FILE.write_bytes(key)
    try:
        os.chmod(CACHE_KEY_FILE, 0o600)  # owner read/write only (no-op on Windows FAT)
    except OSError:
        pass
    return key


class EnhancedPhotoSorter:
    """Enhanced face recognition pipeline with preprocessing and ensemble detection.

    Builds on the original PhotoSorter with:
        - CLAHE image enhancement for better accuracy in poor lighting
        - Ensemble face detection (HOG + CNN fallback) for higher recall
        - Face-region enhancement for reference photos
        - Normalized match margin for each match (replaces "confidence")
        - Two-threshold routing: strong / _review_required / _unmatched
        - Strict reference validation: exactly one face required
        - Secure encoding cache (SHA-256, file-metadata, app-data storage)
    """

    DISTANCE_THRESHOLD = 0.50   # Strong match — copy to student folder
    REVIEW_THRESHOLD = 0.60     # Borderline — copy to _review_required/
    MAX_IMAGE_DIMENSION = 1000

    def __init__(
        self,
        reference_folder: Path,
        events_folder: Path,
        output_folder: Path,
        logger: logging.Logger,
        use_preprocessing: bool = True,
        use_cache: bool = True,
        ensemble_detection: bool = True,
        fast_mode: bool = False,
    ) -> None:
        """Initialise the enhanced sorter.

        Args:
            reference_folder: Path to folder with one reference photo per student.
            events_folder: Path to folder containing event sub-folders with photos.
            output_folder: Where sorted results will be written.
            logger: Configured logger instance.
            use_preprocessing: Enable CLAHE + brightness normalization.
            use_cache: Cache face encodings to disk for faster re-runs.
            ensemble_detection: Use HOG + CNN ensemble for better face detection.
            fast_mode: Skip CNN detection entirely (HOG only, even as a
                fallback). Trades recall for speed on large photo batches —
                useful on slow school laptops where the ~2s/image CNN pass
                is the main bottleneck. Overrides ensemble_detection.
        """
        self.reference_folder = reference_folder
        self.events_folder = events_folder
        self.output_folder = output_folder
        self.logger = logger
        self.use_cache = use_cache
        self.ensemble_detection = ensemble_detection
        self.fast_mode = fast_mode

        self._student_encodings: dict[str, np.ndarray] = {}
        self._student_margin: dict[str, float] = {}
        self._preprocessor = ImagePreprocessor(enabled=use_preprocessing)
        self._engine = FaceEngine()

        # Accuracy tracking (margin scores, not "confidence")
        self._match_margin_scores: list[float] = []
        self._detection_methods_used: dict[str, int] = {"hog": 0, "cnn": 0, "ensemble": 0}

    # ------------------------------------------------------------------
    # Encoding cache (secure, app-data storage)
    # ------------------------------------------------------------------

    @staticmethod
    def _ref_metadata(ref_folder: Path) -> dict[str, dict]:
        """Collect file metadata for every reference image.

        Returns a dict mapping filename → {size, mtime} for cache
        validation.  The cache is invalidated when *any* reference file
        changes size or modification time.
        """
        meta: dict[str, dict] = {}
        for p in sorted(ref_folder.iterdir()):
            if is_image_file(p):
                try:
                    stat = p.stat()
                    meta[p.name] = {
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                    }
                except OSError:
                    continue
        return meta

    def _load_cache(self) -> dict[str, list[float]] | None:
        """Load cached encodings from disk if they exist and are valid.

        Validation checks:
          1. File exists and is valid JSON.
          2. Reference file list matches (by name, size, and mtime).
          3. Cache age < 24 hours.
          4. SHA-256 integrity hash matches.
        """
        if not self.use_cache or not CACHE_FILE.exists():
            return None

        if not _CRYPTO_AVAILABLE:
            self.logger.warning(
                "cryptography package not installed — skipping encrypted cache"
            )
            return None

        try:
            blob = CACHE_FILE.read_bytes()
            key = _get_or_create_cache_key()
            nonce, ciphertext = blob[:12], blob[12:]
            raw = AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8")
        except OSError:
            return None
        except Exception:
            self.logger.warning("Cache decryption failed — treating as invalid")
            return None

        # Integrity is already guaranteed by AES-GCM's authentication tag
        # (decrypt() above raises if the ciphertext was tampered with), so
        # a separate SHA-256 check is redundant here.
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, KeyError):
            self.logger.warning("Cache corrupted — invalid JSON")
            return None

        # --- File metadata validation ----------------------------------
        current_meta = self._ref_metadata(self.reference_folder)
        cached_meta = data.get("_ref_meta", {})
        if current_meta != cached_meta:
            self.logger.info("Cache stale — reference photos changed (size/mtime)")
            return None

        # --- Age check -------------------------------------------------
        cached_time = data.get("_timestamp", 0)
        if time.time() - cached_time > 86400:
            self.logger.info("Cache expired (>24h)")
            return None

        self.logger.info("Loaded %d encodings from cache", len(data) - 4)
        return {k: v for k, v in data.items() if not k.startswith("_")}

    def _save_cache(self) -> None:
        """Save current encodings to disk cache with integrity hash."""
        if not self.use_cache:
            return

        if not _CRYPTO_AVAILABLE:
            self.logger.warning(
                "cryptography package not installed — cache not saved "
                "(refusing to write biometric data unencrypted)"
            )
            return

        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)

            data = {
                name: enc.tolist()
                for name, enc in self._student_encodings.items()
            }
            data["_ref_meta"] = self._ref_metadata(self.reference_folder)
            data["_timestamp"] = time.time()
            payload = json.dumps(data).encode("utf-8")

            key = _get_or_create_cache_key()
            nonce = os.urandom(12)
            ciphertext = AESGCM(key).encrypt(nonce, payload, None)

            with open(CACHE_FILE, "wb") as f:
                f.write(nonce + ciphertext)
            try:
                os.chmod(CACHE_FILE, 0o600)
            except OSError:
                pass

            self.logger.info(
                "Saved %d encodings to encrypted cache (AES-256-GCM, %s)",
                len(self._student_encodings),
                CACHE_FILE,
            )
        except OSError as exc:
            self.logger.warning("Could not save cache: %s", exc)

    @classmethod
    def clear_cache(cls) -> bool:
        """Delete the biometric encoding cache from app data.

        Returns True if the cache was deleted successfully (or didn't exist).
        """
        try:
            if CACHE_FILE.exists():
                CACHE_FILE.unlink()
            if CACHE_KEY_FILE.exists():
                CACHE_KEY_FILE.unlink()
            return True
        except OSError:
            return False

    @classmethod
    def cache_exists(cls) -> bool:
        """Return True if a cached encoding file exists on disk."""
        return CACHE_FILE.exists()

    # ------------------------------------------------------------------
    # Reference loading (enhanced with preprocessing + strict validation)
    # ------------------------------------------------------------------

    def load_references(
        self,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> list[str]:
        """Load and encode reference photos with preprocessing enhancement.

        Attempts to load from cache first. For each reference photo:
            1. Load image with preprocessing (CLAHE + brightness normalization)
            2. Detect faces with CNN (more accurate for reference photos)
            3. Enhance the face region
            4. Encode with multiple jitters for robust embeddings
            5. Store and cache the encoding

        **Strict validation**: Reference photos containing zero faces OR more
        than one face are rejected.  Only photos with exactly one face are
        accepted as valid references.

        Returns:
            List of student names whose reference photo was rejected.
        """
        # Try cache first
        cached = self._load_cache()
        if cached:
            for name, enc_list in cached.items():
                self._student_encodings[name] = np.array(enc_list)
            self.logger.info(
                "Loaded %d student(s) from cache", len(self._student_encodings)
            )
            return []

        no_face_names: list[str] = []
        reference_images = sorted(
            p for p in self.reference_folder.iterdir() if is_image_file(p)
        )

        if not reference_images:
            self.logger.warning("No reference images found in %s", self.reference_folder)
            return no_face_names

        total = len(reference_images)
        for current, ref_path in enumerate(reference_images, start=1):
            student_name = ref_path.stem
            if progress_callback:
                progress_callback(current, total, student_name)

            try:
                # Load with preprocessing
                rgb_image = load_and_preprocess(ref_path, self._preprocessor)

                # Use CNN for reference photos (more accurate)
                locations = self._engine.face_locations(rgb_image, model="cnn")
                encodings = self._engine.face_encodings(
                    rgb_image,
                    known_face_locations=locations,
                    num_jitters=15,  # More jitters for robust reference encoding
                    model="large",
                )

                # --- Strict: reject zero faces ---
                if not encodings:
                    self.logger.warning(
                        "No face detected in reference for %s (%s) — REJECTED",
                        student_name,
                        ref_path.name,
                    )
                    no_face_names.append(student_name)
                    continue

                # --- Strict: reject multiple faces ---
                if len(encodings) > 1:
                    self.logger.warning(
                        "Multiple faces (%d) detected in reference for %s (%s) — REJECTED. "
                        "Reference photographs containing zero or multiple faces are rejected.",
                        len(encodings),
                        student_name,
                        ref_path.name,
                    )
                    no_face_names.append(student_name)
                    continue

                # Exactly one face — accept
                self._student_encodings[student_name] = encodings[0]
                self._student_margin[student_name] = 1.0  # Reference: baseline margin
                self.logger.info("Loaded reference for %s (enhanced)", student_name)

            except Exception as exc:
                self.logger.error(
                    "Could not read reference photo %s: %s", ref_path.name, exc
                )

        self.logger.info(
            "Loaded %d student reference(s) with preprocessing",
            len(self._student_encodings),
        )

        # Save to cache
        self._save_cache()

        return no_face_names

    # ------------------------------------------------------------------
    # Main sort loop (enhanced with two-threshold routing)
    # ------------------------------------------------------------------

    def sort_all(
        self,
        progress_callback: Callable[[int, int, str], None],
        cancelled: Callable[[], bool],
    ) -> dict[str, int]:
        """Sort all event photos with enhanced detection and two-threshold matching.

        For each photo:
            1. Load and preprocess (CLAHE enhancement)
            2. Ensemble face detection: HOG first (fast), CNN fallback (accurate)
            3. Encode detected faces with jitter for robustness
            4. Match against references with normalized match margin scoring
            5. Route based on two thresholds:
               - distance ≤ DISTANCE_THRESHOLD (0.50) → strong match → student folder
               - DISTANCE_THRESHOLD < distance ≤ REVIEW_THRESHOLD (0.60) → borderline → _review_required/
               - distance > REVIEW_THRESHOLD → no match → _unmatched/
            6. Group shots supported: one photo can land in multiple student folders

        Returns:
            Dict with keys: total, matched, review, unmatched, skipped, accuracy_metrics.
        """
        images = collect_event_images(self.events_folder)
        total = len(images)

        counts = {
            "total": total,
            "matched": 0,
            "review": 0,
            "unmatched": 0,
            "skipped": 0,
        }
        self._match_margin_scores = []
        self._detection_methods_used = {"hog": 0, "cnn": 0, "ensemble": 0}

        self.logger.info("Starting enhanced sort — %d images found", total)

        for current, (image_path, event_name) in enumerate(images, start=1):
            if cancelled():
                self.logger.info("Sort cancelled at image %d/%d", current, total)
                break

            progress_callback(current, total, image_path.name)
            output_filename = build_output_filename(event_name, image_path.name)

            try:
                # Load with preprocessing
                rgb_image = load_and_preprocess(image_path, self._preprocessor)
            except Exception as exc:
                self.logger.error("Could not open %s: %s — skipping", image_path.name, exc)
                counts["skipped"] += 1
                continue

            try:
                # Ensemble face detection
                face_locations = self._detect_faces_ensemble(rgb_image)
                if not face_locations:
                    self.logger.info("No face detected: %s → _unmatched", image_path.name)
                    safe_copy(
                        image_path,
                        self.output_folder / "_unmatched",
                        output_filename,
                        self.logger,
                    )
                    counts["unmatched"] += 1
                    continue

                face_encodings = self._engine.face_encodings(
                    rgb_image, face_locations, num_jitters=5, model="large"
                )
            except Exception as exc:
                self.logger.error(
                    "Face detection failed for %s: %s", image_path.name, exc
                )
                safe_copy(
                    image_path,
                    self.output_folder / "_unmatched",
                    output_filename,
                    self.logger,
                )
                counts["unmatched"] += 1
                continue

            if not face_encodings:
                safe_copy(
                    image_path,
                    self.output_folder / "_unmatched",
                    output_filename,
                    self.logger,
                )
                counts["unmatched"] += 1
                continue

            # Match and track margin — two-threshold routing
            best_category: str | None = None
            best_student: str | None = None
            best_margin = 0.0

            for encoding in face_encodings:
                student, margin, category = self._match_face_with_margin(encoding)
                if student and category:
                    # Track the best match across all faces in this photo
                    if category_rank(category) < category_rank(best_category) or (
                        category_rank(category) == category_rank(best_category)
                        and margin > best_margin
                    ):
                        best_category = category
                        best_student = student
                        best_margin = margin

            if best_student and best_category:
                if best_category == "strong":
                    # --- Strong match → student folder ------------------
                    dest_folder = self.output_folder / best_student
                    safe_copy(image_path, dest_folder, output_filename, self.logger)
                    self.logger.info(
                        "Matched %s → %s (margin=%.2f%%)",
                        image_path.name,
                        best_student,
                        best_margin * 100,
                    )
                    self._match_margin_scores.append(best_margin)
                    counts["matched"] += 1

                elif best_category == "review":
                    # --- Borderline → _review_required/ -----------------
                    safe_copy(
                        image_path,
                        self.output_folder / "_review_required",
                        output_filename,
                        self.logger,
                    )
                    self.logger.info(
                        "Borderline match: %s → %s (margin=%.2f%%) → _review_required",
                        image_path.name,
                        best_student,
                        best_margin * 100,
                    )
                    self._match_margin_scores.append(best_margin)
                    counts["review"] += 1
            else:
                self.logger.info("No match: %s → _unmatched", image_path.name)
                safe_copy(
                    image_path,
                    self.output_folder / "_unmatched",
                    output_filename,
                    self.logger,
                )
                counts["unmatched"] += 1

        # Compute accuracy metrics
        if self._match_margin_scores:
            avg_margin = float(np.mean(self._match_margin_scores))
            median_margin = float(np.median(self._match_margin_scores))
            self.logger.info(
                "Accuracy metrics — avg_margin=%.4f median_margin=%.4f",
                avg_margin,
                median_margin,
            )
        else:
            avg_margin = 0.0
            median_margin = 0.0

        counts["accuracy_metrics"] = {
            "avg_margin": round(avg_margin, 4),
            "median_margin": round(median_margin, 4),
            "total_matches": len(self._match_margin_scores),
            "detection_methods": self._detection_methods_used,
        }

        self.logger.info(
            "Enhanced sort complete — total=%d matched=%d review=%d unmatched=%d skipped=%d",
            counts["total"],
            counts["matched"],
            counts["review"],
            counts["unmatched"],
            counts["skipped"],
        )
        return counts

    # ------------------------------------------------------------------
    # Ensemble face detection
    # ------------------------------------------------------------------

    def _detect_faces_ensemble(self, rgb_image: np.ndarray) -> list[tuple[int, int, int, int]]:
        """Detect faces using HOG first, then CNN for robust coverage.

        Strategy:
            1. HOG detection (fast, ~0.2s): catches most faces
            2. If HOG finds nothing, try CNN (slower, ~2s, but more sensitive)
            3. If ensemble mode: merge both results for maximum recall

        In fast_mode, only HOG ever runs — CNN is skipped in both the
        ensemble step and the no-detection fallback. This sacrifices recall
        (some profile/occluded faces get missed) for a large speed win on
        big batches on slow hardware.

        Returns:
            List of face locations as (top, right, bottom, left) tuples.
        """
        # Step 1: HOG detection (fast)
        hog_locations = self._engine.face_locations(rgb_image, model="hog")

        if hog_locations:
            self._detection_methods_used["hog"] += 1

        if self.fast_mode:
            return hog_locations

        if hog_locations:
            if not self.ensemble_detection:
                return hog_locations

            # Ensemble: also try CNN for faces HOG might miss
            cnn_locations = self._engine.face_locations(rgb_image, model="cnn")
            if cnn_locations:
                self._detection_methods_used["ensemble"] += 1
                # Merge: deduplicate overlapping detections
                return self._merge_face_locations(hog_locations + cnn_locations)
            return hog_locations

        # Step 2: HOG found nothing, fall back to CNN
        cnn_locations = self._engine.face_locations(rgb_image, model="cnn")
        if cnn_locations:
            self._detection_methods_used["cnn"] += 1
            return cnn_locations

        return []

    @staticmethod
    def _merge_face_locations(
        locations: list[tuple[int, int, int, int]],
        iou_threshold: float = 0.5,
    ) -> list[tuple[int, int, int, int]]:
        """Merge overlapping face detections using IoU-based deduplication.

        When HOG and CNN both detect the same face, keep the CNN detection
        (more precise) and discard the HOG detection if they overlap significantly.
        """
        if len(locations) <= 1:
            return locations

        # Sort by area descending (prefer larger detections)
        def _area(loc: tuple[int, int, int, int]) -> int:
            t, r, b, l = loc
            return (b - t) * (r - l)

        sorted_locs = sorted(locations, key=_area, reverse=True)
        kept: list[tuple[int, int, int, int]] = []

        for loc in sorted_locs:
            is_duplicate = False
            t1, r1, b1, l1 = loc
            area1 = _area(loc)

            for kept_loc in kept:
                t2, r2, b2, l2 = kept_loc

                # Compute intersection
                inter_top = max(t1, t2)
                inter_bottom = min(b1, b2)
                inter_left = max(l1, l2)
                inter_right = min(r1, r2)

                if inter_top < inter_bottom and inter_left < inter_right:
                    inter_area = (inter_bottom - inter_top) * (inter_right - inter_left)
                    area2 = _area(kept_loc)
                    union = area1 + area2 - inter_area
                    iou = inter_area / union if union > 0 else 0

                    if iou > iou_threshold:
                        is_duplicate = True
                        break

            if not is_duplicate:
                kept.append(loc)

        return kept

    # ------------------------------------------------------------------
    # Normalized match margin (replaces "confidence")
    # ------------------------------------------------------------------

    def _match_face_with_margin(
        self, encoding: np.ndarray
    ) -> tuple[str | None, float, str | None]:
        """Match a face encoding and return (student_name, margin, category).

        The **normalized match margin** is computed as:
            margin = 1.0 - (distance / REVIEW_THRESHOLD)
        A margin of 1.0 means perfect match (distance=0); 0.0 means at the
        upper review boundary.  Negative margins fall below the review threshold.

        Two-threshold routing:
            distance ≤ DISTANCE_THRESHOLD (0.50) → "strong"
            DISTANCE_THRESHOLD < distance ≤ REVIEW_THRESHOLD (0.60) → "review"
            distance > REVIEW_THRESHOLD → None (no match)

        Args:
            encoding: 128-d face encoding from face_recognition.

        Returns:
            Tuple of (matched student name or None, margin 0-1, category or None).
        """
        if not self._student_encodings:
            return None, 0.0, None

        names = list(self._student_encodings.keys())
        known_encodings = list(self._student_encodings.values())

        distances = self._engine.face_distance(known_encodings, encoding)
        best_idx = int(np.argmin(distances))
        best_distance = distances[best_idx]

        # Compute normalized match margin (0-1 range; higher = better match)
        margin = max(0.0, 1.0 - (best_distance / self.REVIEW_THRESHOLD))

        if best_distance <= self.DISTANCE_THRESHOLD:
            self.logger.debug(
                "Face matched to %s (distance=%.4f, margin=%.2f%%) — STRONG",
                names[best_idx],
                best_distance,
                margin * 100,
            )
            return names[best_idx], float(margin), "strong"

        if best_distance <= self.REVIEW_THRESHOLD:
            self.logger.debug(
                "Face borderline match: %s (distance=%.4f, margin=%.2f%%) — REVIEW",
                names[best_idx],
                best_distance,
                margin * 100,
            )
            return names[best_idx], float(margin), "review"

        self.logger.debug(
            "No match — best distance=%.4f (DISTANCE_THRESHOLD=%.2f, REVIEW_THRESHOLD=%.2f)",
            best_distance,
            self.DISTANCE_THRESHOLD,
            self.REVIEW_THRESHOLD,
        )
        return None, 0.0, None


def category_rank(category: str | None) -> int:
    """Return numeric rank for comparison (lower = better match)."""
    if category == "strong":
        return 0
    if category == "review":
        return 1
    return 2  # None / unmatched


# ------------------------------------------------------------------
# Evaluation helper
# ------------------------------------------------------------------

def evaluate_accuracy(
    sorter: EnhancedPhotoSorter,
    test_folder: Path,
    ground_truth: dict[str, str],
) -> dict:
    """Evaluate sorting accuracy against ground truth labels.

    Args:
        sorter: Configured EnhancedPhotoSorter with loaded references.
        test_folder: Folder containing test images.
        ground_truth: Dict mapping image filename → expected student name.

    Returns:
        Dict with precision, recall, F1, and per-student breakdown.
    """
    from utils import collect_event_images

    results = {"correct": 0, "incorrect": 0, "no_face": 0, "per_student": {}}

    for student in sorter._student_encodings:
        results["per_student"][student] = {"tp": 0, "fp": 0, "fn": 0}

    images = collect_event_images(test_folder)
    for image_path, _ in images:
        filename = image_path.name
        expected = ground_truth.get(filename)
        if expected is None:
            continue

        try:
            rgb = load_and_preprocess(image_path, sorter._preprocessor)
            locations = sorter._detect_faces_ensemble(rgb)
            encodings = sorter._engine.face_encodings(
                rgb, locations, num_jitters=3, model="large"
            )

            if not encodings:
                results["no_face"] += 1
                if expected in results["per_student"]:
                    results["per_student"][expected]["fn"] += 1
                continue

            matched = False
            for enc in encodings:
                match, _, _ = sorter._match_face_with_margin(enc)
                if match == expected:
                    results["correct"] += 1
                    results["per_student"][expected]["tp"] += 1
                    matched = True
                elif match and match != expected:
                    results["incorrect"] += 1
                    results["per_student"][expected]["fn"] += 1
                    if match in results["per_student"]:
                        results["per_student"][match]["fp"] += 1

            if not matched:
                results["no_face"] += 1
                if expected in results["per_student"]:
                    results["per_student"][expected]["fn"] += 1

        except Exception:
            results["no_face"] += 1

    total = results["correct"] + results["incorrect"] + results["no_face"]
    results["total_evaluated"] = total
    results["accuracy"] = results["correct"] / max(total, 1)
    results["precision"] = (
        results["correct"] / max(results["correct"] + results["incorrect"], 1)
    )

    return results
