Installer release

This repository does not include the large installer binary in the git history to keep the repository small. The official Windows installer (KinderSortLiteSetup.exe) is published as a GitHub Release asset.

Download location

- GitHub Release (recommended): https://github.com/Hueiqi/KinderSort/releases

Expected release tag name used by CI / build process: v1.0.0 (for example). If the release is created with a different tag, check the Releases page for the artifact.

How this was produced (short guide)

1. Build the app exe locally with PyInstaller (or use the CI):
   - pyinstaller --noconfirm --onefile --name KinderSortLite main.py
   - the built exe will be in dist\KinderSortLite.exe
2. Optionally package into an installer with Inno Setup using KinderSortLite.iss
   - ISCC.exe KinderSortLite.iss -> produces KinderSortLiteSetup.exe
3. Create a tag and a GitHub Release, then attach the installer (recommended using gh CLI):
   - git tag -a v1.0.0 -m "KinderSortLite v1.0.0"
   - git push origin v1.0.0
   - gh release create v1.0.0 dist\KinderSortLiteSetup.exe --title "KinderSortLite v1.0.0" --notes "Windows installer (CPU-only, offline)"

If you need the installer committed under /release/KinderSortLiteSetup.exe instead of a Release asset, tell me and I can add it (note: committing large binaries is not recommended).

Contact / Maintainers

If the release link above is empty, the installer has not yet been published — please build and create a Release following the steps above or ask me to build and publish it for you.
