"""
main.py — KinderSort Lite GUI entry point.

Enhanced version with preprocessing toggle, ensemble detection,
normalized match margin display, two-threshold review system,
strict reference validation, secure cache management, and accuracy metrics.
"""

import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from enhanced_sorter import EnhancedPhotoSorter
from utils import setup_logger


class KinderSortLiteApp(tk.Tk):
    """Main application window for KinderSort Lite — Enhanced Student Photo Organiser."""

    MIN_WIDTH = 580
    MIN_HEIGHT = 600

    def __init__(self) -> None:
        super().__init__()
        self.title("KinderSort Lite — Ethical AI Photo Organiser")
        self.minsize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resizable(True, True)

        # StringVars
        self._reference_var = tk.StringVar()
        self._events_var = tk.StringVar()
        self._output_var = tk.StringVar()

        # Enhancement toggles
        self._preprocessing_var = tk.BooleanVar(value=True)
        self._ensemble_var = tk.BooleanVar(value=True)
        self._cache_var = tk.BooleanVar(value=True)
        self._fast_mode_var = tk.BooleanVar(value=False)

        # Cancellation
        self._cancel_flag = threading.Event()

        # Spinner
        self._spinner_frames = ["🕐", "🕑", "🕒", "🕓", "🕔", "🕕", "🕖", "🕗", "🕘", "🕙", "🕚", "🕛"]
        self._spinner_idx = 0
        self._sort_start_time: float | None = None
        self._ticker_id: str | None = None

        self._build_ui()

    # ------------------------------------------------------------------
    # Widget construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root_frame = tk.Frame(self, padx=16, pady=16)
        root_frame.pack(fill=tk.BOTH, expand=True)

        # Title
        tk.Label(
            root_frame,
            text="🏫 KinderSort Lite — Ethical AI Photo Organiser",
            font=("Helvetica", 13, "bold"),
        ).pack(anchor="w", pady=(0, 4))

        tk.Label(
            root_frame,
            text="AI-enhanced face recognition • Offline • Low-resource • Privacy-first",
            font=("Helvetica", 9),
            fg="#666666",
        ).pack(anchor="w", pady=(0, 12))

        # Folder selectors
        folders_frame = tk.LabelFrame(root_frame, text="📁 Folders", padx=8, pady=8)
        folders_frame.pack(fill=tk.X, pady=(0, 12))

        self._build_folder_row(folders_frame, "Reference Photos:", self._reference_var, 0)
        self._build_folder_row(folders_frame, "Events Folder:", self._events_var, 1)
        self._build_folder_row(folders_frame, "Output Folder:", self._output_var, 2)
        folders_frame.columnconfigure(1, weight=1)

        # Enhancement options
        options_frame = tk.LabelFrame(root_frame, text="⚙️ AI Enhancement Options", padx=8, pady=8)
        options_frame.pack(fill=tk.X, pady=(0, 12))

        tk.Checkbutton(
            options_frame,
            text="Image Preprocessing (CLAHE enhancement — improves accuracy in poor lighting)",
            variable=self._preprocessing_var,
        ).pack(anchor="w")

        tk.Checkbutton(
            options_frame,
            text="Ensemble Detection (HOG + CNN — higher face detection recall)",
            variable=self._ensemble_var,
        ).pack(anchor="w")

        tk.Checkbutton(
            options_frame,
            text="Cache Encodings (skips re-encoding on re-run — faster)",
            variable=self._cache_var,
        ).pack(anchor="w")

        tk.Checkbutton(
            options_frame,
            text="Fast Mode (HOG only, skip CNN — best for slow laptops with large batches)",
            variable=self._fast_mode_var,
        ).pack(anchor="w")

        # --- Cache management row ---------------------------------------
        cache_frame = tk.Frame(options_frame)
        cache_frame.pack(fill=tk.X, pady=(4, 0))

        self._clear_cache_btn = tk.Button(
            cache_frame,
            text="🗑 Delete Biometric Cache",
            font=("Helvetica", 9),
            padx=8,
            pady=2,
            command=self._on_clear_cache,
        )
        self._clear_cache_btn.pack(side=tk.LEFT)

        self._cache_status_label = tk.Label(
            cache_frame,
            text="",
            font=("Helvetica", 8),
            fg="#888888",
        )
        self._cache_status_label.pack(side=tk.LEFT, padx=(8, 0))

        # Update cache status label
        self._update_cache_status()

        # Privacy notice
        privacy_frame = tk.Frame(options_frame)
        privacy_frame.pack(fill=tk.X, pady=(4, 0))
        tk.Label(
            privacy_frame,
            text="🔒 Facial encodings are stored locally in your app data folder "
                 "(~/.kindersort/cache/). No data ever leaves this computer.",
            font=("Helvetica", 8),
            fg="#888888",
            wraplength=520,
        ).pack(anchor="w")

        # Buttons
        btn_frame = tk.Frame(root_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 12))

        self._start_btn = tk.Button(
            btn_frame,
            text="🚀 Start Sorting",
            font=("Helvetica", 11, "bold"),
            bg="#2E86C1",
            fg="white",
            activebackground="#1B4F72",
            activeforeground="white",
            padx=16,
            pady=8,
            command=self._on_start,
        )
        self._start_btn.pack(side=tk.LEFT, padx=(0, 8))

        self._cancel_btn = tk.Button(
            btn_frame,
            text="Cancel",
            font=("Helvetica", 11),
            padx=16,
            pady=8,
            state=tk.DISABLED,
            command=self._on_cancel,
        )
        self._cancel_btn.pack(side=tk.LEFT)

        # Progress section
        self._build_progress_section(root_frame)

        # Summary box
        self._build_summary_box(root_frame)

    def _build_folder_row(
        self, parent: tk.Widget, label_text: str, string_var: tk.StringVar, row: int
    ) -> None:
        tk.Label(parent, text=label_text, anchor="w").grid(
            row=row, column=0, sticky="w", padx=(0, 8), pady=4
        )
        entry = tk.Entry(parent, textvariable=string_var, state="readonly", width=40)
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        btn = tk.Button(
            parent, text="Browse…", command=lambda v=string_var: self._browse_folder(v)
        )
        btn.grid(row=row, column=2, padx=(8, 0), pady=4)

    def _build_progress_section(self, parent: tk.Widget) -> None:
        progress_frame = tk.LabelFrame(parent, text="📊 Progress", padx=8, pady=8)
        progress_frame.pack(fill=tk.X, pady=(0, 12))

        self._progress_var = tk.DoubleVar(value=0.0)
        self._progress_bar = ttk.Progressbar(
            progress_frame, variable=self._progress_var, maximum=100, mode="determinate"
        )
        self._progress_bar.pack(fill=tk.X, pady=(0, 4))

        self._status_label = tk.Label(
            progress_frame, text="Ready.", anchor="w", wraplength=540
        )
        self._status_label.pack(fill=tk.X)

        self._timer_label = tk.Label(
            progress_frame, text="", anchor="w", fg="#555555"
        )
        self._timer_label.pack(fill=tk.X)

    def _build_summary_box(self, parent: tk.Widget) -> None:
        summary_frame = tk.LabelFrame(parent, text="📋 Summary", padx=8, pady=8)
        summary_frame.pack(fill=tk.BOTH, expand=True)

        self._summary_text = tk.Text(
            summary_frame, height=8, state=tk.DISABLED, wrap=tk.WORD
        )
        self._summary_text.pack(fill=tk.BOTH, expand=True)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _browse_folder(self, string_var: tk.StringVar) -> None:
        folder = filedialog.askdirectory(title="Select folder")
        if folder:
            string_var.set(folder)

    def _on_clear_cache(self) -> None:
        """Delete the biometric encoding cache from app data."""
        if not EnhancedPhotoSorter.cache_exists():
            messagebox.showinfo(
                "No Cache Found",
                "There is no biometric cache to delete.\n\n"
                "The cache is created the first time you run a sort with "
                "'Cache Encodings' enabled.",
            )
            return

        confirm = messagebox.askyesno(
            "Delete Biometric Cache",
            "This will delete all cached facial encodings from your app data.\n\n"
            "The cache will be regenerated on the next sort if 'Cache Encodings' "
            "is enabled. This does NOT affect your reference photos or sorted output.\n\n"
            "Are you sure you want to delete the cache?",
        )
        if confirm:
            success = EnhancedPhotoSorter.clear_cache()
            if success:
                self._cache_status_label.config(text="✅ Cache deleted")
                messagebox.showinfo("Cache Deleted", "Biometric cache has been cleared.")
            else:
                messagebox.showerror("Error", "Could not delete the cache file.")
        self._update_cache_status()

    def _update_cache_status(self) -> None:
        """Update the cache status indicator."""
        if EnhancedPhotoSorter.cache_exists():
            self._cache_status_label.config(text="📦 Cache exists")
        else:
            self._cache_status_label.config(text="📭 No cache")

    def _on_start(self) -> None:
        ref = self._reference_var.get().strip()
        events = self._events_var.get().strip()
        output = self._output_var.get().strip()

        if not ref or not events or not output:
            messagebox.showerror(
                "Missing folders",
                "Please select all three folders before starting.",
            )
            return

        ref_path = Path(ref)
        events_path = Path(events)
        output_path = Path(output)

        for path, name in [(ref_path, "Reference"), (events_path, "Events")]:
            if not path.is_dir():
                messagebox.showerror("Invalid folder", f"{name} folder does not exist:\n{path}")
                return

        try:
            output_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Output folder error", f"Cannot create output folder:\n{exc}")
            return

        self._start_btn.config(state=tk.DISABLED)
        self._cancel_btn.config(state=tk.NORMAL)
        self._cancel_flag.clear()
        self._clear_summary()
        self._progress_var.set(0)
        self._set_status("🔍 Loading reference photos with AI enhancement…")
        self._start_ticker()

        logger = setup_logger(output_path)
        sorter = EnhancedPhotoSorter(
            ref_path,
            events_path,
            output_path,
            logger,
            use_preprocessing=self._preprocessing_var.get(),
            use_cache=self._cache_var.get(),
            ensemble_detection=self._ensemble_var.get(),
            fast_mode=self._fast_mode_var.get(),
        )

        thread = threading.Thread(
            target=self._run_sorting, args=(sorter,), daemon=True
        )
        thread.start()

    def _run_sorting(self, sorter: EnhancedPhotoSorter) -> None:
        try:
            skipped_names = sorter.load_references(
                progress_callback=self._on_ref_progress
            )
        except Exception as exc:
            self.after(0, self._on_error, str(exc))
            return

        if skipped_names:
            self.after(0, self._show_ref_warning, skipped_names)

        if not sorter._student_encodings:
            self.after(
                0,
                self._on_error,
                "No student faces could be loaded. Please check your Reference folder.",
            )
            return

        try:
            summary = sorter.sort_all(
                progress_callback=self._on_progress,
                cancelled=self._cancel_flag.is_set,
            )
            self.after(0, self._on_done, summary)
        except Exception as exc:
            self.after(0, self._on_error, str(exc))

    def _start_ticker(self) -> None:
        self._sort_start_time = time.monotonic()
        self._spinner_idx = 0
        self._tick()

    def _tick(self) -> None:
        if self._sort_start_time is None:
            return
        elapsed = int(time.monotonic() - self._sort_start_time)
        minutes, seconds = divmod(elapsed, 60)
        spinner = self._spinner_frames[self._spinner_idx % len(self._spinner_frames)]
        self._spinner_idx += 1
        self._timer_label.config(text=f"{spinner}  {minutes:02d}:{seconds:02d} elapsed")
        self._ticker_id = self.after(250, self._tick)

    def _stop_ticker(self, final_elapsed: int | None = None) -> None:
        if self._ticker_id:
            self.after_cancel(self._ticker_id)
            self._ticker_id = None
        if final_elapsed is not None:
            minutes, seconds = divmod(final_elapsed, 60)
            self._timer_label.config(text=f"✅  Done in {minutes:02d}:{seconds:02d}")
        else:
            self._timer_label.config(text="")
        self._sort_start_time = None

    def _on_ref_progress(self, current: int, total: int, name: str) -> None:
        self.after(
            0, self._set_status, f"Loading references [{current}/{total}]: {name}…"
        )

    def _show_ref_warning(self, skipped_names: list[str]) -> None:
        names_str = "\n".join(f"  • {n}" for n in skipped_names)
        messagebox.showwarning(
            "Reference photos rejected",
            f"The following reference photos were rejected:\n\n{names_str}\n\n"
            "Reference photographs containing zero or multiple faces are rejected. "
            "Each reference photo must contain exactly one clearly visible face.\n\n"
            "These students will be skipped during sorting.",
        )

    def _on_cancel(self) -> None:
        self._cancel_flag.set()
        self._cancel_btn.config(state=tk.DISABLED)
        self._set_status("Cancelling… (finishing current image)")

    def _on_progress(self, current: int, total: int, filename: str) -> None:
        self.after(0, self._apply_progress, current, total, filename)

    def _apply_progress(self, current: int, total: int, filename: str) -> None:
        pct = (current / total * 100) if total else 0
        self._progress_var.set(pct)
        self._set_status(f"[{current}/{total}] {filename}")

    def _on_done(self, summary: dict) -> None:
        elapsed = int(time.monotonic() - self._sort_start_time) if self._sort_start_time else None
        self._stop_ticker(final_elapsed=elapsed)
        self._start_btn.config(state=tk.NORMAL)
        self._cancel_btn.config(state=tk.DISABLED)
        self._progress_var.set(100)

        cancelled = self._cancel_flag.is_set()
        status = "Sorting cancelled." if cancelled else "Sorting complete! ✅"
        self._set_status(status)

        metrics = summary.get("accuracy_metrics", {})
        lines = [
            status,
            "",
            "═══ Results ═══",
            f"  Total images found   : {summary['total']}",
            f"  Matched (strong)     : {summary['matched']}",
            f"  Review required      : {summary['review']}",
            f"  Unmatched            : {summary['unmatched']}",
            f"  Skipped (errors)     : {summary['skipped']}",
        ]

        if metrics and metrics.get("total_matches", 0) > 0:
            lines += [
                "",
                "═══ Match Quality ═══",
                f"  Avg margin           : {metrics.get('avg_margin', 0):.1%}",
                f"  Median margin        : {metrics.get('median_margin', 0):.1%}",
                f"  Total face matches   : {metrics.get('total_matches', 0)}",
            ]

        if summary.get("review", 0) > 0:
            lines += [
                "",
                "═══ ℹ️ Review Required ═══",
                f"  {summary['review']} photo(s) copied to _review_required/ — ",
                "  these are borderline matches needing manual review.",
            ]

        enhancements = []
        if self._preprocessing_var.get():
            enhancements.append("CLAHE preprocessing")
        if self._ensemble_var.get():
            enhancements.append("Ensemble detection")
        if self._cache_var.get():
            enhancements.append("Encoding cache")
        if enhancements:
            lines += [
                "",
                "═══ Enhancements Active ═══",
            ]
            for e in enhancements:
                lines.append(f"  ✓ {e}")

        lines += [
            "",
            "═══ Ethical Design ═══",
            "  ✓ 100% offline — no data leaves the device",
            "  ✓ CPU-only — works on old laptops",
            "  ✓ Privacy-first — children's photos never uploaded",
            "  ✓ Biometric cache stored in local app data",
        ]

        self._write_summary("\n".join(lines))

        # Update cache status (may have been created during this run)
        self._update_cache_status()

        if summary["total"] == 0:
            messagebox.showwarning(
                "No images found",
                "No photos were found in the Events folder.\n\n"
                "Make sure your Events folder contains photos (or sub-folders with photos).\n"
                "Supported formats: .jpg  .jpeg  .png  .bmp  .webp",
            )

    def _on_error(self, message: str) -> None:
        self._stop_ticker()
        self._start_btn.config(state=tk.NORMAL)
        self._cancel_btn.config(state=tk.DISABLED)
        self._set_status("An error occurred.")
        messagebox.showerror("Unexpected error", message)

    def _set_status(self, text: str) -> None:
        self._status_label.config(text=text)

    def _write_summary(self, text: str) -> None:
        self._summary_text.config(state=tk.NORMAL)
        self._summary_text.delete("1.0", tk.END)
        self._summary_text.insert(tk.END, text)
        self._summary_text.config(state=tk.DISABLED)

    def _clear_summary(self) -> None:
        self._write_summary("")


def main() -> None:
    app = KinderSortLiteApp()
    app.mainloop()


if __name__ == "__main__":
    main()
