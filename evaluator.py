"""
evaluator.py — Accuracy evaluation framework for KinderSort Lite.

Provides baseline vs. enhanced comparison, performance benchmarks,
and detailed accuracy metrics for the project report.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import face_recognition
import numpy as np

from enhanced_sorter import EnhancedPhotoSorter
from preprocessor import ImagePreprocessor, load_and_preprocess
from sorter import PhotoSorter as OriginalPhotoSorter
from utils import collect_event_images, is_image_file


@dataclass
class EvaluationResult:
    """Structured evaluation results for a single sorter run."""

    name: str
    total_images: int
    faces_detected: int
    faces_missed: int
    correct_matches: int
    incorrect_matches: int
    avg_confidence: float
    median_confidence: float
    processing_time_seconds: float
    images_per_second: float
    detection_breakdown: dict = field(default_factory=dict)


class Evaluator:
    """Runs baseline and enhanced evaluation on a test dataset."""

    def __init__(
        self,
        reference_folder: Path,
        test_events_folder: Path,
        ground_truth: dict[str, str],
    ) -> None:
        """Initialise the evaluator.

        Args:
            reference_folder: Path to reference student photos.
            test_events_folder: Path to test event images.
            ground_truth: Dict mapping image filename → expected student name.
        """
        self.reference_folder = reference_folder
        self.test_events_folder = test_events_folder
        self.ground_truth = ground_truth

    def evaluate_baseline(self) -> EvaluationResult:
        """Run evaluation using the original (unenhanced) PhotoSorter."""
        import logging

        logger = logging.getLogger("eval_baseline")
        logger.setLevel(logging.WARNING)

        sorter = OriginalPhotoSorter(
            self.reference_folder,
            self.test_events_folder,
            Path("."),
            logger,
        )

        start = time.time()
        sorter.load_references()
        load_time = time.time() - start

        images = collect_event_images(self.test_events_folder)
        total = len(images)

        correct = 0
        incorrect = 0
        no_face = 0
        confidences = []

        for image_path, _ in images:
            filename = image_path.name
            expected = self.ground_truth.get(filename)
            if expected is None:
                continue

            try:
                rgb = sorter._load_and_resize(image_path)
                locations = face_recognition.face_locations(rgb, model="hog")
                if not locations:
                    locations = face_recognition.face_locations(rgb, model="cnn")
                encodings = face_recognition.face_encodings(
                    rgb, locations, num_jitters=3, model="large"
                )

                if not encodings:
                    no_face += 1
                    continue

                for enc in encodings:
                    match = sorter._match_face(enc)
                    if match == expected:
                        correct += 1
                        # Estimate confidence
                        if sorter._student_encodings:
                            names = list(sorter._student_encodings.keys())
                            known = np.array(list(sorter._student_encodings.values()))
                            distances = face_recognition.face_distance(known, enc)
                            best_dist = float(np.min(distances))
                            conf = 1.0 - (best_dist / sorter.DISTANCE_THRESHOLD)
                            confidences.append(max(0, min(1, conf)))
                    elif match and match != expected:
                        incorrect += 1
                    else:
                        no_face += 1

            except Exception:
                no_face += 1

        elapsed = time.time() - start + load_time

        return EvaluationResult(
            name="Baseline (Original)",
            total_images=total,
            faces_detected=correct + incorrect,
            faces_missed=no_face,
            correct_matches=correct,
            incorrect_matches=incorrect,
            avg_confidence=float(np.mean(confidences)) if confidences else 0.0,
            median_confidence=float(np.median(confidences)) if confidences else 0.0,
            processing_time_seconds=round(elapsed, 2),
            images_per_second=round(total / max(elapsed, 0.01), 2),
        )

    def evaluate_enhanced(self) -> EvaluationResult:
        """Run evaluation using the enhanced EnhancedPhotoSorter."""
        import logging

        logger = logging.getLogger("eval_enhanced")
        logger.setLevel(logging.WARNING)

        sorter = EnhancedPhotoSorter(
            self.reference_folder,
            self.test_events_folder,
            Path("."),
            logger,
            use_preprocessing=True,
            use_cache=False,
            ensemble_detection=True,
        )

        start = time.time()
        sorter.load_references()
        load_time = time.time() - start

        images = collect_event_images(self.test_events_folder)
        total = len(images)

        correct = 0
        incorrect = 0
        no_face = 0
        confidences = []

        for image_path, _ in images:
            filename = image_path.name
            expected = self.ground_truth.get(filename)
            if expected is None:
                continue

            try:
                rgb = load_and_preprocess(image_path, sorter._preprocessor)
                locations = sorter._detect_faces_ensemble(rgb)
                encodings = face_recognition.face_encodings(
                    rgb, locations, num_jitters=5, model="large"
                )

                if not encodings:
                    no_face += 1
                    continue

                for enc in encodings:
                    match, conf = sorter._match_face_with_confidence(enc)
                    if match == expected:
                        correct += 1
                        confidences.append(conf)
                    elif match and match != expected:
                        incorrect += 1
                    else:
                        no_face += 1

            except Exception:
                no_face += 1

        elapsed = time.time() - start + load_time

        return EvaluationResult(
            name="Enhanced (KinderSort Lite)",
            total_images=total,
            faces_detected=correct + incorrect,
            faces_missed=no_face,
            correct_matches=correct,
            incorrect_matches=incorrect,
            avg_confidence=float(np.mean(confidences)) if confidences else 0.0,
            median_confidence=float(np.median(confidences)) if confidences else 0.0,
            processing_time_seconds=round(elapsed, 2),
            images_per_second=round(total / max(elapsed, 0.01), 2),
            detection_breakdown=sorter._detection_methods_used,
        )

    def run_comparison(self) -> dict:
        """Run both baseline and enhanced evaluation and return comparison."""
        print("=" * 60)
        print("  KINDERSORT LITE — ACCURACY EVALUATION")
        print("=" * 60)
        print()

        print("[1/2] Running BASELINE evaluation (original KinderSort)...")
        baseline = self.evaluate_baseline()
        self._print_result(baseline)

        print()
        print("[2/2] Running ENHANCED evaluation (KinderSort Lite)...")
        enhanced = self.evaluate_enhanced()
        self._print_result(enhanced)

        print()
        print("=" * 60)
        print("  IMPROVEMENT SUMMARY")
        print("=" * 60)
        print()

        accuracy_gain = enhanced.correct_matches - baseline.correct_matches
        accuracy_pct = (
            (enhanced.correct_matches / max(baseline.correct_matches, 1) - 1) * 100
        )
        recall_gain = enhanced.faces_detected - baseline.faces_detected

        print(f"  Correct matches:   {baseline.correct_matches:>4} → {enhanced.correct_matches:>4}  (+{accuracy_gain})")
        print(f"  Faces detected:    {baseline.faces_detected:>4} → {enhanced.faces_detected:>4}  (+{recall_gain})")
        print(f"  Avg confidence:    {baseline.avg_confidence:.2%} → {enhanced.avg_confidence:.2%}")
        print(f"  Speed:             {baseline.images_per_second:.1f} → {enhanced.images_per_second:.1f} img/s")

        return {
            "baseline": baseline,
            "enhanced": enhanced,
            "improvement": {
                "accuracy_gain": accuracy_gain,
                "accuracy_pct": round(accuracy_pct, 1),
                "recall_gain": recall_gain,
                "confidence_gain": round(enhanced.avg_confidence - baseline.avg_confidence, 4),
            },
        }

    @staticmethod
    def _print_result(r: EvaluationResult) -> None:
        """Print a formatted evaluation result."""
        print(f"\n  --- {r.name} ---")
        print(f"  Images:            {r.total_images}")
        print(f"  Faces detected:    {r.faces_detected}")
        print(f"  Faces missed:      {r.faces_missed}")
        print(f"  Correct matches:   {r.correct_matches}")
        print(f"  Incorrect matches: {r.incorrect_matches}")
        print(f"  Avg confidence:    {r.avg_confidence:.2%}")
        print(f"  Median confidence: {r.median_confidence:.2%}")
        print(f"  Processing time:   {r.processing_time_seconds:.1f}s")
        print(f"  Throughput:        {r.images_per_second:.1f} img/s")
        if r.detection_breakdown:
            print(f"  Detection methods: {r.detection_breakdown}")


def main() -> None:
    """Run evaluation from command line."""
    import sys

    if len(sys.argv) < 3:
        print("Usage: python evaluator.py <reference_folder> <test_events_folder>")
        print("Optional: --ground-truth <json_file>  (filename→student_name mapping)")
        sys.exit(1)

    ref = Path(sys.argv[1])
    test = Path(sys.argv[2])

    # Load ground truth if provided
    gt = {}
    for i, arg in enumerate(sys.argv):
        if arg == "--ground-truth" and i + 1 < len(sys.argv):
            with open(sys.argv[i + 1]) as f:
                gt = json.load(f)

    evaluator = Evaluator(ref, test, gt)
    evaluator.run_comparison()


if __name__ == "__main__":
    main()
