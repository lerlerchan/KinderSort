"""
main.py — KinderSort GUI entry point.

Single-window tkinter application that drives the PhotoSorter pipeline.
"""

import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from datetime import datetime

from sorter import PhotoSorter
from utils import setup_logger

# Try importing docx for report generation
try:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from PIL import Image
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False


class KinderSortApp(tk.Tk):
    """Main application window for KinderSort — Student Photo Organiser."""

    MIN_WIDTH = 500
    MIN_HEIGHT = 480

    def __init__(self) -> None:
        """Initialise the window, build all widgets, and configure layout."""
        super().__init__()
        self.title("KinderSort Lite v1.1 — Student Photo Organiser")
        self.minsize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resizable(True, True)

        # StringVars for the three folder paths
        self._reference_var = tk.StringVar()
        self._events_var = tk.StringVar()
        self._output_var = tk.StringVar()

        # Cancellation flag shared between GUI and worker thread
        self._cancel_flag = threading.Event()

        # Spinner / elapsed timer state
        self._spinner_frames = ["🕐", "🕑", "🕒", "🕓", "🕔", "🕕", "🕖", "🕗", "🕘", "🕙", "🕚", "🕛"]
        self._spinner_idx = 0
        self._sort_start_time: float | None = None
        self._ticker_id: str | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        """Build and pack all widgets into the main window."""
        root_frame = tk.Frame(self, padx=16, pady=16)
        root_frame.pack(fill=tk.BOTH, expand=True)

        # Title label
        title_frame = tk.Frame(root_frame)
        title_frame.pack(fill=tk.X, pady=(0, 12))

        tk.Label(
            title_frame,
            text="KinderSort Lite — Student Photo Organiser",
            font=("Helvetica", 14, "bold"),
        ).pack(side=tk.LEFT)

        tk.Label(
            title_frame,
            text="v1.1",
            font=("Helvetica", 9),
            fg="#666",
        ).pack(side=tk.LEFT, padx=(8, 0))

        # Folder selector rows
        folders_frame = tk.LabelFrame(root_frame, text="Folders", padx=8, pady=8)
        folders_frame.pack(fill=tk.X, pady=(0, 12))

        self._build_folder_row(folders_frame, "Reference Photos:", self._reference_var, 0)
        self._build_folder_row(folders_frame, "Events Folder:", self._events_var, 1)
        self._build_folder_row(folders_frame, "Output Folder:", self._output_var, 2)

        folders_frame.columnconfigure(1, weight=1)

        # Button row
        btn_frame = tk.Frame(root_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 12))

        self._start_btn = tk.Button(
            btn_frame,
            text="▶ Start Sorting",
            font=("Helvetica", 11, "bold"),
            bg="#4CAF50",
            fg="white",
            activebackground="#388E3C",
            activeforeground="white",
            padx=16,
            pady=8,
            command=self._on_start,
        )
        self._start_btn.pack(side=tk.LEFT, padx=(0, 8))

        self._cancel_btn = tk.Button(
            btn_frame,
            text="✖ Cancel",
            font=("Helvetica", 11),
            padx=16,
            pady=8,
            state=tk.DISABLED,
            command=self._on_cancel,
        )
        self._cancel_btn.pack(side=tk.LEFT)

        self._report_btn = tk.Button(
            btn_frame,
            text="📄 Generate Report",
            font=("Helvetica", 10),
            bg="#2196F3",
            fg="white",
            activebackground="#1976D2",
            activeforeground="white",
            padx=16,
            pady=8,
            command=self._on_generate_report,
        )
        self._report_btn.pack(side=tk.LEFT, padx=(8, 0))

        # Progress section
        progress_frame = tk.LabelFrame(root_frame, text="Progress", padx=8, pady=8)
        progress_frame.pack(fill=tk.X, pady=(0, 12))

        self._progress_var = tk.DoubleVar(value=0.0)
        self._progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self._progress_var,
            maximum=100,
            mode="determinate",
        )
        self._progress_bar.pack(fill=tk.X, pady=(0, 4))

        self._status_label = tk.Label(
            progress_frame, text="Ready.", anchor="w", wraplength=460
        )
        self._status_label.pack(fill=tk.X)

        self._timer_label = tk.Label(
            progress_frame, text="", anchor="w", fg="#555555"
        )
        self._timer_label.pack(fill=tk.X)

        # Summary box
        summary_frame = tk.LabelFrame(root_frame, text="Summary", padx=8, pady=8)
        summary_frame.pack(fill=tk.BOTH, expand=True)

        self._summary_text = tk.Text(
            summary_frame, height=5, state=tk.DISABLED, wrap=tk.WORD
        )
        self._summary_text.pack(fill=tk.BOTH, expand=True)

    def _build_folder_row(self, parent, label_text, string_var, row):
        tk.Label(parent, text=label_text, anchor="w").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        entry = tk.Entry(parent, textvariable=string_var, state="readonly", width=40)
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        btn = tk.Button(parent, text="Browse…", command=lambda v=string_var: self._browse_folder(v))
        btn.grid(row=row, column=2, padx=(8, 0), pady=4)

    def _browse_folder(self, string_var):
        folder = filedialog.askdirectory(title="Select folder")
        if folder:
            string_var.set(folder)

    def _on_start(self):
        ref = self._reference_var.get().strip()
        events = self._events_var.get().strip()
        output = self._output_var.get().strip()

        if not ref or not events or not output:
            messagebox.showerror("Missing folders", "Please select all three folders before starting.")
            return

        ref_path = Path(ref)
        events_path = Path(events)
        output_path = Path(output)

        if not ref_path.is_dir() or not events_path.is_dir():
            messagebox.showerror("Invalid folder", "Reference and Events folders must exist.")
            return

        output_path.mkdir(parents=True, exist_ok=True)

        self._start_btn.config(state=tk.DISABLED)
        self._cancel_btn.config(state=tk.NORMAL)
        self._report_btn.config(state=tk.DISABLED)
        self._cancel_flag.clear()
        self._clear_summary()
        self._progress_var.set(0)
        self._set_status("Loading reference photos…")
        self._start_ticker()

        logger = setup_logger(output_path)
        sorter = PhotoSorter(ref_path, events_path, output_path, logger, enhance_images=True, use_cache=True)

        thread = threading.Thread(target=self._run_sorting, args=(sorter,), daemon=True)
        thread.start()

    def _run_sorting(self, sorter):
        try:
            skipped_names = sorter.load_references(progress_callback=self._on_ref_progress)
            if skipped_names:
                self.after(0, self._show_ref_warning, skipped_names)
            if sorter._student_encodings:
                summary = sorter.sort_all(progress_callback=self._on_progress, cancelled=self._cancel_flag.is_set)
                self.after(0, self._on_done, summary)
            else:
                self.after(0, self._on_error, "No student faces could be loaded.")
        except Exception as e:
            self.after(0, self._on_error, str(e))

    def _start_ticker(self):
        self._sort_start_time = time.monotonic()
        self._spinner_idx = 0
        self._tick()

    def _tick(self):
        if self._sort_start_time is None:
            return
        elapsed = int(time.monotonic() - self._sort_start_time)
        minutes, seconds = divmod(elapsed, 60)
        spinner = self._spinner_frames[self._spinner_idx % len(self._spinner_frames)]
        self._spinner_idx += 1
        self._timer_label.config(text=f"{spinner}  {minutes:02d}:{seconds:02d} elapsed")
        self._ticker_id = self.after(250, self._tick)

    def _stop_ticker(self, final_elapsed=None):
        if self._ticker_id:
            self.after_cancel(self._ticker_id)
            self._ticker_id = None
        if final_elapsed is not None:
            minutes, seconds = divmod(final_elapsed, 60)
            self._timer_label.config(text=f"✅  Done in {minutes:02d}:{seconds:02d}")
        else:
            self._timer_label.config(text="")
        self._sort_start_time = None

    def _on_ref_progress(self, current, total, name):
        self.after(0, self._set_status, f"Loading references [{current}/{total}]: {name}…")

    def _show_ref_warning(self, skipped_names):
        names_str = "\n".join(f"  • {n}" for n in skipped_names)
        messagebox.showwarning(
            "Reference photos without faces",
            f"No face was detected for:\n\n{names_str}\n\nThese students will be skipped."
        )

    def _on_cancel(self):
        self._cancel_flag.set()
        self._cancel_btn.config(state=tk.DISABLED)
        self._set_status("Cancelling…")

    def _on_progress(self, current, total, filename):
        self.after(0, self._apply_progress, current, total, filename)

    def _apply_progress(self, current, total, filename):
        pct = (current / total * 100) if total else 0
        self._progress_var.set(pct)
        self._set_status(f"[{current}/{total}] {filename}")

    def _on_done(self, summary):
        elapsed = int(time.monotonic() - self._sort_start_time) if self._sort_start_time else None
        self._stop_ticker(final_elapsed=elapsed)
        self._start_btn.config(state=tk.NORMAL)
        self._cancel_btn.config(state=tk.DISABLED)
        self._report_btn.config(state=tk.NORMAL)
        self._progress_var.set(100)

        cancelled = self._cancel_flag.is_set()
        status = "Sorting cancelled." if cancelled else "Sorting complete."
        self._set_status(status)

        lines = [status, "",
                 f"Total images found : {summary['total']}",
                 f"Matched (sorted)   : {summary['matched']}",
                 f"Unmatched          : {summary['unmatched']}",
                 f"Skipped (errors)   : {summary['skipped']}"]
        self._write_summary("\n".join(lines))

    def _on_error(self, message):
        self._stop_ticker()
        self._start_btn.config(state=tk.NORMAL)
        self._cancel_btn.config(state=tk.DISABLED)
        self._report_btn.config(state=tk.NORMAL)
        self._set_status("An error occurred.")
        messagebox.showerror("Unexpected error", message)

    def _on_generate_report(self):
        from export_matched_photos import main as export_main
        try:
            export_main()
        except Exception as e:
            messagebox.showerror("Report Error", str(e))

    def _set_status(self, text):
        self._status_label.config(text=text)

    def _write_summary(self, text):
        self._summary_text.config(state=tk.NORMAL)
        self._summary_text.delete("1.0", tk.END)
        self._summary_text.insert(tk.END, text)
        self._summary_text.config(state=tk.DISABLED)

    def _clear_summary(self):
        self._write_summary("")


def main():
    app = KinderSortApp()
    app.mainloop()


if __name__ == "__main__":
    main()