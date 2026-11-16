"""D14 input boundaries, using only new temporary synthetic data."""
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import test_reserved_reference_names as fixtures
from utils import collect_event_images, safe_copy


class TestInputPathSafety(unittest.TestCase):
    new_sorter = fixtures.TestReservedReferenceNames.new_sorter
    image = fixtures.TestReservedReferenceNames.image

    def setUp(self):
        fixtures.TestReservedReferenceNames.setUp(self)
        self.external = self.root / "external"
        self.external.mkdir()
        self.sentinel = self.image(self.external, "sentinel.jpg")
        self.before = (self.sentinel.read_bytes(), self.sentinel.stat().st_mtime_ns)
        self.addCleanup(self.assert_sentinel)

    def assert_sentinel(self):
        self.assertEqual((self.sentinel.read_bytes(), self.sentinel.stat().st_mtime_ns), self.before)

    def link(self, alias, target, kind="junction", directory=True):
        if kind == "junction":
            if os.name != "nt":
                self.skipTest("Windows junction requires Windows")
            result = subprocess.run(
                ["cmd.exe", "/c", "mklink", "/J", str(alias), str(target)],
                capture_output=True, text=True, check=False,
            )
            if result.returncode:
                self.skipTest("Junction unavailable: " + result.stderr)
        else:
            try:
                alias.symlink_to(target, target_is_directory=directory)
            except (OSError, NotImplementedError) as exc:
                self.skipTest("Symlink unavailable: " + str(exc))
        self.addCleanup(lambda: os.rmdir(alias) if directory and os.name == "nt" else alias.unlink())

    def assert_no_scan_through(self, root, alias):
        """Check rejection before enumeration, not merely output filtering."""
        real_scandir = os.scandir
        real_listdir = os.listdir
        scanned = []

        def check(path):
            path = Path(path)
            scanned.append(path)
            if (path == alias or alias in path.parents
                    or path == self.external or self.external in path.parents):
                self.fail("Scanner entered linked target: " + str(path))

        def scan(path):
            check(path)
            return real_scandir(path)

        def listdir(path):
            check(path)
            return real_listdir(path)

        with patch("os.scandir", side_effect=scan), patch("os.listdir", side_effect=listdir):
            with self.assertRaisesRegex(ValueError, "[Ll]ink|reparse"):
                collect_event_images(root)
        self.assertNotIn(alias, scanned)

    def scenario(self, kind, nested=False, internal=False, missing=False, cycle=False, file=False):
        parent = self.events
        if nested:
            parent = self.events / "Day" / "Deep"
            parent.mkdir(parents=True)
        target = self.sentinel if file else self.external
        if internal:
            target = self.image(self.events, "ordinary.jpg") if file else self.events / "ordinary"
            if not file:
                target.mkdir()
                self.image(target, "ordinary.jpg")
        if missing:
            target = self.root / "missing"
        if cycle:
            target = self.events
        alias = parent / ("linked.jpg" if file else "linked")
        self.link(alias, target, kind, directory=not file)
        self.assert_no_scan_through(self.events, alias)

    def test_ordinary_tree_and_classification(self):
        self.image(self.references, "Ali.jpg")
        root_photo = self.image(self.events, "root.jpg")
        folder = self.events / "Day" / "Deep"
        folder.mkdir(parents=True)
        nested = self.image(folder, "nested.JPG")
        self.assertCountEqual(collect_event_images(self.events), [(root_photo, "events"), (nested, "Day")])
        self.sorter.load_references()
        stats = self.sorter.sort_all(lambda *args: None, lambda: False)
        self.assertEqual(stats, dict(total=2, matched=2, unmatched=0, errors=0, skipped=0))
        self.assertEqual((self.output / "Ali" / "Day__nested.JPG").read_bytes(), nested.read_bytes())

    def test_linked_event_root(self):
        alias = self.root / "event_alias"
        self.link(alias, self.external)
        self.assert_no_scan_through(alias, alias)

    def test_linked_root_ancestor(self):
        child = self.external / "child"
        child.mkdir()
        self.image(child, "photo.jpg")
        alias = self.root / "ancestor_alias"
        self.link(alias, self.external)
        self.assert_no_scan_through(alias / "child", alias)

    def test_reference_junction_rejected_before_loader(self):
        self.link(self.references / "Ali.jpg", self.external)
        with self.assertRaises(ValueError):
            self.sorter.load_references()
        self.faces.load_image_file.assert_not_called()
        self.assertEqual(self.sorter._student_encodings, {})

    def test_reference_root_junction_rejected_before_loader(self):
        alias = self.root / "reference_alias"
        self.link(alias, self.external)
        self.sorter.reference_folder = alias
        with self.assertRaises(ValueError):
            self.sorter.load_references()
        self.faces.load_image_file.assert_not_called()

    def test_event_junction_rejected_before_decode_or_copy(self):
        self.link(self.events / "linked", self.external)
        self.sorter._load_and_resize = Mock()
        with patch.object(Path, "open", side_effect=AssertionError("Unexpected file open")) as opened:
            with self.assertRaises(ValueError):
                self.sorter.sort_all(lambda *args: None, lambda: False)
        opened.assert_not_called()
        self.sorter._load_and_resize.assert_not_called()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_copy_rechecks_source_ancestor(self):
        alias = self.root / "copy_alias"
        self.link(alias, self.external)
        with patch.object(Path, "open", side_effect=AssertionError("Unexpected file open")) as opened:
            with self.assertRaises(ValueError):
                safe_copy(alias / "sentinel.jpg", self.output, "copy.jpg", self.logger)
        opened.assert_not_called()

    def test_copy_rejects_replacement_after_destination_reservation(self):
        folder = self.events / "Day"
        folder.mkdir()
        source = self.image(folder, "sentinel.jpg")
        real_open = Path.open
        reads = []

        def open_file(path, mode="r", *args, **kwargs):
            if mode == "xb":
                folder.rename(self.events / "saved")
                self.link(folder, self.external)
            if mode == "rb":
                reads.append(path)
                self.fail("Source opened after linked replacement")
            return real_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", open_file):
            with self.assertRaises(ValueError):
                safe_copy(source, self.output, "copy.jpg", self.logger)
        self.assertEqual(reads, [])
        self.assertEqual(list(self.output.iterdir()), [])

    def test_reference_callback_replacement_rejected_before_loader(self):
        original = self.references / "ordinary"
        original.mkdir()
        self.image(original, "Ali.jpg")
        self.sorter.reference_folder = original

        def replace(*args):
            original.rename(self.references / "saved")
            self.link(original, self.external)

        with self.assertRaises(ValueError):
            self.sorter.load_references(replace)
        self.faces.load_image_file.assert_not_called()

    def test_event_callback_replacement_rejected_before_decode(self):
        folder = self.events / "Day"
        folder.mkdir()
        self.image(folder, "sentinel.jpg")
        self.sorter._load_and_resize = Mock()

        def replace(*args):
            folder.rename(self.events / "saved")
            self.link(folder, self.external)

        with self.assertRaises(ValueError):
            self.sorter.sort_all(replace, lambda: False)
        self.sorter._load_and_resize.assert_not_called()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_reference_file_symlink(self):
        self.link(self.references / "Ali.jpg", self.sentinel, "symlink", directory=False)
        with self.assertRaises(ValueError):
            self.sorter.load_references()
        self.faces.load_image_file.assert_not_called()


# Separate tests keep unavailable native symlinks visible as individual SKIPs.
def scenario_test(kind, options):
    def test(self):
        self.scenario(kind, **options)
    return test


for _kind in ("junction", "symlink"):
    for _name, _options in {
        "external_directory": {},
        "nested_external_directory": {"nested": True},
        "internal_directory": {"internal": True},
        "missing_directory": {"missing": True},
        "cycle_directory": {"cycle": True, "nested": True},
    }.items():
        setattr(TestInputPathSafety, f"test_{_kind}_{_name}", scenario_test(_kind, _options))
for _name, _options in {
    "root_external": {},
    "nested_external": {"nested": True},
    "internal": {"internal": True},
    "dangling": {"missing": True},
}.items():
    setattr(TestInputPathSafety, f"test_symlink_file_{_name}", scenario_test("symlink", dict(file=True, **_options)))
