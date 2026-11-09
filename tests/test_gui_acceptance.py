"""D15 controller acceptance; no real GUI or face recognition work."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import test_gui_error_recovery as controller
import test_input_path_safety as boundaries


class TestGuiAcceptance(unittest.TestCase):
    setUp = controller.TestGuiErrorRecovery.setUp
    drain = controller.TestGuiErrorRecovery.drain
    summary = controller.TestGuiErrorRecovery.summary
    status = controller.TestGuiErrorRecovery.status
    restored = controller.TestGuiErrorRecovery.restored
    run_worker = controller.TestGuiErrorRecovery.run_worker
    prepare_start = controller.TestGuiErrorRecovery.prepare_start

    def test_initialization_and_widget_defaults(self):
        with patch.object(self.gui.tk.Tk, '__init__'), \
                patch.object(self.gui.KinderSortApp, 'title'), \
                patch.object(self.gui.KinderSortApp, 'minsize'), \
                patch.object(self.gui.KinderSortApp, 'resizable'), \
                patch.object(self.gui.KinderSortApp, 'protocol') as protocol, \
                patch.object(self.gui.tk, 'StringVar'), \
                patch.object(self.gui.KinderSortApp, '_build_ui'):
            app = self.gui.KinderSortApp()
        self.assertFalse(app._cancel_flag.is_set())
        self.assertIsNone(app._worker)
        self.assertFalse(app._closing)
        protocol.assert_called_once_with('WM_DELETE_WINDOW', app._on_close)
        # Exercise real widget construction with toolkit factories replaced.
        with patch.multiple(self.gui.tk, **{name: Mock() for name in (
                'Frame', 'LabelFrame', 'Label', 'Entry', 'Button', 'Text', 'DoubleVar')}):
            button = self.gui.tk.Button
            label = self.gui.tk.Label
            entry = self.gui.tk.Entry
            with patch.object(self.gui.ttk, 'Progressbar') as progress:
                app._build_ui()
            buttons = {call.kwargs['text']: call.kwargs for call in button.call_args_list}
            self.assertEqual(buttons['Cancel']['state'], 'disabled')
            self.assertEqual(buttons['Start Sorting']['command'], app._on_start)
            self.assertEqual(sum(call.kwargs.get('text') == 'Browse…' for call in button.call_args_list), 3)
            self.assertEqual(len(entry.call_args_list), 3)
            self.assertTrue(all(call.kwargs['state'] == 'readonly' for call in entry.call_args_list))
            self.assertTrue(any(call.kwargs.get('text') == 'Ready.' for call in label.call_args_list))
            self.assertEqual(progress.call_args.kwargs['maximum'], 100)

    def test_browse_each_selection_and_cancel(self):
        for chosen in ('reference fixture', 'event fixture', 'output fixture'):
            variable = Mock()
            with patch.object(self.gui.filedialog, 'askdirectory', return_value=chosen):
                self.app._browse_folder(variable)
            variable.set.assert_called_once_with(chosen)
        variable = Mock()
        with patch.object(self.gui.filedialog, 'askdirectory', return_value=''):
            self.app._browse_folder(variable)
        variable.set.assert_not_called()

    def test_partial_selections_never_start_worker(self):
        for selected in range(1, 7):
            with self.subTest(mask=selected):
                for bit, attr in enumerate(('_reference_var', '_events_var', '_output_var')):
                    setattr(self.app, attr, Mock(get=Mock(return_value='fixture' if selected & (1 << bit) else '')))
                with patch.object(self.gui.threading, 'Thread') as thread:
                    self.app._on_start()
                thread.assert_not_called()
                self.assertEqual(self.dialog.call_args.args[0], 'Missing folders')

    def test_missing_reference_and_event_directory(self):
        for missing in ('_reference_var', '_events_var'):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temp:
                self.prepare_start(Path(temp))
                getattr(self.app, missing).get.return_value = str(Path(temp) / 'not-created')
                with patch.object(self.gui, 'setup_logger') as logger, patch.object(self.gui.threading, 'Thread') as thread:
                    self.app._on_start()
                logger.assert_not_called()
                thread.assert_not_called()
                self.assertEqual(self.dialog.call_args.args[0], 'Invalid folder')

    def test_duplicate_start_cannot_overlap_workers(self):
        with tempfile.TemporaryDirectory() as temp:
            self.prepare_start(Path(temp))
            with patch.object(self.gui, 'setup_logger'), patch.object(self.gui.threading, 'Thread') as thread:
                thread.return_value.is_alive.return_value = True
                self.app._on_start()
                self.app._on_start()
            self.assertEqual(thread.call_count, 1)
            thread.return_value.start.assert_called_once()

    def fixture(self):
        fixture = boundaries.TestInputPathSafety()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def test_d14_event_junction_reaches_gui_and_allows_retry(self):
        fixture = self.fixture()
        alias = fixture.events / 'linked'
        fixture.link(alias, fixture.external)
        fixture.sorter._student_encodings = {'Ali': fixture.encoding}
        fixture.sorter.load_references = Mock(return_value=[])
        self.app._run_sorting(fixture.sorter)
        self.drain()
        self.assertIn('Activity sorting', self.summary())
        self.assertIn('incomplete', self.status().lower())
        self.restored()
        self.assertEqual(list(fixture.output.iterdir()), [])
        # Retry after the input is corrected, with the same controller.
        fixture.sorter.events_folder = fixture.references
        self.app._run_sorting(fixture.sorter)
        self.drain()
        self.assertEqual(self.status(), 'Sorting complete.')
        self.restored()

    def test_d14_reference_junction_stops_before_sort(self):
        fixture = self.fixture()
        fixture.link(fixture.references / 'linked', fixture.external)
        with patch.object(fixture.sorter, 'sort_all') as sort_all:
            self.app._run_sorting(fixture.sorter)
            self.drain()
        sort_all.assert_not_called()
        self.assertIn('Reference validation', self.summary())
        self.restored()

    def test_progress_zero_and_fraction(self):
        for current, total, expected in ((0, 0, 0), (1, 4, 25), (3, 4, 75), (4, 4, 100)):
            self.app._on_progress(current, total, 'synthetic.jpg')
            self.drain()
            self.assertEqual(self.app._progress_var.set.call_args.args[0], expected)

    def slow_worker(self, root):
        """Pause after one real synthetic copy, released by cancellation."""
        copied = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)
        source = root / 'source.jpg'
        source.write_bytes(b'synthetic D15 source')
        target = root / 'completed.jpg'

        def slow(progress_callback, cancelled):
            target.write_bytes(source.read_bytes())
            copied.set()
            if not release.wait(3):
                raise RuntimeError('Test synchronization timed out')
            self.assertTrue(cancelled())
            return dict(total=2, matched=1, unmatched=0, skipped=0, errors=0)

        self.sorter.sort_all.side_effect = slow
        worker = threading.Thread(target=self.app._run_sorting, args=(self.sorter,))
        self.app._worker = worker
        self.addCleanup(lambda: worker.join(4))
        self.addCleanup(release.set)
        worker.start()
        self.assertTrue(copied.wait(3))
        return worker, release, source, target

    def test_cancel_slow_worker_retains_completed_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            worker, release, source, target = self.slow_worker(Path(temp))
            self.app._on_cancel()
            self.assertTrue(worker.is_alive())
            release.set()
            worker.join(3)
            self.assertFalse(worker.is_alive())
            self.drain()
            self.assertEqual(target.read_bytes(), source.read_bytes())
            self.assertIn('cancelled', self.status())
            self.assertNotIn('Sorting complete.', self.summary())
            self.assertNotIn(100, [call.args[0] for call in self.app._progress_var.set.call_args_list])
            self.restored()

    def test_close_waits_for_worker_and_preserves_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            worker, release, source, target = self.slow_worker(Path(temp))
            self.app.destroy = Mock()
            self.app._on_close()
            self.assertTrue(self.app._cancel_flag.is_set())
            self.app.destroy.assert_not_called()
            self.assertTrue(worker.is_alive())
            # Closing must also reject a new task.
            with patch.object(self.gui, 'setup_logger') as logger:
                self.app._on_start()
            logger.assert_not_called()
            release.set()
            worker.join(3)
            self.assertFalse(worker.is_alive())
            self.drain()
            self.app.destroy.assert_called_once()
            self.dialog.assert_not_called()
            self.assertEqual(target.read_bytes(), source.read_bytes())

    def test_close_idle_destroys_once(self):
        self.app.destroy = Mock()
        self.app._on_close()
        self.app._on_close()
        self.app.destroy.assert_called_once()

    def test_closing_worker_error_does_not_show_modal_dialog(self):
        self.app._closing = True
        self.sorter.sort_all.side_effect = RuntimeError('synthetic failure')
        self.run_worker()
        self.dialog.assert_not_called()

    def test_failure_then_success_can_restart(self):
        self.sorter.sort_all.side_effect = RuntimeError('synthetic failure')
        self.run_worker()
        self.restored()
        self.sorter.sort_all.side_effect = None
        self.run_worker()
        self.assertEqual(self.status(), 'Sorting complete.')
        self.restored()

    def test_worker_never_updates_widgets_directly(self):
        owner = threading.get_ident()
        mutations = []

        def mutation(*args, **kwargs):
            mutations.append(threading.get_ident())

        for name in ('_start_btn', '_cancel_btn', '_status_label', '_timer_label', '_summary_text'):
            getattr(self.app, name).config.side_effect = mutation
        self.app._progress_var.set.side_effect = mutation

        def sort(progress_callback, cancelled):
            progress_callback(1, 2, 'synthetic.jpg')
            return self.stats

        self.sorter.sort_all.side_effect = sort
        worker = threading.Thread(target=self.app._run_sorting, args=(self.sorter,))
        worker.start()
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(mutations, [])
        self.drain()
        self.assertTrue(mutations)
        self.assertEqual(set(mutations), {owner})
