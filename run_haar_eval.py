"""
run_haar_eval.py — Standalone ablation evaluation for KinderSort Lite.

Runs the SAME EnhancedPhotoSorter pipeline twice, with preprocessing +
ensemble detection OFF (baseline-like) vs ON (KinderSort Lite), forcing
the OpenCV Haar-cascade backend so it works without dlib installed.

This is an honest ablation of the CLAHE preprocessing + ensemble detection
contribution, run against the project's own synthetic ground-truth test
set (test_data/). It is NOT a reproduction of the dlib HOG/CNN baseline
described in the report's Section 4 -- that requires dlib, which could
not be compiled in this environment. Note this distinction in the report.
"""

import json
import logging
import statistics
import time
from pathlib import Path

from enhanced_sorter import EnhancedPhotoSorter

BASE = Path(__file__).parent
REF = BASE / "test_data" / "reference"
EVENTS = BASE / "test_data" / "test_events"
GT_FILE = BASE / "test_data" / "ground_truth.json"

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger("haar_eval")


def force_haar(sorter: EnhancedPhotoSorter) -> None:
    """Disable the DNN net so FaceEngine falls back to Haar cascade."""
    sorter._engine._net = None


def run_config(name: str, use_preprocessing: bool, ensemble: bool, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    EnhancedPhotoSorter.clear_cache()

    sorter = EnhancedPhotoSorter(
        REF, EVENTS, output_dir, logger,
        use_preprocessing=use_preprocessing,
        use_cache=False,
        ensemble_detection=ensemble,
    )
    force_haar(sorter)

    t0 = time.time()
    sorter.load_references()
    force_haar(sorter)  # engine may reinit lazily; force again before sorting
    counts = sorter.sort_all(lambda a, b, c: None, lambda: False)
    elapsed = time.time() - t0

    # Score against ground truth by inspecting output folders
    gt = json.loads(GT_FILE.read_text())
    correct = 0
    total_labeled = len(gt)
    for fname, expected_student in gt.items():
        expected_folder = output_dir / expected_student
        if expected_folder.exists() and any(
            f.name.split("__")[-1] == fname or f.name.endswith(fname)
            for f in expected_folder.glob("*")
        ):
            correct += 1

    margin_scores = sorter._match_margin_scores
    return {
        "name": name,
        "total_images": counts["total"],
        "matched": counts["matched"],
        "review": counts["review"],
        "unmatched": counts["unmatched"],
        "correct_vs_ground_truth": correct,
        "total_ground_truth": total_labeled,
        "accuracy_pct": round(100 * correct / total_labeled, 1) if total_labeled else 0.0,
        "avg_margin": round(statistics.mean(margin_scores), 4) if margin_scores else 0.0,
        "detection_breakdown": dict(sorter._detection_methods_used),
        "elapsed_seconds": round(elapsed, 2),
    }


if __name__ == "__main__":
    print("Running BASELINE-LIKE (preprocessing OFF, ensemble OFF, Haar backend)...")
    baseline = run_config("baseline_like_haar", use_preprocessing=False, ensemble=False,
                           output_dir=BASE / "test_data" / "output_haar_baseline")
    print(json.dumps(baseline, indent=2))

    print("\nRunning ENHANCED (preprocessing ON, ensemble ON, Haar backend)...")
    enhanced = run_config("enhanced_haar", use_preprocessing=True, ensemble=True,
                           output_dir=BASE / "test_data" / "output_haar_enhanced")
    print(json.dumps(enhanced, indent=2))

    result = {"baseline_like": baseline, "enhanced": enhanced}
    out_path = BASE / "evidence" / "evaluation" / "haar_ablation_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nSaved to {out_path}")
