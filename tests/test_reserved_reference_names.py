"""Reserved reference-name regressions using synthetic images and mocked faces."""

import importlib.util
import itertools
import logging
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, Mock, patch


class TestReservedReferenceNames(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.references = self.root / "references"
        self.events = self.root / "events"
        self.output = self.root / "output"
        for folder in (self.references, self.events, self.output):
            folder.mkdir()

        self.encoding = [0.0] * 128
        self.faces = Mock()
        self.faces.load_image_file.return_value = [[[20, 40, 60]]]
        self.faces.face_locations.return_value = [(0, 8, 8, 0)]
        self.faces.face_encodings.return_value = [self.encoding]
        self.faces.face_distance.side_effect = lambda known, face: [0.0] * len(known)

        # Only image-processing boundaries are simulated. The real sorter still
        # enumerates files, derives names, loads references, matches and copies.
        numpy = ModuleType("numpy")
        numpy.ndarray = list  # Resolve sorter's runtime type annotations.
        numpy.array = Mock(side_effect=lambda value: value)
        numpy.argmin = Mock(
            side_effect=lambda values: min(range(len(values)), key=values.__getitem__)
        )
        pillow = ModuleType("PIL")
        image_api = ModuleType("PIL.Image")
        image = Mock()
        image.size = (8, 8)
        image.convert.return_value = image
        opened_image = MagicMock()
        opened_image.__enter__.return_value = image
        image_api.open = Mock(return_value=opened_image)
        pillow.Image = image_api
        pillow.UnidentifiedImageError = type("UnidentifiedImageError", (OSError,), {})

        # Restore all dependency entries immediately after importing the isolated
        # sorter. Its globals retain these substitutes without leaking imports.
        spec = importlib.util.spec_from_file_location(
            "_reserved_names_sorter", Path(__file__).resolve().parents[1] / "sorter.py"
        )
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {
            "face_recognition": self.faces,
            "numpy": numpy,
            "PIL": pillow,
            "PIL.Image": image_api,
        }):
            spec.loader.exec_module(module)
        self.sorter_class = module.PhotoSorter
        self.logger = Mock(spec=logging.Logger)
        self.sorter = self.new_sorter()

    def new_sorter(self):
        return self.sorter_class(
            self.references, self.events, self.output, self.logger
        )

    def image(self, folder, filename):
        path = folder / filename
        # Synthetic bytes only: decoding is handled by the external API mocks.
        path.write_bytes(b"synthetic image fixture: " + filename.encode("utf-8"))
        return path

    def assert_rejected_before_encoding(self, filename, sorter=None):
        sorter = sorter or self.sorter
        error = None
        try:
            sorter.load_references()
        except ValueError as exc:
            error = exc
        # Independent checks expose encoding even when no exception was raised.
        with self.subTest(check="reject entire reference set"):
            self.assertIsInstance(error, ValueError, "Invalid student name must raise ValueError")
            self.assertIn(filename, str(error))
        with self.subTest(check="reject before face encoding"):
            self.faces.face_encodings.assert_not_called()
        return error

    def assert_normal_name(self, filename):
        self.image(self.references, filename)
        self.image(self.events, "event.jpg")
        self.assertEqual(self.sorter.load_references(), [])
        self.faces.face_encodings.assert_called_once()
        result = self.sorter.sort_all(lambda *args: None, lambda: False)
        self.assertEqual(result, {"total": 1, "matched": 1, "unmatched": 0, "skipped": 0})
        self.assertEqual(
            (self.output / Path(filename).stem / "events__event.jpg").read_bytes(),
            (self.events / "event.jpg").read_bytes(),
        )

    def test_t01_normal_english_name(self):
        self.assert_normal_name("Alice.jpg")

    def test_t02_normal_chinese_name(self):
        self.assert_normal_name("王小明.png")

    def test_t03_reserved_unmatched(self):
        self.image(self.references, "_unmatched.jpg")
        self.assert_rejected_before_encoding("_unmatched.jpg")

    def test_t04_case_insensitive_unmatched(self):
        for filename in ("_UNMATCHED.jpg", "_UnMatched.png"):
            with self.subTest(filename=filename):
                path = self.image(self.references, filename)
                try:
                    self.faces.reset_mock()
                    self.assert_rejected_before_encoding(filename, self.new_sorter())
                finally:
                    path.unlink()

    def test_t05_reserved_log_filename(self):
        self.image(self.references, "kindersort_log.txt.jpg")
        self.assert_rejected_before_encoding("kindersort_log.txt.jpg")

    def test_t06_case_insensitive_log_filename(self):
        self.image(self.references, "KINDERSORT_LOG.TXT.png")
        self.assert_rejected_before_encoding("KINDERSORT_LOG.TXT.png")

    def test_t07_trailing_period_or_space(self):
        for filename in ("_unmatched..jpg", "Student .jpg", "Student..png"):
            with self.subTest(filename=filename):
                path = self.image(self.references, filename)
                try:
                    self.faces.reset_mock()
                    self.assert_rejected_before_encoding(filename, self.new_sorter())
                finally:
                    path.unlink()

    def test_t08_mixed_set_is_atomic_for_every_enumeration_order(self):
        self.image(self.events, "event.jpg")
        original_iterdir = Path.iterdir
        # Both lexical positions matter because load_references sorts its input.
        for names in (("Alice.jpg", "Bob.jpg"), ("alice.jpg", "bob.jpg")):
            paths = [self.image(self.references, name) for name in (*names, "_unmatched.jpg")]
            try:
                for order in itertools.permutations(paths):
                    with self.subTest(order=[p.name for p in order]):
                        sorter = self.new_sorter()
                        self.faces.reset_mock()

                        def enumerate_paths(folder):
                            if folder == self.references:
                                return iter(order)
                            return original_iterdir(folder)

                        with patch.object(Path, "iterdir", enumerate_paths):
                            self.assert_rejected_before_encoding("_unmatched.jpg", sorter)
                        # Probe retained state through public sorting behavior.
                        # This deliberate post-error probe uses only temporary data.
                        result = sorter.sort_all(lambda *args: None, lambda: False)
                        self.assertEqual(result["matched"], 0, "No students may remain partially loaded")
            finally:
                for path in paths:
                    path.unlink()

    def test_t09_error_identifies_file_reason_and_remedy(self):
        for filename in ("_unmatched.jpg", "kindersort_log.txt.jpg", "Student .jpg"):
            with self.subTest(filename=filename):
                path = self.image(self.references, filename)
                try:
                    with self.assertRaises(ValueError) as raised:
                        self.new_sorter().load_references()
                    message = str(raised.exception)
                    self.assertIn(filename, message)
                    reason = "must not end with a period or space" if filename == "Student .jpg" else "reserved"
                    self.assertIn(reason, message.lower())
                    self.assertRegex(message.lower(), r"\bplease rename\b")
                finally:
                    path.unlink()

    def test_t10_inputs_and_existing_output_are_preserved(self):
        self.image(self.references, "Alice.jpg")
        self.image(self.references, "_unmatched.jpg")
        self.image(self.events, "event.jpg")
        (self.output / "Alice").mkdir()
        (self.output / "Alice" / "events__event.jpg").write_bytes(b"existing photo")
        (self.output / "kindersort_log.txt").write_bytes(b"existing log")

        def snapshot():
            return {
                path.relative_to(self.root).as_posix(): (
                    path.read_bytes(), path.stat().st_mtime_ns
                ) if path.is_file() else None
                for path in self.root.rglob("*")
            }

        before = snapshot()
        try:
            # The public pipeline calls sort_all only after load_references succeeds.
            # PhotoSorter has no combined load-and-sort method or GUI entry point.
            with self.assertRaises(ValueError):
                self.sorter.load_references()
                self.sorter.sort_all(lambda *args: None, lambda: False)
        finally:
            self.assertEqual(snapshot(), before, "Inputs and output must remain unchanged")


if __name__ == "__main__":
    unittest.main()
