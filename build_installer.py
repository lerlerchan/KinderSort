import os
import sys
import subprocess
import urllib.request
from pathlib import Path

# Define the project root directory
BASE_DIR = Path(__file__).parent.resolve()
VC_REDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
VC_REDIST_FILE = BASE_DIR / "vc_redist.x64.exe"
SPEC_FILE = BASE_DIR / "KinderSort.spec"

def download_vc_redist():
    """Download Microsoft Visual C++ Redistributable installer if not present."""
    if not VC_REDIST_FILE.exists():
        print("[INFO] Downloading Microsoft VC++ Redistributable (vc_redist.x64.exe)...")
        try:
            urllib.request.urlretrieve(VC_REDIST_URL, VC_REDIST_FILE)
            print("[SUCCESS] Downloaded vc_redist.x64.exe successfully.")
        except Exception as exc:
            print(f"[ERROR] Failed to download VC++ redistributable: {exc}")
            sys.exit(1)
    else:
        print("[INFO] vc_redist.x64.exe already exists. Skipping download.")

def run_pyinstaller_spec():
    """Execute PyInstaller directly using the provided KinderSort.spec file."""
    print("[INFO] Starting PyInstaller build process using KinderSort.spec...")
    
    if not SPEC_FILE.exists():
        print(f"[ERROR] Specified spec file not found at: {SPEC_FILE}")
        sys.exit(1)

    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--clean",
        str(SPEC_FILE)
    ]
    
    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode != 0:
        print("[ERROR] PyInstaller build failed using KinderSort.spec!")
        sys.exit(1)
    print("\n[SUCCESS] PyInstaller build completed successfully!")
    print(f"👉 Standalone executable created at: {BASE_DIR / 'dist' / 'KinderSort.exe'}")

def run_inno_setup():
    """Optional: Compile installer_script.iss using Inno Setup if installed."""
    print("\n[INFO] Checking for Inno Setup compiler...")
    inno_paths = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    
    iscc_path = None
    for path in inno_paths:
        if os.path.exists(path):
            iscc_path = path
            break

    if not iscc_path:
        print("[INFO] Inno Setup (ISCC.exe) not found in default system paths.")
        print("[HINT] You can directly upload 'dist/KinderSort.exe' to GitHub Releases!")
        return

    iss_file = BASE_DIR / "installer_script.iss"
    if iss_file.exists():
        print("[INFO] Compiling Windows Installer setup package...")
        cmd = [iscc_path, str(iss_file)]
        result = subprocess.run(cmd, cwd=BASE_DIR)
        if result.returncode == 0:
            print("🎉 Inno Setup compilation finished successfully!")
            print(f"👉 Setup Installer created at: {BASE_DIR / 'release' / 'KinderSortLiteSetup' / 'KinderSortLiteSetup.exe'}")
        else:
            print("[WARNING] Inno Setup compilation failed.")
    else:
        print("[INFO] installer_script.iss not found, skipping Inno Setup step.")

if __name__ == "__main__":
    download_vc_redist()
    run_pyinstaller_spec()
    run_inno_setup()