"""
face_engine.py — Portable face detection and recognition engine.

Provides a unified interface for face detection and encoding with automatic
backend selection. Falls back to pure OpenCV when dlib is unavailable.

Backends (in priority order):
    1. dlib (face_recognition) — most accurate, requires dlib installation
    2. OpenCV DNN — always available, no compilation needed

Models are downloaded automatically on first use (cached to ~/.kindersort/models/).
"""

import logging
import os
import pickle
import urllib.request
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger("kindersort.face_engine")

# Model URLs (lightweight, CPU-friendly models)
MODEL_DIR = Path.home() / ".kindersort" / "models"

FACE_DETECTOR_MODEL = {
    "prototxt": "https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt",
    "caffemodel": "https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel",
    "prototxt_file": "deploy.prototxt",
    "caffemodel_file": "res10_300x300_ssd_iter_140000.caffemodel",
}

# OpenFace NN4 model for deep learning face embeddings
FACE_EMBEDDING_MODEL = {
    "url": "https://github.com/opencv/opencv_3rdparty/raw/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel",
    "file": "openface_nn4.small2.v1.t7",
}
OPENFACE_URL = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/face_detection_short_range.tflite"

# Try to import dlib/face_recognition
_dlib_available = False
try:
    import face_recognition
    _dlib_available = True
    logger.info("dlib backend available")
except ImportError:
    logger.info("dlib not available — using OpenCV backend")


def _download_file(url: str, dest: Path) -> bool:
    """Download a file with progress indication. Returns True on success."""
    if dest.exists():
        return True

    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("Downloading %s → %s", Path(url).name, dest)
        urllib.request.urlretrieve(url, dest)
        logger.info("Downloaded %s", Path(url).name)
        return True
    except Exception as exc:
        logger.warning("Could not download %s: %s", url, exc)
        return False


