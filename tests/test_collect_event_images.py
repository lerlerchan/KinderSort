"""
Regression tests for collecting event images.
"""

import tempfile
import unittest
from pathlib import Path

from utils import collect_event_images


class TestCollectEventImages(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.events = Path(self.temp_dir.name) / "Events"
        self.events.mkdir()

    def create_file(self, relative_path):
        path = self.events / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        return path

    def test_root_images_only(self):
        # T01: Collect images directly inside Events.
        image = self.create_file("IMG_001.jpg")

        result = collect_event_images(self.events)

        self.assertEqual(
            result,
            [(image, "Events")],
        )

    def test_subfolder_images_only(self):
        # T02: Collect images from event subfolders.
        image = self.create_file("Sports_Day/IMG_002.jpg")

        result = collect_event_images(self.events)

        self.assertEqual(
            result,
            [(image, "Sports_Day")],
        )

    def test_root_and_subfolder_images(self):
        # T03: Collect both without duplicates.
        root_image = self.create_file("IMG_001.jpg")
        sub_image = self.create_file("Sports_Day/IMG_002.jpg")

        result = collect_event_images(self.events)

        self.assertCountEqual(
            result,
            [
                (root_image, "Events"),
                (sub_image, "Sports_Day"),
            ],
        )
        self.assertEqual(len(result), 2)

    def test_deeply_nested_images(self):
        # T04: Keep the immediate event folder name.
        image = self.create_file(
            "Sports_Day/Day1/IMG_003.jpg"
        )

        result = collect_event_images(self.events)

        self.assertEqual(
            result,
            [(image, "Sports_Day")],
        )

    def test_ignore_non_images(self):
        # T05: Ignore unsupported files; accept uppercase JPG.
        image = self.create_file("Sports_Day/PHOTO.JPG")
        self.create_file("notes.txt")
        self.create_file("Sports_Day/readme.docx")

        result = collect_event_images(self.events)

        self.assertEqual(
            result,
            [(image, "Sports_Day")],
        )

    def test_empty_events_folder(self):
        # T06: Return an empty list if no images exist.
        result = collect_event_images(self.events)

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
