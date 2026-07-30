"""setup_test_data.py — Setup test data from LFW dataset"""

import csv
import random
import shutil
from pathlib import Path
from PIL import Image, ImageEnhance

LFW_FOLDER = r"C:\Users\zhenh\Downloads\archive\lfw-deepfunneled\lfw-deepfunneled"
NUM_STUDENTS = 5
PHOTOS_PER_STUDENT = 3

HERE = Path(__file__).parent.resolve()
REF_FOLDER = HERE / "referencePhoto"
EVENTS_FOLDER = HERE / "Events" / "Sports_Day"
BENCHMARK_DIR = HERE / "benchmark_data"
GROUND_TRUTH_CSV = BENCHMARK_DIR / "ground_truth.csv"

def darken_image(src: Path, dest: Path, brightness: float = 0.25) -> None:
    with Image.open(src) as img:
        img = img.convert("RGB")
        darkened = ImageEnhance.Brightness(img).enhance(brightness)
        darkened.save(str(dest))

def main():
    lfw_path = Path(LFW_FOLDER)
    if not lfw_path.exists():
        print(f"LFW folder not found: {lfw_path}")
        return

    for folder in [REF_FOLDER, EVENTS_FOLDER, BENCHMARK_DIR]:
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)

    # Get people with enough photos
    people = [d for d in lfw_path.iterdir() if d.is_dir() and len(list(d.glob("*.jpg"))) >= PHOTOS_PER_STUDENT + 1]
    random.seed(42)
    students = random.sample(people, min(NUM_STUDENTS, len(people)))

    ground_truth = []

    for person_folder in students:
        photos = sorted(person_folder.glob("*.jpg"))
        student_name = person_folder.name.replace("_", " ")

        # Reference photo
        ref_dest = REF_FOLDER / f"{student_name}.jpg"
        shutil.copy2(photos[0], ref_dest)
        print(f"  Reference: {ref_dest.name}")

        # Event photos
        for photo in photos[1:PHOTOS_PER_STUDENT + 1]:
            dest_name = f"{student_name}_{photo.name}"
            dest = EVENTS_FOLDER / dest_name
            shutil.copy2(photo, dest)
            ground_truth.append({"filename": dest_name, "expected_students": student_name})
            print(f"    Event: {dest_name}")

        # Dark photo
        dark_src = photos[PHOTOS_PER_STUDENT + 1] if len(photos) > PHOTOS_PER_STUDENT + 1 else photos[1]
        dark_name = f"DARK_{student_name}_{dark_src.name}"
        darken_image(dark_src, EVENTS_FOLDER / dark_name)
        ground_truth.append({"filename": dark_name, "expected_students": student_name})
        print(f"    Dark: {dark_name}")

    # Unmatched photos
    non_students = [d for d in people if d not in students]
    random.shuffle(non_students)
    for person_folder in non_students[:2]:
        photos = list(person_folder.glob("*.jpg"))
        if photos:
            dest_name = f"UNMATCHED_{person_folder.name}_{photos[0].name}"
            shutil.copy2(photos[0], EVENTS_FOLDER / dest_name)
            ground_truth.append({"filename": dest_name, "expected_students": ""})
            print(f"  Unmatched: {dest_name}")

    with GROUND_TRUTH_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "expected_students"])
        writer.writeheader()
        writer.writerows(ground_truth)

    print(f"\n✅ Done! {len(ground_truth)} test photos created.")

if __name__ == "__main__":
    main()