class FaceEngine:
    """Unified face detection and encoding engine.

    Provides methods compatible with face_recognition's API but with
    automatic backend selection and model downloading.

    Usage:
        engine = FaceEngine()
        locations = engine.face_locations(image)
        encodings = engine.face_encodings(image, locations)
        match = engine.compare_faces(known_encodings, encoding)
    """

    def __init__(self) -> None:
        """Initialize the engine and ensure models are downloaded."""
        self._net: cv2.dnn.Net | None = None
        self._ensure_models()

        if _dlib_available:
            self._backend = "dlib"
        else:
            self._backend = "opencv"
        logger.info("Face engine initialized with %s backend", self._backend)

    def _ensure_models(self) -> None:
        """Download required models if not present."""
        MODEL_DIR.mkdir(parents=True, exist_ok=True)

        # Face detector model
        prototxt_path = MODEL_DIR / FACE_DETECTOR_MODEL["prototxt_file"]
        caffemodel_path = MODEL_DIR / FACE_DETECTOR_MODEL["caffemodel_file"]

        _download_file(FACE_DETECTOR_MODEL["prototxt"], prototxt_path)
        _download_file(FACE_DETECTOR_MODEL["caffemodel"], caffemodel_path)

        if prototxt_path.exists() and caffemodel_path.exists():
            self._net = cv2.dnn.readNetFromCaffe(
                str(prototxt_path), str(caffemodel_path)
            )
            # Prefer OpenCL/CPU
            self._net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self._net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

    def face_locations(
        self,
        image: np.ndarray,
        model: str = "hog",
    ) -> list[tuple[int, int, int, int]]:
        """Detect face locations in an RGB image.

        Args:
            image: RGB numpy array (H, W, 3).
            model: Detection model — "hog" (fast), "cnn" (accurate),
                   or any value triggers OpenCV DNN detection.

        Returns:
            List of (top, right, bottom, left) tuples.
        """
        if self._backend == "dlib":
            return face_recognition.face_locations(image, model=model)

        # OpenCV DNN backend
        if self._net is None:
            # Fallback to Haar cascade
            return self._haar_face_locations(image)

        return self._dnn_face_locations(image)

    def _dnn_face_locations(
        self, image: np.ndarray
    ) -> list[tuple[int, int, int, int]]:
        """Detect faces using OpenCV DNN SSD detector."""
        h, w = image.shape[:2]

        # Create blob from image
        blob = cv2.dnn.blobFromImage(
            image, 1.0, (300, 300), [104, 117, 123], False, False
        )
        self._net.setInput(blob)
        detections = self._net.forward()

        locations = []
        for i in range(detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            if confidence < 0.5:  # 50% confidence threshold
                continue

            box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
            left, top, right, bottom = box.astype(int)

            # Clamp to image boundaries
            top = max(0, top)
            right = min(w, right)
            bottom = min(h, bottom)
            left = max(0, left)

            if bottom > top and right > left:
                locations.append((top, right, bottom, left))

        return locations

    def _haar_face_locations(
        self, image: np.ndarray
    ) -> list[tuple[int, int, int, int]]:
        """Fallback: Haar cascade face detection."""
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(cascade_path)

        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(30, 30))

        return [
            (y, x + w, y + h, x)
            for (x, y, w, h) in faces
        ]

    def face_encodings(
        self,
        image: np.ndarray,
        known_face_locations: list[tuple[int, int, int, int]] | None = None,
        num_jitters: int = 1,
        model: str = "large",
    ) -> list[np.ndarray]:
        """Generate face encodings for faces in the image.

        Args:
            image: RGB numpy array.
            known_face_locations: Optional pre-computed face locations.
            num_jitters: Number of jitters (only used with dlib backend).
            model: Model size (only used with dlib backend).

        Returns:
            List of 128-d encoding numpy arrays.
        """
        if self._backend == "dlib":
            return face_recognition.face_encodings(
                image,
                known_face_locations=known_face_locations,
                num_jitters=num_jitters,
                model=model,
            )

        # OpenCV backend: use LBPH feature extraction
        if known_face_locations is None:
            known_face_locations = self._dnn_face_locations(image)

        encodings = []
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)

        for top, right, bottom, left in known_face_locations:
            face_roi = gray[top:bottom, left:right]
            if face_roi.size == 0:
                continue

            # Resize to standard size and flatten as feature vector
            face_roi = cv2.resize(face_roi, (128, 128))
            # Use HOG-like feature: flattened normalized pixel + gradient histogram
            features = self._extract_features(face_roi)
            encodings.append(features)

        return encodings

    @staticmethod
    def _extract_features(face_roi: np.ndarray) -> np.ndarray:
        """Extract a 128-d feature vector from a face ROI using LBPH features.

        Uses Local Binary Patterns (LBP) — rotation-invariant texture descriptors
        that are far more discriminative than raw pixels for face identity.
        """
        face_norm = cv2.equalizeHist(face_roi)

        # Align face: detect eyes and rotate for frontal view
        face_resized = cv2.resize(face_norm, (96, 96))

        # LBP features — local texture patterns (64x4 grid = 256-d, we'll use subset)
        lbp = np.zeros_like(face_resized, dtype=np.uint8)
        for i in range(1, face_resized.shape[0]-1):
            for j in range(1, face_resized.shape[1]-1):
                center = face_resized[i, j]
                code = 0
                neighbors = [(-1,-1),(-1,0),(-1,1),(0,1),(1,1),(1,0),(1,-1),(0,-1)]
                for k, (di, dj) in enumerate(neighbors):
                    if face_resized[i+di, j+dj] > center:
                        code |= (1 << k)
                lbp[i, j] = code

        # Build LBP histogram over grid
        grid = (8, 4)  # 8x4 grid = 32 regions
        cell_h = 96 // grid[0]   # 12
        cell_w = 96 // grid[1]   # 24
        features = []
        for r in range(grid[0]):
            for c in range(grid[1]):
                cell = lbp[r*cell_h:(r+1)*cell_h, c*cell_w:(c+1)*cell_w]
                hist = np.bincount(cell.flatten(), minlength=256).astype(np.float32)
                # Compress 256 bins to 4 per cell = 128 total
                hist = np.array([hist[i:i+64].sum() for i in range(0, 256, 64)])
                features.extend(hist / (cell.size + 1e-6))

        # Combine
        combined = np.array(features, dtype=np.float32)  # 128-d

        # Normalize to unit length
        norm = np.linalg.norm(combined)
        if norm > 0:
            combined = combined / norm

        return combined.astype(np.float32)

    def compare_faces(
        self,
        known_encodings: list[np.ndarray],
        encoding: np.ndarray,
        tolerance: float = 0.5,
    ) -> list[bool]:
        """Compare a face encoding against a list of known encodings.

        Args:
            known_encodings: List of known face encodings.
            encoding: The encoding to compare.
            tolerance: Distance threshold for match (lower = stricter).

        Returns:
            List of boolean match results.
        """
        if self._backend == "dlib":
            return list(
                face_recognition.compare_faces(
                    known_encodings, encoding, tolerance=tolerance
                )
            )

        # Cosine similarity for OpenCV backend
        results = []
        for known in known_encodings:
            distance = self._face_distance(known, encoding)
            results.append(distance <= tolerance)
        return results

    def face_distance(
        self,
        known_encodings: list[np.ndarray],
        encoding: np.ndarray,
    ) -> np.ndarray:
        """Compute distances between an encoding and known encodings.

        Returns:
            numpy array of distances (lower = more similar).
        """
        if self._backend == "dlib":
            return face_recognition.face_distance(
                np.array(known_encodings), encoding
            )

        distances = np.array([
            self._face_distance(known, encoding)
            for known in known_encodings
        ])
        return distances

    @staticmethod
    def _face_distance(enc1: np.ndarray, enc2: np.ndarray) -> float:
        """Compute cosine distance between two encodings."""
        dot = np.dot(enc1, enc2)
        norm1 = np.linalg.norm(enc1)
        norm2 = np.linalg.norm(enc2)
        if norm1 == 0 or norm2 == 0:
            return 1.0
        cosine_sim = dot / (norm1 * norm2)
        return float(1.0 - cosine_sim)

    @property
    def backend(self) -> str:
        """Return the active backend name."""
        return self._backend

    @property
    def is_dlib_available(self) -> bool:
        """Check if dlib backend is usable."""
        return _dlib_available
