"""
sorter.py — Face recognition logic for KinderSort Lite.
"""

import hashlib
import logging
import math
import pickle
from collections.abc import Callable
from pathlib import Path

import cv2
import face_recognition
import numpy as np
from PIL import Image, ImageEnhance, UnidentifiedImageError

from utils import build_output_filename, collect_event_images, is_image_file, safe_copy

_MODEL_DIR = Path(__file__).parent / "models"
_PROTOTXT = _MODEL_DIR / "deploy.prototxt"
_CAFFEMODEL = _MODEL_DIR / "res10_300x300_ssd_iter_140000.caffemodel"


class PhotoSorter:
    DISTANCE_THRESHOLD = 0.55
    MAX_IMAGE_DIMENSION = 1000
    LOW_LIGHT_BRIGHTNESS_THRESHOLD = 70
    OPENCV_CONFIDENCE_THRESHOLD = 0.5
    CACHE_FILENAME = ".kindersort_cache.pkl"

    def __init__(self, reference_folder: Path, events_folder: Path, output_folder: Path,
                 logger: logging.Logger, enhance_images: bool = True, use_cache: bool = True):
        self.reference_folder = reference_folder
        self.events_folder = events_folder
        self.output_folder = output_folder
        self.logger = logger
        self.enhance_images = enhance_images
        self.use_cache = use_cache
        self._student_encodings: dict[str, np.ndarray] = {}
        self._opencv_net = None

    def _get_opencv_net(self):
        if self._opencv_net is not None:
            return self._opencv_net
        if not _PROTOTXT.exists() or not _CAFFEMODEL.exists():
            self.logger.warning("OpenCV DNN model files not found. Run: python download_model.py")
            return None
        self.logger.info("Loading OpenCV DNN face detector...")
        self._opencv_net = cv2.dnn.readNetFromCaffe(str(_PROTOTXT), str(_CAFFEMODEL))
        self._opencv_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self._opencv_net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        return self._opencv_net

    def _detect_faces_opencv(self, rgb_image: np.ndarray) -> list[tuple]:
        net = self._get_opencv_net()
        if net is None:
            return []
        bgr = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)
        h, w = bgr.shape[:2]
        blob = cv2.dnn.blobFromImage(cv2.resize(bgr, (300, 300)), 1.0, (300, 300), (104.0, 177.0, 123.0))
        net.setInput(blob)
        detections = net.forward()
        locations = []
        for i in range(detections.shape[2]):
            confidence = float(detections[0, 0, i, 2])
            if confidence < self.OPENCV_CONFIDENCE_THRESHOLD:
                continue
            box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
            startX, startY, endX, endY = box.astype(int)
            startX, startY = max(0, startX), max(0, startY)
            endX, endY = min(w, endX), min(h, endY)
            if endX <= startX or endY <= startY:
                continue
            locations.append((startY, endX, endY, startX))
        return locations

    def _detect_faces_with_fallback(self, rgb_image: np.ndarray) -> list[tuple]:
        locations = self._detect_faces_opencv(rgb_image)
        if locations:
            return locations
        self.logger.debug("OpenCV DNN found no faces, trying dlib HOG...")
        locations = face_recognition.face_locations(rgb_image, model="hog")
        if locations:
            return locations
        self.logger.debug("HOG found no faces, trying dlib CNN...")
        return face_recognition.face_locations(rgb_image, model="cnn")

    def _cache_path(self) -> Path:
        return self.reference_folder / self.CACHE_FILENAME

    def _file_hash(self, path: Path) -> str:
        return hashlib.md5(path.read_bytes()).hexdigest()

    def _load_cache(self) -> dict:
        cache_path = self._cache_path()
        if not cache_path.exists():
            return {}
        try:
            with cache_path.open("rb") as f:
                data = pickle.load(f)
            if isinstance(data, dict):
                self.logger.info(f"Loaded embedding cache from {cache_path.name}")
                return data
        except Exception:
            pass
        return {}

    def _save_cache(self, cache: dict) -> None:
        try:
            with self._cache_path().open("wb") as f:
                pickle.dump(cache, f)
            self.logger.info(f"Embedding cache saved to {self.CACHE_FILENAME}")
        except Exception as e:
            self.logger.warning(f"Could not save cache: {e}")

    def load_references(self, progress_callback: Callable[[int, int, str], None] | None = None) -> list[str]:
        no_face_names = []
        reference_images = sorted(p for p in self.reference_folder.iterdir() if is_image_file(p))
        if not reference_images:
            return no_face_names

        cache = self._load_cache() if self.use_cache else {}
        updated_cache = {}
        cache_hits = 0

        for current, ref_path in enumerate(reference_images, start=1):
            student_name = ref_path.stem
            if progress_callback:
                progress_callback(current, len(reference_images), student_name)

            file_hash = self._file_hash(ref_path)
            cache_key = (ref_path.name, file_hash)

            if self.use_cache and cache_key in cache:
                encoding = cache[cache_key]
                if encoding is not None:
                    self._student_encodings[student_name] = encoding
                    cache_hits += 1
                else:
                    no_face_names.append(student_name)
                updated_cache[cache_key] = encoding
                continue

            try:
                image = face_recognition.load_image_file(str(ref_path))
                pil_image = Image.fromarray(image)
                aligned = self._align_face(pil_image, ref_path.name)
                image = np.array(aligned)

                locations = self._detect_faces_with_fallback(image)
                encodings = face_recognition.face_encodings(image, known_face_locations=locations,
                                                            num_jitters=10, model="large")
                if not encodings:
                    no_face_names.append(student_name)
                    updated_cache[cache_key] = None
                    continue
                self._student_encodings[student_name] = encodings[0]
                updated_cache[cache_key] = encodings[0]
                self.logger.info(f"Encoded reference for {student_name}")
            except Exception as e:
                self.logger.error(f"Could not read {ref_path.name}: {e}")

        if self.use_cache:
            self._save_cache(updated_cache)
        return no_face_names

    def sort_all(self, progress_callback: Callable[[int, int, str], None],
                 cancelled: Callable[[], bool]) -> dict[str, int]:
        images = collect_event_images(self.events_folder)
        total = len(images)
        counts = {"total": total, "matched": 0, "unmatched": 0, "skipped": 0}

        for current, (image_path, event_name) in enumerate(images, start=1):
            if cancelled():
                break
            progress_callback(current, total, image_path.name)
            output_filename = build_output_filename(event_name, image_path.name)

            try:
                rgb_image = self._load_and_resize(image_path)
            except UnidentifiedImageError:
                safe_copy(image_path, self.output_folder / "_unmatched", output_filename, self.logger)
                counts["unmatched"] += 1
                continue
            except Exception:
                counts["skipped"] += 1
                continue

            try:
                face_locations = self._detect_faces_with_fallback(rgb_image)
                face_encodings = face_recognition.face_encodings(rgb_image, face_locations,
                                                                 num_jitters=3, model="large")
            except Exception:
                safe_copy(image_path, self.output_folder / "_unmatched", output_filename, self.logger)
                counts["unmatched"] += 1
                continue

            if not face_encodings:
                safe_copy(image_path, self.output_folder / "_unmatched", output_filename, self.logger)
                counts["unmatched"] += 1
                continue

            matched_students = set()
            for encoding in face_encodings:
                match = self._match_face(encoding)
                if match:
                    matched_students.add(match)

            if matched_students:
                for student_name in matched_students:
                    safe_copy(image_path, self.output_folder / student_name, output_filename, self.logger)
                counts["matched"] += 1
            else:
                safe_copy(image_path, self.output_folder / "_unmatched", output_filename, self.logger)
                counts["unmatched"] += 1

        return counts

    def _load_and_resize(self, image_path: Path) -> np.ndarray:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            w, h = img.size
            if max(w, h) > self.MAX_IMAGE_DIMENSION:
                scale = self.MAX_IMAGE_DIMENSION / max(w, h)
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            if self.enhance_images:
                img = self._enhance_low_light(img, image_path.name)
            return np.array(img)

    def _enhance_low_light(self, img: Image.Image, filename: str) -> Image.Image:
        mean_brightness = float(np.array(img.convert("L")).mean())
        if mean_brightness < self.LOW_LIGHT_BRIGHTNESS_THRESHOLD:
            boost = min(120.0 / max(mean_brightness, 1.0), 4.0)
            arr = np.array(img).astype(np.float32) / 255.0
            arr = np.power(arr, 0.6)
            gamma_img = Image.fromarray((arr * 255).clip(0, 255).astype(np.uint8))
            return ImageEnhance.Brightness(gamma_img).enhance(boost * 0.5)
        return img

    def _align_face(self, img: Image.Image, filename: str) -> Image.Image:
        arr = np.array(img)
        landmarks_list = face_recognition.face_landmarks(arr)
        if not landmarks_list:
            return img
        landmarks = landmarks_list[0]
        left_pts = landmarks.get("left_eye", [])
        right_pts = landmarks.get("right_eye", [])
        if not left_pts or not right_pts:
            return img
        lx = sum(p[0] for p in left_pts) / len(left_pts)
        ly = sum(p[1] for p in left_pts) / len(left_pts)
        rx = sum(p[0] for p in right_pts) / len(right_pts)
        ry = sum(p[1] for p in right_pts) / len(right_pts)
        angle = math.degrees(math.atan2(ry - ly, rx - lx))
        if abs(angle) < 1.0:
            return img
        return img.rotate(-angle, resample=Image.BICUBIC, expand=False)

    def _match_face(self, encoding: np.ndarray) -> str | None:
        if not self._student_encodings:
            return None
        names = list(self._student_encodings.keys())
        known = np.array(list(self._student_encodings.values()))
        distances = face_recognition.face_distance(known, encoding)
        best_idx = int(np.argmin(distances))
        if distances[best_idx] <= self.DISTANCE_THRESHOLD:
            return names[best_idx]
        return None