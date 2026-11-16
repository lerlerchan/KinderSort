"""Duplicate student names must fail atomically, without image dependencies."""

import itertools
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import test_reserved_reference_names as fixtures


class TestDuplicateReferenceNames(unittest.TestCase):
    # Reuse the isolated dependency mocks and temporary filesystem fixture.
    setUp = fixtures.TestReservedReferenceNames.setUp
    new_sorter = fixtures.TestReservedReferenceNames.new_sorter
    image = fixtures.TestReservedReferenceNames.image

    def assert_duplicate(self, names):
        """Check the error and all pre-encoding boundaries independently."""
        callback = Mock()
        sorter = self.new_sorter()
        self.faces.reset_mock()
        error = None
        try:
            sorter.load_references(callback)
        except ValueError as exc:
            error = exc
        with self.subTest(check="actionable exception"):
            self.assertIsInstance(error, ValueError)
            for name in names:
                self.assertIn(name, str(error))
            self.assertIn("duplicate", str(error).lower())
            self.assertIn("one reference image per student", str(error).lower())
            self.assertRegex(str(error).lower(), r"remove|rename")
        with self.subTest(check="no partial processing"):
            callback.assert_not_called()
            self.faces.load_image_file.assert_not_called()
            self.faces.face_locations.assert_not_called()
            self.faces.face_encodings.assert_not_called()
            self.assertEqual(sorter._student_encodings, {})

    def test_supported_extension_collisions(self):
        """Every supported extension pair shares a student identity."""
        for first, second in itertools.combinations(("jpg", "jpeg", "png", "bmp", "webp"), 2):
            names = (f"Ali.{first}", f"Ali.{second}")
            with self.subTest(names=names):
                paths = [self.image(self.references, name) for name in names]
                try:
                    self.assert_duplicate(names)
                finally:
                    for path in paths:
                        path.unlink()

    def test_every_enumeration_order_and_case_collision(self):
        """Distinct extensions allow case variants on Windows filesystems too."""
        original_iterdir = Path.iterdir
        for names in (("Ali.jpg", "Ali.png"), ("Ali.jpg", "aLI.PNG"), ("王小明.jpg", "王小明.png")):
            paths = [self.image(self.references, name) for name in (*names, "Aaron.jpg", "Zoe.png")]
            try:
                for order in itertools.permutations(paths):
                    with self.subTest(names=names, order=[p.name for p in order]):
                        def enumerate_paths(folder):
                            """Vary enumeration without changing real file operations."""
                            return iter(order) if folder == self.references else original_iterdir(folder)

                        with patch.object(Path, "iterdir", enumerate_paths):
                            self.assert_duplicate(names)
            finally:
                for path in paths:
                    path.unlink()

    def test_source_and_existing_output_preserved(self):
        """Rejected references cannot reach copying or alter existing data."""
        names = ("Ali.jpg", "Ali.png")
        for name in names:
            self.image(self.references, name)
        self.image(self.events, "event.jpg")
        (self.output / "Ali").mkdir()
        self.image(self.output / "Ali", "events__event.jpg")
        (self.output / "kindersort_log.txt").write_bytes(b"existing log")

        def snapshot():
            """Capture directory structure, bytes and modification times."""
            return {
                p.relative_to(self.root).as_posix():
                (p.read_bytes(), p.stat().st_mtime_ns) if p.is_file() else None
                for p in self.root.rglob("*")
            }

        before = snapshot()
        with patch.object(self.sorter, "sort_all") as sort_all:
            with self.assertRaises(ValueError):
                self.sorter.load_references()
                self.sorter.sort_all(Mock(), lambda: False)
            sort_all.assert_not_called()
        self.assertEqual(snapshot(), before)

    def test_unique_names_and_valid_behavior_unchanged(self):
        """Preserve name spelling, encodings and callbacks for valid references."""
        names = ("Ali.jpg", "王小明.png", "Siti.webp")
        for name in names:
            self.image(self.references, name)
        (self.references / "Ali.txt").write_bytes(b"ignored")
        encodings = {"Ali": [1.0] * 128, "王小明": [2.0] * 128, "Siti": [3.0] * 128}
        self.faces.load_image_file.side_effect = lambda path: Path(path).stem
        self.faces.face_encodings.side_effect = lambda image, **kwargs: [encodings[image]] if image in encodings else []
        callback = Mock()
        self.assertEqual(self.sorter.load_references(callback), [])
        self.assertEqual(self.sorter._student_encodings, encodings)
        self.assertEqual(self.faces.face_encodings.call_count, 3)
        self.assertEqual(callback.call_count, 3)
        self.assertEqual([call.args for call in callback.call_args_list], [
            (i, 3, path.stem) for i, path in enumerate(sorted(self.references / name for name in names), 1)
        ])


if __name__ == "__main__":
    unittest.main()
