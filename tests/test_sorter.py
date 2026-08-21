import logging
import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

face_recognition_stub = types.ModuleType("face_recognition")


def load_image_file(*args, **kwargs):
    raise NotImplementedError


face_recognition_stub.load_image_file = load_image_file
face_recognition_stub.face_locations = lambda *args, **kwargs: []
face_recognition_stub.face_encodings = lambda *args, **kwargs: []
face_recognition_stub.face_distance = lambda *args, **kwargs: []
sys.modules.setdefault("face_recognition", face_recognition_stub)

numpy_stub = types.ModuleType("numpy")


class ndarray:  # pragma: no cover - simple stub for type annotations
    pass


numpy_stub.ndarray = ndarray
sys.modules.setdefault("numpy", numpy_stub)

pil_module = types.ModuleType("PIL")


class UnidentifiedImageError(Exception):
    pass


pil_module.Image = object
pil_module.UnidentifiedImageError = UnidentifiedImageError
sys.modules.setdefault("PIL", pil_module)

from sorter import PhotoSorter


class PhotoSorterConstructorTests(unittest.TestCase):
    def test_constructor_initializes_expected_state(self) -> None:
        logger = logging.getLogger("kindersort-test")
        sorter = PhotoSorter(
            Path("/tmp/reference"),
            Path("/tmp/events"),
            Path("/tmp/output"),
            logger,
        )

        self.assertEqual(sorter.reference_folder, Path("/tmp/reference"))
        self.assertEqual(sorter.events_folder, Path("/tmp/events"))
        self.assertEqual(sorter.output_folder, Path("/tmp/output"))
        self.assertIs(sorter.logger, logger)
        self.assertEqual(sorter.MAX_IMAGE_DIMENSION, 1000)
        self.assertEqual(sorter._student_encodings, {})


if __name__ == "__main__":
    unittest.main()
