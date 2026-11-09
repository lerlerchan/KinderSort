"""
Regression tests for folder separation validation.
"""

import tempfile
import unittest
from pathlib import Path

from utils import validate_folder_separation


class TestFolderValidation(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.root = Path(self.temp_dir.name)

        self.reference = self.root / "references"
        self.events = self.root / "events"
        self.output = self.root / "output"

        self.reference.mkdir()
        self.events.mkdir()

    def test_separate_folders_allowed(self):
        # T01: Three separate folders should be accepted.
        validate_folder_separation(
            self.reference,
            self.events,
            self.output,
        )

        # Validation should not create the output folder.
        self.assertFalse(self.output.exists())

    def test_output_equals_events_rejected(self):
        # T02: Output cannot equal Events.
        with self.assertRaises(ValueError):
            validate_folder_separation(
                self.reference,
                self.events,
                self.events,
            )

    def test_output_equals_reference_rejected(self):
        # T03: Output cannot equal References.
        with self.assertRaises(ValueError):
            validate_folder_separation(
                self.reference,
                self.events,
                self.reference,
            )

    def test_output_inside_events_rejected(self):
        # T04: Output cannot be inside Events.
        with self.assertRaises(ValueError):
            validate_folder_separation(
                self.reference,
                self.events,
                self.events / "output",
            )

    def test_output_inside_reference_rejected(self):
        # T05: Output cannot be inside References.
        with self.assertRaises(ValueError):
            validate_folder_separation(
                self.reference,
                self.events,
                self.reference / "output",
            )

    def test_output_parent_of_inputs_rejected(self):
        # T06: Output cannot contain input folders.
        with self.assertRaises(ValueError):
            validate_folder_separation(
                self.reference,
                self.events,
                self.root,
            )

    def test_symlink_conflict_rejected(self):
        # T07: A symbolic link must not bypass validation.
        alias = self.root / "events_link"

        try:
            alias.symlink_to(
                self.events,
                target_is_directory=True,
            )
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Symlinks unavailable: {exc}")

        with self.assertRaises(ValueError):
            validate_folder_separation(
                self.reference,
                self.events,
                alias,
            )


if __name__ == "__main__":
    unittest.main()
