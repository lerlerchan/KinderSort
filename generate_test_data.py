"""
generate_test_data.py — Creates a test dataset for KinderSort Lite evaluation.

Generates synthetic face images using face_recognition's built-in capabilities
or creates a structured test folder with known ground truth for accuracy testing.
"""

import json
import random
import shutil
from pathlib import Path


def create_test_structure(base_dir: Path, num_students: int = 5, photos_per_student: int = 10) -> dict:
    """Create a structured test directory with ground truth labels.

    This creates:
        base_dir/
            reference/       ← One clear reference photo per student
                Student_A.jpg
                Student_B.jpg
                ...
            test_events/
                Event_1/     ← Mixed photos with known labels
                    photo_001.jpg  → Student_A
                    photo_002.jpg  → Student_B
                    ...

    Args:
        base_dir: Where to create the test structure.
        num_students: Number of unique students.
        photos_per_student: Number of test photos per student.

    Returns:
        Dict with paths and ground_truth mapping.
    """
    base_dir.mkdir(parents=True, exist_ok=True)
    ref_dir = base_dir / "reference"
    test_dir = base_dir / "test_events" / "Event_1"
    ref_dir.mkdir(parents=True, exist_ok=True)
    test_dir.mkdir(parents=True, exist_ok=True)

    student_names = [f"Student_{chr(65 + i)}" for i in range(num_students)]
    ground_truth = {}

    print(f"Creating test dataset with {num_students} students...")
    print(f"  Reference folder: {ref_dir}")
    print(f"  Test folder:      {test_dir}")

    # Create simple placeholder reference images (solid colour blocks with labels)
    for i, name in enumerate(student_names):
        _create_placeholder_image(ref_dir / f"{name}.jpg", name, is_reference=True)

    # Create test images
    for i in range(num_students * photos_per_student):
        student_idx = i % num_students
        name = student_names[student_idx]
        filename = f"photo_{i + 1:03d}.jpg"
        _create_placeholder_image(test_dir / filename, name, is_reference=False)
        ground_truth[filename] = name

    # Save ground truth
    gt_path = base_dir / "ground_truth.json"
    with open(gt_path, "w") as f:
        json.dump(ground_truth, f, indent=2)

    print(f"Created {num_students * photos_per_student} test images")
    print(f"Ground truth saved to: {gt_path}")

    return {
        "reference_folder": str(ref_dir),
        "test_folder": str(base_dir / "test_events"),
        "ground_truth": ground_truth,
        "ground_truth_path": str(gt_path),
    }


def _create_placeholder_image(path: Path, label: str, is_reference: bool = False) -> None:
    """Create a simple placeholder image using PIL.

    In a real scenario, you'd use actual face photos. This creates colour-coded
    placeholder images for testing the pipeline structure.
    """
    from PIL import Image, ImageDraw, ImageFont

    # Use different colours per student for visual distinction
    colours = {
        "A": (255, 100, 100),
        "B": (100, 255, 100),
        "C": (100, 100, 255),
        "D": (255, 255, 100),
        "E": (255, 100, 255),
    }

    student_letter = label.split("_")[-1] if "_" in label else "A"
    bg_colour = colours.get(student_letter, (200, 200, 200))

    size = (200, 200) if is_reference else (300, 300)
    img = Image.new("RGB", size, bg_colour)
    draw = ImageDraw.Draw(img)

    # Draw a simple face-like circle
    circle_bbox = (50, 30, 150, 130)
    draw.ellipse(circle_bbox, fill=(255, 220, 180), outline=(0, 0, 0))

    # Draw eyes
    draw.ellipse((75, 60, 95, 80), fill=(0, 0, 0))
    draw.ellipse((105, 60, 125, 80), fill=(0, 0, 0))

    # Draw mouth
    draw.arc((80, 90, 120, 115), 0, 180, fill=(0, 0, 0), width=2)

    # Label
    draw.text((10, 150), label, fill=(0, 0, 0))

    img.save(path, "JPEG", quality=85)


def create_evaluation_dataset(output_dir: Path) -> dict:
    """Create a full evaluation dataset with ground truth.

    This generates a dataset suitable for running evaluator.py.
    """
    return create_test_structure(output_dir, num_students=5, photos_per_student=10)


if __name__ == "__main__":
    import sys

    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("./test_data")
    result = create_evaluation_dataset(output)
    print(f"\nTest dataset ready: {output}")
    print(f"Run evaluation with:")
    print(f"  python evaluator.py {result['reference_folder']} {result['test_folder']} --ground-truth {result['ground_truth_path']}")
