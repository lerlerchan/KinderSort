"""
preprocessor.py — Image enhancement pipeline for improving face recognition accuracy.

Applies CLAHE contrast enhancement, brightness normalization, and optional
face alignment to improve recognition rates, especially in challenging lighting
conditions common in kindergarten environments (indoor, mixed lighting).
"""

import logging
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger("kindersort.preprocessor")


class ImagePreprocessor:
    """Image enhancement pipeline for face recognition preprocessing.

    Applies a sequence of transformations that normalize image quality
    before face detection and encoding, improving accuracy across varying
    lighting conditions without requiring GPU.
    """

    CLAHE_CLIP_LIMIT = 2.0
    CLAHE_TILE_SIZE = (8, 8)
    TARGET_BRIGHTNESS = 128
    MAX_DIMENSION = 800  # Resize before enhancement for speed

    def __init__(self, enabled: bool = True) -> None:
        """Initialise the preprocessor.

        Args:
            enabled: If False, all methods pass through without modification.
        """
        self.enabled = enabled
        self._clahe = cv2.createCLAHE(
            clipLimit=self.CLAHE_CLIP_LIMIT,
            tileGridSize=self.CLAHE_TILE_SIZE,
        ) if enabled else None

    def enhance(self, image: np.ndarray) -> np.ndarray:
        """Apply the full enhancement pipeline to a BGR/grayscale image.

        Pipeline:
            1. Downscale if too large (speed)
            2. Convert to LAB and apply CLAHE on L channel
            3. Normalize brightness
            4. Optional sharpening

        Args:
            image: numpy array (H, W, 3) BGR or (H, W) grayscale.

        Returns:
            Enhanced image in the same format.
        """
        if not self.enabled:
            return image

        try:
            # Step 1: Resize if too large
            image = self._resize_if_large(image)

            # Step 2: Convert to LAB for better colour-space enhancement
            if len(image.shape) == 3 and image.shape[2] == 3:
                lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
                l_channel, a_channel, b_channel = cv2.split(lab)

                # Apply CLAHE to L channel
                l_channel = self._clahe.apply(l_channel)

                merged = cv2.merge([l_channel, a_channel, b_channel])
                enhanced = cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
            elif len(image.shape) == 2:
                enhanced = self._clahe.apply(image)
            else:
                enhanced = image

            # Step 3: Brightness normalization
            enhanced = self._normalize_brightness(enhanced)

            return enhanced

        except Exception:
            logger.debug("Preprocessing failed, returning original image")
            return image

    def enhance_rgb(self, rgb_image: np.ndarray) -> np.ndarray:
        """Enhance an RGB image (face_recognition format).

        face_recognition.load_image_file returns RGB, so this converts
        BGR → RGB after OpenCV processing.

        Args:
            rgb_image: numpy array (H, W, 3) in RGB format.

        Returns:
            Enhanced RGB numpy array.
        """
        if not self.enabled:
            return rgb_image

        bgr = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)
        enhanced_bgr = self.enhance(bgr)
        return cv2.cvtColor(enhanced_bgr, cv2.COLOR_BGR2RGB)

    @staticmethod
    def _resize_if_large(image: np.ndarray, max_dim: int = 800) -> np.ndarray:
        """Downscale image if its longest side exceeds max_dim."""
        h, w = image.shape[:2]
        longest = max(h, w)
        if longest > max_dim:
            scale = max_dim / longest
            new_size = (int(w * scale), int(h * scale))
            return cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)
        return image

    @staticmethod
    def _normalize_brightness(image: np.ndarray) -> np.ndarray:
        """Adjust brightness so mean pixel value approaches target."""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        mean_brightness = np.mean(gray)
        if mean_brightness < 40 or mean_brightness > 220:
            # Extreme case — skip normalization to avoid artifacts
            return image

        target = 128.0
        alpha = target / max(mean_brightness, 1.0)
        alpha = max(0.6, min(1.4, alpha))  # Clamp to avoid over-correction

        return cv2.convertScaleAbs(image, alpha=alpha, beta=0)

    @staticmethod
    def enhance_face_region(
        rgb_image: np.ndarray,
        face_location: tuple[int, int, int, int],
    ) -> np.ndarray:
        """Extract and enhance just the face region from an RGB image.

        Used for reference photo encoding to get higher-quality face embeddings.

        Args:
            rgb_image: Full RGB image.
            face_location: (top, right, bottom, left) from face_recognition.

        Returns:
            Enhanced face region as RGB numpy array, or original if extraction fails.
        """
        try:
            top, right, bottom, left = face_location
            # Add padding around face
            h, w = rgb_image.shape[:2]
            pad = int((bottom - top) * 0.2)
            top = max(0, top - pad)
            right = min(w, right + pad)
            bottom = min(h, bottom + pad)
            left = max(0, left - pad)

            face_crop = rgb_image[top:bottom, left:right]

            # Enhance the face crop
            bgr = cv2.cvtColor(face_crop, cv2.COLOR_RGB2BGR)
            lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
            l_channel, a_channel, b_channel = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l_channel = clahe.apply(l_channel)
            enhanced_bgr = cv2.cvtColor(
                cv2.merge([l_channel, a_channel, b_channel]),
                cv2.COLOR_LAB2BGR,
            )
            return cv2.cvtColor(enhanced_bgr, cv2.COLOR_BGR2RGB)

        except Exception:
            return rgb_image


def load_and_preprocess(image_path: Path, preprocessor: ImagePreprocessor | None = None) -> np.ndarray:
    """Load an image and apply preprocessing.

    Args:
        image_path: Path to the image file.
        preprocessor: Optional preprocessor; if None, just loads and returns.

    Returns:
        RGB numpy array ready for face_recognition.
    """
    from PIL import Image as PILImage

    with PILImage.open(image_path) as img:
        img = img.convert("RGB")
        rgb = np.array(img)

    if preprocessor and preprocessor.enabled:
        rgb = preprocessor.enhance_rgb(rgb)

    return rgb
