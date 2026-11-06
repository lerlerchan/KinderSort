"""Atomic reference validation and real GUI worker failure propagation."""

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

import test_reserved_reference_names as fixtures


class TestReferenceFailures(unittest.TestCase):
    setUp = fixtures.TestReservedReferenceNames.setUp
    new_sorter = fixtures.TestReservedReferenceNames.new_sorter
    image = fixtures.TestReservedReferenceNames.image

    def configure(self, failures):
        """Inject only external image/face API failures by filename and stage."""
        self.faces.load_image_file.side_effect = lambda path: process("reading", Path(path).name)
        self.faces.face_locations.side_effect = lambda image, **kwargs: process("detection", image)
        self.faces.face_encodings.side_effect = lambda image, **kwargs: process("encoding", image)

        def process(stage, name):
            """Return normal external API results unless this stage fails."""
            if name in failures and failures[name][0] == stage:
                result = failures[name][1]
                if isinstance(result, Exception):
                    raise result
                return result
            return {"reading": name, "detection": [(0, 8, 8, 0)], "encoding": [self.encoding]}[stage]

    def reject(self, failures):
        """Require actionable errors and an unusable partial reference set."""
        self.configure(failures)
        with self.assertRaises(ValueError) as caught:
            self.sorter.load_references()
        message = str(caught.exception)
        for name, (stage, _) in failures.items():
            self.assertIn(name, message)
            self.assertIn(stage, message.lower())
        self.assertRegex(message.lower(), r"replace|correct")
        self.assertIn("sorting has not started", message.lower())
        self.assertEqual(self.sorter._student_encodings, {})
        return message

    def test_t01_all_valid(self):
        """All supported extensions and Chinese names retain successful behavior."""
        names = ("Ali.jpg", "Bob.jpeg", "王小明.PNG", "Siti.bmp", "Zoe.webp")
        for name in names:
            self.image(self.references, name)
        (self.references / "ignored.gif").write_bytes(b"unsupported")
        self.configure({})
        callback = Mock()
        self.assertEqual(self.sorter.load_references(callback), [])
        self.assertEqual(set(self.sorter._student_encodings), {Path(n).stem for n in names})
        self.assertEqual(callback.call_count, 5)
        self.assertEqual(self.faces.load_image_file.call_count, 5)
        self.faces.face_encodings.assert_called_with(
            "王小明.PNG", known_face_locations=[(0, 8, 8, 0)], num_jitters=10, model="large"
        )

    def one_failure(self, stage, failure):
        """Exercise a failed supported file using real validation."""
        self.image(self.references, "Bad.jpg")
        self.reject({"Bad.jpg": (stage, failure)})

    def test_t02_corrupt(self):
        self.one_failure("reading", self.sorter.load_references.__globals__["UnidentifiedImageError"]("corrupt"))

    def test_t03_permission(self):
        self.one_failure("reading", PermissionError("access denied"))

    def test_t04_decode_oserror(self):
        self.one_failure("reading", OSError("decoder failed"))

    def test_t05_detection(self):
        self.one_failure("detection", RuntimeError("detector failed"))

    def test_t06_encoding(self):
        self.one_failure("encoding", RuntimeError("encoder failed"))

    def test_t07_no_usable_encoding(self):
        for result in ([], [None], [[]], [[0.0] * 127], [[float("nan")] * 128]):
            with self.subTest(result=repr(result)[:50]):
                self.sorter = self.new_sorter()
                self.one_failure("encoding", result)

    def test_t08_mixed_valid_invalid(self):
        for name in ("Aaron.jpg", "Bad.png", "Zoe.jpg"):
            self.image(self.references, name)
        self.reject({"Bad.png": ("reading", OSError("bad data"))})
        self.assertEqual(self.faces.load_image_file.call_count, 3)

    def test_t09_collect_multiple_failures(self):
        failures = {
            "A.jpg": ("reading", PermissionError("denied")),
            "B.png": ("detection", RuntimeError("bad detection")),
            "C.bmp": ("encoding", []),
        }
        for name in failures:
            self.image(self.references, name)
        self.reject(failures)
        self.assertEqual(self.faces.load_image_file.call_count, 3)

    def test_t10_failed_reload_clears_partial_and_stale_data(self):
        self.image(self.references, "Aaron.jpg")
        self.configure({})
        self.sorter.load_references()
        self.assertTrue(self.sorter._student_encodings)
        self.image(self.references, "Zoe.png")
        self.reject({"Zoe.png": ("encoding", [])})
        self.assertIsNone(self.sorter._match_face(self.encoding))

    def gui_module(self):
        """Import real GUI code with isolated sorter dependency; no Tk window."""
        dependency = ModuleType("sorter")
        dependency.PhotoSorter = self.sorter_class
        spec = importlib.util.spec_from_file_location("_failure_gui", Path(__file__).resolve().parents[1] / "main.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"sorter": dependency}):
            spec.loader.exec_module(module)
        return module

    def run_gui_failure(self):
        """Run real loading, worker, and error callback with mocked UI boundaries."""
        module = self.gui_module()
        app = Mock()
        app._on_error = lambda message: module.KinderSortApp._on_error(app, message)
        app.after.side_effect = lambda delay, callback, *args: callback(*args)
        with patch.object(self.sorter, "sort_all", wraps=self.sorter.sort_all) as sort_all:
            with patch.object(module.messagebox, "showerror") as showerror:
                module.KinderSortApp._run_sorting(app, self.sorter)
            sort_all.assert_not_called()
        showerror.assert_called_once()
        self.assertIn("Bad.jpg", showerror.call_args.args[1])
        self.assertIn("sorting has not started", showerror.call_args.args[1].lower())
        app._start_btn.config.assert_called_once_with(state=module.tk.NORMAL)
        app._cancel_btn.config.assert_called_once_with(state=module.tk.DISABLED)
        app._stop_ticker.assert_called_once()
        app._on_done.assert_not_called()
        app._show_ref_warning.assert_not_called()

    def test_t11_gui_stops_and_restores_controls(self):
        self.image(self.references, "Aaron.jpg")
        self.image(self.references, "Bad.jpg")
        self.configure({"Bad.jpg": ("encoding", [])})
        self.run_gui_failure()

    def test_t12_preserves_sources_and_existing_output(self):
        for name in ("Aaron.jpg", "Bad.jpg"):
            self.image(self.references, name)
        self.image(self.events, "event.jpg")
        (self.output / "Aaron").mkdir()
        self.image(self.output / "Aaron", "events__event.jpg")
        (self.output / "kindersort_log.txt").write_bytes(b"existing log")

        def snapshot():
            """Compare directory structure, file content and modification times."""
            return {p.relative_to(self.root).as_posix():
                    (p.read_bytes(), p.stat().st_mtime_ns) if p.is_file() else None
                    for p in self.root.rglob("*")}

        before = snapshot()
        self.configure({"Bad.jpg": ("reading", OSError("bad image"))})
        self.run_gui_failure()
        self.assertEqual(snapshot(), before)

    def test_t13_multiple_faces_still_use_first_encoding(self):
        """Keep the established selection policy and delay publishing until done."""
        self.image(self.references, "Ali.jpg")
        self.configure({"Ali.jpg": ("encoding", [self.encoding, [1.0] * 128])})
        callback = Mock(side_effect=lambda *args: self.assertEqual(self.sorter._student_encodings, {}))
        self.assertEqual(self.sorter.load_references(callback), [])
        self.assertIs(self.sorter._student_encodings["Ali"], self.encoding)
        callback.assert_called_once_with(1, 1, "Ali")
        self.logger.warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
