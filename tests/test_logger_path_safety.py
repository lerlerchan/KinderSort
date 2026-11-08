"""Log path regressions; all targets are newly created synthetic fixtures."""
import logging
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import setup_logger


class TestLoggerPathSafety(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.logger = logging.Logger("isolated.d13")
        self.addCleanup(self.close_handlers)
        self.get_logger = patch("utils.logging.getLogger", return_value=self.logger)
        self.get_logger.start()
        self.addCleanup(self.get_logger.stop)

    def close_handlers(self):
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)

    def directory_link(self, alias, target):
        try:
            alias.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            if os.name != "nt":
                self.skipTest(str(exc))
            result = subprocess.run(
                ["cmd.exe", "/c", "mklink", "/J", str(alias), str(target)],
                capture_output=True, text=True, check=False,
            )
            if result.returncode:
                self.skipTest("Directory link unavailable: " + result.stderr)
        self.addCleanup(lambda: os.rmdir(alias) if os.name == "nt" else alias.unlink())

    def test_linked_output_directory_rejected_before_log_creation(self):
        target = self.root / "protected"
        target.mkdir()
        sentinel = target / "sentinel.bin"
        sentinel.write_bytes(b"synthetic protected data")
        alias = self.root / "output"
        self.directory_link(alias, target)
        with self.assertRaises(ValueError):
            setup_logger(alias)
        self.assertEqual(sentinel.read_bytes(), b"synthetic protected data")
        self.assertEqual({p.name for p in target.iterdir()}, {"sentinel.bin"})

    def test_linked_log_file_rejected_before_append(self):
        output = self.root / "output"
        output.mkdir()
        target = self.root / "protected.txt"
        target.write_bytes(b"synthetic protected data")
        try:
            (output / "kindersort_log.txt").symlink_to(target)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("File symlink unavailable: " + str(exc))
        with self.assertRaises(ValueError):
            setup_logger(output)
        self.assertEqual(target.read_bytes(), b"synthetic protected data")

    def test_regular_existing_log_still_appends(self):
        output = self.root / "output"
        output.mkdir()
        log = output / "kindersort_log.txt"
        log.write_text("existing log\n", encoding="utf-8")
        setup_logger(output).info("synthetic D13 entry")
        self.close_handlers()
        content = log.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("existing log\n"))
        self.assertIn("synthetic D13 entry", content)
