"""Activity error accounting with real filesystem copying and injected boundaries."""

import errno
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import test_reserved_reference_names as fixtures


class TestActivityPhotoFailures(unittest.TestCase):
    new_sorter = fixtures.TestReservedReferenceNames.new_sorter
    image = fixtures.TestReservedReferenceNames.image

    def setUp(self):
        """Keep all photos synthetic and all face dependencies isolated."""
        fixtures.TestReservedReferenceNames.setUp(self)
        self.image(self.references, "Ali.jpg")
        self.sorter.load_references()
        self.bad = self.image(self.events, "a.jpg")
        self.good = self.image(self.events, "z.jpg")
        self.originals = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.addCleanup(self.assert_originals)
        self.progress = Mock()

    def assert_originals(self):
        """Every test verifies source bytes survive, even when assertions fail."""
        for path, content in self.originals.items():
            self.assertEqual(path.read_bytes(), content)

    def run_sort(self):
        """Exercise real sorter, counters, classification, and safe_copy."""
        return self.sorter.sort_all(self.progress, lambda: False)

    def decode_failure(self, error):
        """Inject one decoding failure; later photos decode normally."""
        self.sorter._load_and_resize = Mock(side_effect=lambda path: (_ for _ in ()).throw(error) if path == self.bad else "valid")

    def assert_error(self, stats, stage, preserved=True):
        """Assert disjoint counters, details, preservation and continuation."""
        self.assertEqual(stats, {"total": 2, "matched": 1, "unmatched": 0,
                                 "skipped": 0 if preserved else 1, "errors": 1})
        self.assertEqual(len(self.sorter.error_details), 1)
        detail = self.sorter.error_details[0]
        self.assertEqual(detail["source"], str(self.bad))
        self.assertEqual(detail["stage"], stage)
        self.assertTrue(detail["reason"])
        self.assertEqual(detail["preserved"], preserved)
        if preserved:
            self.assertEqual(Path(detail["preserved_path"]).read_bytes(), self.bad.read_bytes())
            self.assertEqual(Path(detail["preserved_path"]).parent, self.output / "_unmatched")
        else:
            self.assertIsNone(detail["preserved_path"])
            self.assertTrue(detail["preservation_reason"])
        self.assertEqual((self.output / "Ali" / "events__z.jpg").read_bytes(), self.good.read_bytes())

    def test_t01_matched(self):
        self.assertEqual(self.run_sort(), {"total": 2, "matched": 2, "unmatched": 0, "skipped": 0, "errors": 0})

    def test_t02_no_face(self):
        self.faces.face_locations.return_value = []
        self.faces.face_encodings.return_value = []
        self.assertEqual(self.run_sort(), {"total": 2, "matched": 0, "unmatched": 2, "skipped": 0, "errors": 0})
        self.assertEqual(self.sorter.error_details, [])

    def test_t03_no_match(self):
        self.faces.face_distance.side_effect = lambda known, face: [0.9]
        self.assertEqual(self.run_sort(), {"total": 2, "matched": 0, "unmatched": 2, "skipped": 0, "errors": 0})

    def test_t04_unidentified(self):
        self.decode_failure(self.sorter.sort_all.__globals__["UnidentifiedImageError"]("bad"))
        self.assert_error(self.run_sort(), "image reading")

    def test_t05_decode_oserror(self):
        self.decode_failure(OSError("decoder failed"))
        self.assert_error(self.run_sort(), "image reading")

    def test_t06_permission(self):
        self.decode_failure(PermissionError("source denied"))
        self.assert_error(self.run_sort(), "image reading")

    def test_t07_hog(self):
        self.faces.face_locations.side_effect = [RuntimeError("hog failed"), [(0, 8, 8, 0)]]
        self.assert_error(self.run_sort(), "HOG detection")

    def test_t08_cnn(self):
        self.faces.face_locations.side_effect = [[], RuntimeError("cnn failed"), [(0, 8, 8, 0)]]
        self.assert_error(self.run_sort(), "CNN detection")

    def test_t09_encoding(self):
        self.faces.face_encodings.side_effect = [RuntimeError("encoder failed"), [self.encoding]]
        self.assert_error(self.run_sort(), "face encoding")

    def test_t10_matching(self):
        self.faces.face_distance.side_effect = [RuntimeError("distance failed"), [0.0]]
        self.assert_error(self.run_sort(), "face matching")

    def test_t11_preservation_uses_actual_collision_path(self):
        folder = self.output / "_unmatched"
        folder.mkdir()
        existing = folder / "events__a.jpg"
        existing.write_bytes(b"existing destination")
        self.decode_failure(OSError("decode failed"))
        self.assert_error(self.run_sort(), "image reading")
        self.assertEqual(existing.read_bytes(), b"existing destination")
        self.assertEqual(Path(self.sorter.error_details[0]["preserved_path"]).name, "events__a_2.jpg")

    def test_t12_raw_source_open_failure(self):
        self.decode_failure(OSError("decode failed"))
        real_open = Path.open
        denied = []

        def open_file(path, mode="r", *args, **kwargs):
            """Fault only the actual raw source opening operation."""
            if path == self.bad and mode == "rb":
                denied.append(path)
                raise PermissionError("raw source denied")
            return real_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", open_file):
            stats = self.run_sort()
        self.assertTrue(denied)
        self.assert_error(stats, "image reading", False)
        self.assertFalse((self.output / "_unmatched" / "events__a.jpg").exists())

    def test_t13_destination_failures_stop(self):
        for operation in ("mkdir", "open", "write", "metadata", "close"):
            with self.subTest(operation=operation):
                self.sorter = self.new_sorter()
                self.sorter._student_encodings = {"Ali": self.encoding}
                failure = PermissionError("destination denied")
                real_mkdir, real_open = Path.mkdir, Path.open
                hit = []

                def mkdir(path, *args, **kwargs):
                    if operation == "mkdir" and path == self.output / "Ali":
                        hit.append(operation)
                        raise failure
                    return real_mkdir(path, *args, **kwargs)

                def open_file(path, mode="r", *args, **kwargs):
                    if operation == "open" and mode == "xb":
                        hit.append(operation)
                        raise failure
                    stream = real_open(path, mode, *args, **kwargs)
                    if operation == "close" and mode == "xb":
                        class CloseFailure:
                            def __getattr__(self, name):
                                return getattr(stream, name)

                            def __enter__(self):
                                return self

                            def __exit__(self, exc_type, *args):
                                self_test.assertIsNone(exc_type, "Copy must reach close without an earlier failure")
                                stream.flush()
                                self_test.assertEqual(path.read_bytes(), self_test.bad.read_bytes())
                                stream.close()
                                hit.append(operation)
                                raise failure
                        self_test = self
                        return CloseFailure()
                    return stream

                def fail(*args, **kwargs):
                    hit.append(operation)
                    raise failure

                with patch.object(Path, "mkdir", mkdir), patch.object(Path, "open", open_file):
                    target = "utils.shutil.copyfileobj" if operation == "write" else "utils.shutil.copystat"
                    with patch(target, side_effect=fail) if operation in ("write", "metadata") else patch.dict({}, {}):
                        self.progress.reset_mock()
                        with self.assertRaises(PermissionError) as caught:
                            self.run_sort()
                self.assertIs(caught.exception, failure)
                self.assertTrue(hit)
                self.assertEqual(self.progress.call_count, 1)

    def test_t14_disk_full(self):
        failure = OSError(errno.ENOSPC, "disk full")
        with patch("utils.shutil.copyfileobj", side_effect=failure) as injected:
            with self.assertRaises(OSError) as caught:
                self.run_sort()
        injected.assert_called_once()
        self.assertIs(caught.exception, failure)
        self.assertEqual(caught.exception.errno, errno.ENOSPC)
        self.assertEqual(self.progress.call_count, 1)

    def test_t15_source_read_during_normal_copy(self):
        real_open = Path.open
        hit = []

        def open_file(path, mode="r", *args, **kwargs):
            stream = real_open(path, mode, *args, **kwargs)
            if path == self.bad and mode == "rb":
                class FailingReader:
                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        stream.close()

                    def read(self, *args):
                        hit.append(path)
                        raise OSError("source read failed")
                return FailingReader()
            return stream

        with patch.object(Path, "open", open_file):
            stats = self.run_sort()
        self.assertTrue(hit)
        self.assert_error(stats, "source copying", False)

    def test_t16_inputs_unchanged(self):
        self.decode_failure(OSError("decode failed"))
        self.run_sort()
        self.assert_originals()

    def test_t17_existing_matched_destination(self):
        folder = self.output / "Ali"
        folder.mkdir()
        original = self.image(folder, "events__a.jpg")
        content = original.read_bytes()
        self.run_sort()
        self.assertEqual(original.read_bytes(), content)
        self.assertEqual((folder / "events__a_2.jpg").read_bytes(), self.bad.read_bytes())

    def test_t18_error_details_do_not_log_biometric_payload(self):
        self.decode_failure(RuntimeError("SECRET_IMAGE_OR_ENCODING"))
        self.assert_error(self.run_sort(), "image reading")
        self.assertNotIn("SECRET_IMAGE_OR_ENCODING", str(self.sorter.error_details))
        self.assertNotIn("SECRET_IMAGE_OR_ENCODING", str(self.logger.mock_calls))

    def test_t19_mixed_statistics(self):
        self.image(self.events, "b.jpg")
        self.decode_failure(OSError("decode failed"))
        self.faces.face_encodings.side_effect = [[], [self.encoding]]
        stats = self.run_sort()
        self.assertEqual(stats, {"total": 3, "matched": 1, "unmatched": 1, "errors": 1, "skipped": 0})
        self.assertEqual(stats["errors"], len(self.sorter.error_details))

    def test_t20_group_partial_output_stops(self):
        self.sorter._student_encodings["Bob"] = [1.0] * 128
        self.faces.face_encodings.return_value = [self.encoding, [1.0] * 128]
        self.faces.face_distance.side_effect = lambda known, face: [0.0, 1.0] if face == self.encoding else [1.0, 0.0]
        real_open = Path.open
        copies = []
        failure = OSError(errno.ENOSPC, "second group destination failed")

        def open_file(path, mode="r", *args, **kwargs):
            if mode == "xb":
                copies.append(path)
                if len(copies) == 2:
                    raise failure
            return real_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", open_file):
            with self.assertRaises(OSError) as caught:
                self.run_sort()
        self.assertIs(caught.exception, failure)
        self.assertEqual(len(copies), 2)
        self.assertEqual(copies[0].read_bytes(), self.bad.read_bytes())
        self.assertEqual(self.progress.call_count, 1)
        self.assertFalse(any("Sort complete" in str(call) for call in self.logger.info.call_args_list))

    def test_t21_error_preservation_output_failure_stops(self):
        self.decode_failure(OSError("bad decoding"))
        failure = OSError(errno.ENOSPC, "output full")
        with patch("utils.shutil.copyfileobj", side_effect=failure) as copy:
            with self.assertRaises(OSError) as caught:
                self.run_sort()
        copy.assert_called_once()
        self.assertIs(caught.exception, failure)
        self.assertEqual(self.progress.call_count, 1)
        detail = self.sorter.error_details[0]
        self.assertFalse(detail["preserved"])
        self.assertIsNone(detail["preserved_path"])
        self.assertIn("batch stopped", detail["preservation_reason"])

    def test_t22_source_failure_cleanup_output_error_stops(self):
        real_open = Path.open
        failure = PermissionError("cannot remove incomplete output")
        hit = []

        def open_file(path, mode="r", *args, **kwargs):
            if path == self.bad and mode == "rb":
                raise PermissionError("source denied")
            return real_open(path, mode, *args, **kwargs)

        def unlink(path, *args, **kwargs):
            hit.append(path)
            raise failure

        with patch.object(Path, "open", open_file), patch.object(Path, "unlink", unlink):
            with self.assertRaises(PermissionError) as caught:
                self.run_sort()
        self.assertIs(caught.exception, failure)
        self.assertEqual(len(hit), 1)
        self.assertEqual(self.progress.call_count, 1)

    def test_t23_group_success_counts_once(self):
        self.sorter._student_encodings["Bob"] = [1.0] * 128
        self.faces.face_encodings.return_value = [self.encoding, [1.0] * 128]
        self.faces.face_distance.side_effect = lambda known, face: [0.0, 1.0] if face == self.encoding else [1.0, 0.0]
        self.assertEqual(self.run_sort(), {"total": 2, "matched": 2, "unmatched": 0, "errors": 0, "skipped": 0})
        for name in ("Ali", "Bob"):
            self.assertEqual((self.output / name / "events__a.jpg").read_bytes(), self.bad.read_bytes())

    def test_t24_error_records_reset_on_next_run(self):
        self.decode_failure(OSError("bad decoding"))
        self.assertEqual(self.run_sort()["errors"], 1)
        self.sorter._load_and_resize = Mock(return_value="valid")
        self.assertEqual(self.run_sort()["errors"], 0)
        self.assertEqual(self.sorter.error_details, [])

    def test_t25_changed_output_identity_stops_after_source_failure(self):
        real_open = Path.open
        denied = []

        def open_file(path, mode="r", *args, **kwargs):
            if path == self.bad and mode == "rb":
                denied.append(path)
                raise PermissionError("source denied")
            return real_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", open_file):
            with patch("utils.os.path.samestat", return_value=False) as identity:
                with self.assertRaises(OSError) as caught:
                    self.run_sort()
        self.assertIn("Destination", str(caught.exception))
        self.assertTrue(denied)
        identity.assert_called_once()
        self.assertEqual(self.progress.call_count, 1)
        self.assertTrue((self.output / "Ali" / "events__a.jpg").exists())


if __name__ == "__main__":
    unittest.main()
