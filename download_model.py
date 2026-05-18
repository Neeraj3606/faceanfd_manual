"""
Model Downloader — Face Attendance System

Downloads all required ONNX models to data/models/:

  1. face_detection_yunet_2023mar.onnx  (~390 KB)  MIT  — OpenCV Zoo
  2. face_recognition_sface_2021dec.onnx (~37 KB)   MIT  — OpenCV Zoo
  3. minifasnet_v2.onnx                 (~1.7 MB)  Apache 2.0 — Silent-Face

Total download: ~2.1 MB  (vs 325 MB buffalo_l before)
All models: commercially free.
"""

import os
import sys
import hashlib
import urllib.request

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(PROJECT_ROOT, "data", "models")
os.makedirs(MODEL_DIR, exist_ok=True)

MODELS = [
    {
        "name": "YuNet Face Detector",
        "filename": "face_detection_yunet_2023mar.onnx",
        "url": (
            "https://github.com/opencv/opencv_zoo/raw/main/models/"
            "face_detection_yunet/face_detection_yunet_2023mar.onnx"
        ),
        "size_kb": 390,
        "license": "MIT (OpenCV Zoo)",
    },
    {
        "name": "SFace Face Recognizer",
        "filename": "face_recognition_sface_2021dec.onnx",
        "url": (
            "https://github.com/opencv/opencv_zoo/raw/main/models/"
            "face_recognition_sface/face_recognition_sface_2021dec.onnx"
        ),
        "size_kb": 37,
        "license": "MIT (OpenCV Zoo)",
    },
    {
        "name": "MiniFASNet v2 Anti-Spoofing",
        "filename": "minifasnet_v2.onnx",
        "url": (
            "https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/"
            "raw/master/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.onnx"
        ),
        "size_kb": 1700,
        "license": "Apache 2.0 (Silent-Face-Anti-Spoofing)",
    },
]


def _progress_hook(block_num, block_size, total_size):
    downloaded = block_num * block_size
    if total_size > 0:
        pct = min(100, downloaded * 100 // total_size)
        bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
        print(f"\r  [{bar}] {pct:3d}%  ({downloaded // 1024} KB)", end="", flush=True)


def download_model(model: dict) -> bool:
    path = os.path.join(MODEL_DIR, model["filename"])

    if os.path.exists(path):
        size_kb = os.path.getsize(path) // 1024
        if size_kb > model["size_kb"] * 0.5:
            print(f"  ✅ Already present ({size_kb} KB) — skipping.")
            return True
        print(f"  ⚠️  Existing file too small ({size_kb} KB) — re-downloading.")

    print(f"  Downloading ~{model['size_kb']} KB ...")
    try:
        urllib.request.urlretrieve(model["url"], path, _progress_hook)
        print()  # newline after progress bar
        actual_kb = os.path.getsize(path) // 1024
        print(f"  ✅ Saved to {path} ({actual_kb} KB)")
        return True
    except Exception as exc:
        print(f"\n  ❌ Download failed: {exc}")
        # Try alternate URL for MiniFASNet
        if model["filename"] == "minifasnet_v2.onnx":
            alt = (
                "https://raw.githubusercontent.com/minivision-ai/"
                "Silent-Face-Anti-Spoofing/master/resources/"
                "anti_spoof_models/2.7_80x80_MiniFASNetV2.onnx"
            )
            print(f"  🔄 Trying alternate URL ...")
            try:
                urllib.request.urlretrieve(alt, path, _progress_hook)
                print()
                print(f"  ✅ Saved (alternate URL)")
                return True
            except Exception as exc2:
                print(f"\n  ❌ Alternate also failed: {exc2}")
        return False


def main():
    print("\n╔══════════════════════════════════════════════════════╗")
    print("║   Face Attendance — ONNX Model Downloader            ║")
    print("║   YuNet + SFace + MiniFASNet  (All MIT / Apache 2.0) ║")
    print("╚══════════════════════════════════════════════════════╝\n")

    all_ok = True
    for model in MODELS:
        print(f"📦 {model['name']}  [{model['license']}]")
        ok = download_model(model)
        if not ok:
            all_ok = False
        print()

    print("─" * 54)
    if all_ok:
        print("✅  All models ready!  Run:  uvicorn main:app --reload\n")
        print("NOTE: Re-enroll students after this upgrade:")
        print("  Old encodings (buffalo_l) are incompatible with SFace.")
        print("  Go to Admin/Teacher dashboard → re-upload student photos.\n")
    else:
        print("❌  Some models failed. Check internet and retry.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
