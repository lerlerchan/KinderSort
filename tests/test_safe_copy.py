"""Regression coverage for safe_copy; all data stays in temporary folders."""

import logging
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import safe_copy


class TestSafeCopy(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source.jpg"
        self.source_bytes = b"synthetic source image\x00\x01"
        self.source.write_bytes(self.source_bytes)
        self.output = self.root / "output"
        self.logger = logging.getLogger("test.safe_copy")
        self.addCleanup(self.assert_source_unchanged)

    def assert_source_unchanged(self):
        self.assertEqual(self.source.read_bytes(), self.source_bytes)

    def copy(self, folder=None):
        return safe_copy(
            self.source, self.output if folder is None else folder,
            "photo.jpg", self.logger,
        )

    def test_t01_new_destination(self):
        result = self.copy()
        self.assertEqual(result, self.output / "photo.jpg")
        self.assertEqual(result.read_bytes(), self.source_bytes)

    def test_t02_existing_filename(self):
        self.output.mkdir()
        original = self.output / "photo.jpg"
        original.write_bytes(b"original destination")
        result = self.copy()
        self.assertEqual(result, self.output / "photo_2.jpg")
        self.assertEqual(original.read_bytes(), b"original destination")
        self.assertEqual(result.read_bytes(), self.source_bytes)

    def test_t03_multiple_numbered_filenames(self):
        self.output.mkdir()
        existing = {
            "photo.jpg": b"original", "photo_2.jpg": b"second",
            "photo_3.jpg": b"third", "photo_5.jpg": b"fifth",
        }
        for name, contents in existing.items():
            (self.output / name).write_bytes(contents)
        result = self.copy()
        self.assertEqual(result, self.output / "photo_4.jpg")
        self.assertEqual(result.read_bytes(), self.source_bytes)
        for name, contents in existing.items():
            self.assertEqual((self.output / name).read_bytes(), contents)

    def test_t04_repeated_copy(self):
        results = [self.copy() for _ in range(3)]
        self.assertEqual(results, [
            self.output / name
            for name in ("photo.jpg", "photo_2.jpg", "photo_3.jpg")
        ])
        for result in results:
            self.assertEqual(result.read_bytes(), self.source_bytes)

    def test_t05_concurrent_filename_reservation(self):
        self.output.mkdir()
        candidate = self.output / "photo.jpg"
        other_bytes = b"another writer owns this file"
        real_open = Path.open
        injected = []
        collisions = []

        def reserve_before_open(path, mode="r", *args, **kwargs):
            if path == candidate and mode == "xb" and not injected:
                # Reserve the name immediately before the real exclusive open.
                # Call the saved method to avoid recursively invoking this hook.
                with real_open(path, "xb") as stream:
                    stream.write(other_bytes)
                injected.append(path)
                try:
                    return real_open(path, mode, *args, **kwargs)
                except FileExistsError:
                    collisions.append(path)
                    raise
            return real_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", reserve_before_open):
            result = self.copy()
        self.assertEqual(injected, [candidate], "The reservation race must be injected")
        self.assertEqual(collisions, [candidate], "Exclusive creation must detect the collision")
        self.assertEqual(candidate.read_bytes(), other_bytes)
        self.assertNotEqual(result, candidate)
        self.assertEqual(result, self.output / "photo_2.jpg")
        self.assertEqual(result.read_bytes(), self.source_bytes)
        self.assert_source_unchanged()

    def test_t06_failure_removes_only_incomplete_output(self):
        self.output.mkdir()
        existing = {"photo.jpg": b"keep original", "unrelated.bin": b"keep unrelated"}
        for name, contents in existing.items():
            (self.output / name).write_bytes(contents)
        failure = OSError("injected write failure")
        partial_paths = []
        partial_bytes = b"incomplete data"
        written = []

        def fail_during_copy(src, dst, *args, **kwargs):
            destination = Path(dst.name)
            partial_paths.append(destination)
            written.append(dst.write(partial_bytes))
            dst.flush()
            self.assertEqual(destination.read_bytes(), partial_bytes)
            raise failure

        with patch("utils.shutil.copyfileobj", side_effect=fail_during_copy) as copy_mock:
            with self.assertRaises(OSError) as caught:
                self.copy()
        copy_mock.assert_called_once()
        self.assertIs(caught.exception, failure)
        self.assertTrue(partial_paths, "The write failure must be exercised")
        self.assertEqual(partial_paths, [self.output / "photo_2.jpg"])
        self.assertEqual(written, [len(partial_bytes)], "Partial bytes must actually be written")
        self.assert_source_unchanged()
        for name, contents in existing.items():
            self.assertEqual((self.output / name).read_bytes(), contents)
        for partial in partial_paths:
            self.assertFalse(os.path.lexists(partial), "Incomplete output was left behind")
        self.assertEqual(set(p.name for p in self.output.iterdir()), set(existing))

    def test_t07_existing_and_dangling_destination_symlinks(self):
        self.output.mkdir()
        target = self.root / "target.jpg"
        target.write_bytes(b"protected symlink target")
        missing = self.root / "missing.jpg"
        folders = [self.output / "existing", self.output / "dangling"]
        for folder in folders:
            folder.mkdir()
        try:
            for folder, link_target in zip(folders, (target, missing)):
                (folder / "photo.jpg").symlink_to(link_target)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"File symlink creation unavailable: {exc}")
        for folder, link_target in zip(folders, (target, missing)):
            with self.subTest(dangling=link_target == missing):
                try:
                    result = self.copy(folder)
                except (OSError, ValueError):
                    pass  # Explicit rejection is also safe.
                else:
                    self.assertNotEqual(result, folder / "photo.jpg")
                    self.assertFalse(result.is_symlink())
                    self.assertEqual(result.read_bytes(), self.source_bytes)
                finally:
                    self.assertTrue((folder / "photo.jpg").is_symlink())
                    self.assertEqual(target.read_bytes(), b"protected symlink target")
                    self.assertFalse(os.path.lexists(missing))

    def test_t08_destination_directory_link_rejected(self):
        target = self.root / "protected_directory"
        target.mkdir()
        sentinel = target / "sentinel.bin"
        sentinel.write_bytes(b"protected directory contents")
        alias = self.root / "directory_alias"
        try:
            alias.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            if os.name != "nt":
                self.skipTest(f"Directory symlink creation unavailable: {exc}")
            junction = subprocess.run(
                ["cmd.exe", "/c", "mklink", "/J", str(alias), str(target)],
                capture_output=True, text=True, check=False,
            )
            if junction.returncode:
                self.skipTest(f"Directory symlink and junction unavailable: {junction.stderr}")
        # Remove the link before TemporaryDirectory cleans its target.
        self.addCleanup(lambda: os.rmdir(alias) if os.name == "nt" else alias.unlink())
        try:
            with self.assertRaises((OSError, ValueError)):
                self.copy(alias)
        finally:
            self.assertEqual(sentinel.read_bytes(), b"protected directory contents")
            self.assertEqual(set(p.name for p in target.iterdir()), {"sentinel.bin"})


if __name__ == "__main__":
    unittest.main()
