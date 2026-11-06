"""Headless GUI regressions: real controller methods, queued Tk callbacks."""
import importlib.util
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch


class TestGuiErrorRecovery(unittest.TestCase):
    def setUp(self):
        dependency = ModuleType('sorter')
        dependency.PhotoSorter = Mock()
        spec = importlib.util.spec_from_file_location('_c3_gui', Path(__file__).resolve().parents[1] / 'main.py')
        self.gui = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'sorter': dependency}):
            spec.loader.exec_module(self.gui)
        # Bypass Tk construction but bind the actual controller implementation.
        self.app = object.__new__(self.gui.KinderSortApp)
        for name in ('_start_btn', '_cancel_btn', '_progress_var', '_status_label', '_timer_label', '_summary_text'):
            setattr(self.app, name, Mock())
        self.app._sort_start_time = None
        self.app._ticker_id = 'timer'
        self.app._cancel_flag = threading.Event()
        self.app.after_cancel = Mock()
        self.queue = []
        self.app.after = Mock(side_effect=lambda delay, cb, *args: self.queue.append((cb, args)))
        self.dialog = patch.object(self.gui.messagebox, 'showerror').start()
        self.warning = patch.object(self.gui.messagebox, 'showwarning').start()
        self.addCleanup(patch.stopall)
        self.sorter = Mock()
        self.sorter._student_encodings = {'Ali': [0]}
        self.sorter.load_references.return_value = []
        self.sorter.error_details = []
        self.stats = dict(total=4, matched=2, unmatched=2, errors=0, skipped=0)
        self.sorter.sort_all.return_value = self.stats

    def drain(self):
        while self.queue:
            cb, args = self.queue.pop(0)
            cb(*args)

    def summary(self):
        return self.app._summary_text.insert.call_args.args[1]

    def status(self):
        return self.app._status_label.config.call_args.kwargs['text']

    def restored(self):
        self.assertEqual(self.app._start_btn.config.call_args.kwargs['state'], 'normal')
        self.assertEqual(self.app._cancel_btn.config.call_args.kwargs['state'], 'disabled')
        self.assertIsNone(self.app._sort_start_time)
        self.assertIsNone(self.app._ticker_id)

    def run_worker(self):
        self.app._run_sorting(self.sorter)
        self.drain()

    def test_success(self):
        self.run_worker()
        self.assertEqual(self.status(), 'Sorting complete.')
        self.assertIn('Total activity photos: 4', self.summary())
        self.restored()

    def test_normal_unmatched_is_not_error(self):
        self.run_worker()
        self.assertIn('Normal unmatched: 2', self.summary())
        self.assertNotIn('completed with errors', self.status())

    def test_errors_and_skipped_subset(self):
        self.stats.update(matched=1, unmatched=1, errors=2, skipped=1)
        self.run_worker()
        self.assertEqual(self.status(), 'Sorting completed with errors')
        for text in ('Matched: 1', 'Normal unmatched: 1', 'Processing errors: 2', 'Error photos without preserved copies: 1'):
            self.assertIn(text, self.summary())
        self.assertNotIn('Processing errors: 3', self.summary())

    def test_sanitized_details_visible(self):
        self.stats.update(errors=1)
        self.sorter.error_details = [dict(source='bad.jpg', stage='image reading', reason='image reading failed (OSError)', preserved=False)]
        self.run_worker()
        for text in ('bad.jpg', 'image reading failed (OSError)', 'Error details', 'not preserved'):
            self.assertIn(text, self.summary())

    def test_reference_failure_blocks_sort(self):
        self.sorter.load_references.side_effect = ValueError("Reference photo validation failed:\n'Bad.jpg': face encoding failed (RuntimeError: SECRET_ENCODING)\nSECRET_IMAGE\nPlease replace or correct these reference photos. Sorting has not started.")
        self.run_worker()
        self.sorter.sort_all.assert_not_called()
        self.assertIn('Bad.jpg', self.dialog.call_args.args[1])
        self.assertIn('Reference validation', self.summary())
        self.assertNotIn('SECRET', self.summary())
        self.restored()

    def test_worker_failure_is_incomplete(self):
        self.sorter.sort_all.side_effect = RuntimeError('SECRET_ENCODING')
        self.run_worker()
        self.assertIn('incomplete', self.status().lower())
        self.assertNotIn('SECRET_ENCODING', self.summary())
        self.assertNotIn('Sorting complete.', self.summary())
        self.restored()

    def test_fatal_output_guidance_no_invented_counts(self):
        self.sorter.sort_all.side_effect = OSError(28, 'disk full')
        self.run_worker()
        for text in ('Activity sorting', 'disk space', 'remain', 'group', 'unavailable', 'retry'):
            self.assertIn(text, self.summary())
        self.assertNotIn('Matched:', self.summary())
        self.assertEqual(self.app._progress_var.set.call_count, 0)

    def test_cancel_is_not_success_or_full_progress(self):
        self.app._sort_start_time = 10.0
        self.app._cancel_flag.set()
        self.run_worker()
        self.assertIn('cancelled', self.status())
        self.assertNotIn('Sorting complete.', self.summary())
        self.assertNotIn('Done in', str(self.app._timer_label.mock_calls))
        self.app._progress_var.set.assert_not_called()
        self.app.after_cancel.assert_called_once_with('timer')
        self.restored()

    def test_worker_only_queues_ui(self):
        worker = threading.Thread(target=self.app._run_sorting, args=(self.sorter,))
        worker.start()
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.app._summary_text.insert.assert_not_called()
        self.app._status_label.config.assert_not_called()
        self.assertTrue(self.queue)
        self.drain()
        self.assertEqual(self.status(), 'Sorting complete.')

    def test_progress_only_queues_ui(self):
        self.app._on_progress(1, 4, 'synthetic.jpg')
        self.app._on_ref_progress(1, 2, 'Ali')
        self.app._status_label.config.assert_not_called()
        self.drain()
        self.app._progress_var.set.assert_called_once_with(25)

    def prepare_start(self, root):
        for attr, name in (('_reference_var', 'ref'), ('_events_var', 'events'), ('_output_var', 'out')):
            folder = root / name
            folder.mkdir()
            setattr(self.app, attr, Mock(get=Mock(return_value=str(folder))))
        self.app._start_ticker = Mock()

    def test_logger_failure_prevents_worker_and_restores(self):
        with tempfile.TemporaryDirectory() as temp:
            self.prepare_start(Path(temp))
            with patch.object(self.gui, 'setup_logger', side_effect=PermissionError('denied')), patch.object(self.gui.threading, 'Thread') as thread:
                self.app._on_start()
            thread.assert_not_called()
        self.assertIn('Logger initialization', self.summary())
        self.assertIn('kindersort_log.txt', self.dialog.call_args.args[1])
        self.restored()

    def test_output_creation_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            self.prepare_start(Path(temp))
            with patch.object(Path, 'mkdir', side_effect=PermissionError('denied')), patch.object(self.gui, 'setup_logger') as logger:
                self.app._on_start()
            logger.assert_not_called()
        self.assertIn('Output folder', self.dialog.call_args.args[1])
        self.assertNotIn('Sorting complete.', str(self.app._summary_text.mock_calls))
        self.restored()

    def test_thread_start_failure_restores(self):
        with tempfile.TemporaryDirectory() as temp:
            self.prepare_start(Path(temp))
            with patch.object(self.gui, 'setup_logger'), patch.object(self.gui.threading, 'Thread') as thread:
                thread.return_value.start.side_effect = RuntimeError('cannot start')
                self.app._on_start()
        self.assertIn('Worker startup', self.summary())
        self.restored()

    def test_missing_inputs_keep_validation(self):
        for attr in ('_reference_var', '_events_var', '_output_var'):
            setattr(self.app, attr, Mock(get=Mock(return_value='')))
        with patch.object(self.gui, 'setup_logger') as logger:
            self.app._on_start()
        logger.assert_not_called()
        self.assertEqual(self.dialog.call_args.args[0], 'Missing folders')

    def test_no_reference_encodings(self):
        self.sorter._student_encodings = {}
        self.run_worker()
        self.sorter.sort_all.assert_not_called()
        self.restored()

    def test_zero_images_warning(self):
        self.stats.update(total=0, matched=0, unmatched=0)
        self.run_worker()
        self.warning.assert_called_once()
        self.restored()

    def test_elapsed_timer_cancelled_after_success(self):
        self.app._sort_start_time = 10.0
        with patch.object(self.gui.time, 'monotonic', return_value=75.0):
            self.run_worker()
        self.app.after_cancel.assert_called_once_with('timer')
        self.assertIn('01:05', self.app._timer_label.config.call_args.kwargs['text'])
        self.restored()

    def test_elapsed_timer_cancelled_after_failure(self):
        self.app._sort_start_time = 10.0
        self.sorter.sort_all.side_effect = OSError('failure')
        self.run_worker()
        self.app.after_cancel.assert_called_once_with('timer')
        self.assertEqual(self.app._timer_label.config.call_args.kwargs['text'], '')
        self.restored()

    def test_cancel_button_signals_existing_event(self):
        self.app._on_cancel()
        self.assertTrue(self.app._cancel_flag.is_set())
        self.assertEqual(self.app._cancel_btn.config.call_args.kwargs['state'], 'disabled')
        self.assertIn('Cancelling', self.status())

    def test_folder_overlap_prevents_logger_and_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            self.prepare_start(Path(temp))
            self.app._output_var.get.return_value = self.app._events_var.get.return_value
            with patch.object(self.gui, 'setup_logger') as logger, patch.object(self.gui.threading, 'Thread') as thread:
                self.app._on_start()
            logger.assert_not_called()
            thread.assert_not_called()
        self.assertEqual(self.dialog.call_args.args[0], 'Invalid folder configuration')

    def test_existing_files_preserved_on_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'existing.jpg'
            target.write_bytes(b'synthetic existing output')
            before = (target.read_bytes(), target.stat().st_mtime_ns)
            self.sorter.sort_all.side_effect = PermissionError('destination denied')
            self.run_worker()
            self.assertEqual((target.read_bytes(), target.stat().st_mtime_ns), before)

    def test_real_group_partial_failure_reaches_gui(self):
        import test_reserved_reference_names as fixtures
        fixture = fixtures.TestReservedReferenceNames()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.image(fixture.events, 'group.jpg')
        sorter = fixture.sorter
        sorter._student_encodings = {'Ali': fixture.encoding, 'Bob': [1.0] * 128}
        sorter.load_references = Mock(return_value=[])
        fixture.faces.face_encodings.return_value = [fixture.encoding, [1.0] * 128]
        fixture.faces.face_distance.side_effect = lambda known, face: [0., 1.] if face == fixture.encoding else [1., 0.]
        existing = fixture.output / 'existing.jpg'
        existing.write_bytes(b'keep existing output')
        before = (existing.read_bytes(), existing.stat().st_mtime_ns)
        real_open = Path.open
        completed = []

        def open_file(path, mode='r', *args, **kwargs):
            if mode == 'xb':
                completed.append(path)
                if len(completed) == 2:
                    raise OSError(28, 'disk full')
            return real_open(path, mode, *args, **kwargs)

        with patch.object(Path, 'open', open_file):
            self.app._run_sorting(sorter)
        self.assertEqual(len(completed), 2)
        self.assertEqual(completed[0].read_bytes(), (fixture.events / 'group.jpg').read_bytes())
        self.assertEqual((existing.read_bytes(), existing.stat().st_mtime_ns), before)
        self.drain()
        self.assertIn('incomplete', self.status())
        self.assertIn('counts are unavailable', self.summary())
        self.assertNotIn('Sorting complete.', self.summary())
        self.restored()


if __name__ == '__main__':
    unittest.main()
