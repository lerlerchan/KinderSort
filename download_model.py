"""download_model.py — Download OpenCV DNN face detection model files."""

import urllib.request
from pathlib import Path

MODELS_DIR = Path(__file__).parent / "models"

FILES = {
    "deploy.prototxt": (
        "https://raw.githubusercontent.com/opencv/opencv/master/"
        "samples/dnn/face_detector/deploy.prototxt"
    ),
    "res10_300x300_ssd_iter_140000.caffemodel": (
        "https://raw.githubusercontent.com/opencv/opencv_3rdparty/"
        "dnn_samples_face_detector_20170830/"
        "res10_300x300_ssd_iter_140000.caffemodel"
    ),
}

def download(filename: str, url: str) -> None:
    dest = MODELS_DIR / filename
    if dest.exists():
        print(f"  Already exists: {filename}")
        return
    print(f"  Downloading {filename}...")
    urllib.request.urlretrieve(url, dest)
    size_kb = dest.stat().st_size // 1024
    print(f"  Saved: {filename} ({size_kb} KB)")

def main() -> None:
    MODELS_DIR.mkdir(exist_ok=True)
    print(f"Downloading OpenCV DNN model files to {MODELS_DIR}/\n")
    for filename, url in FILES.items():
        download(filename, url)
    print("\nDone! OpenCV DNN face detection is ready.")

if __name__ == "__main__":
    main()