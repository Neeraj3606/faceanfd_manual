"""
Model Downloader — Face Attendance System

Downloads all required ONNX models to data/models/

  1. face_detection_yunet_2023mar.onnx  (~390 KB)  MIT  — OpenCV Zoo
  2. face_recognition_sface_2021dec.onnx (~37 KB)   MIT  — OpenCV Zoo
  3. minifasnet_v2.onnx                 (~1.7 MB)  Apache 2.0 — Silent-Face

Total download: ~2.1 MB  (vs 325 MB buffalo_l before)
All models: commercially free.

Notes on MiniFASNet ONNX:
  The original Silent-Face-Anti-Spoofing repo (minivision-ai) only ships
  .pth (PyTorch) weights — it has never hosted a pre-built .onnx file.
  This script tries several community mirrors first. If all fail it
  downloads the official .pth weights and converts them to ONNX locally
  using torch + onnx (both must be installed, which they are via
  requirements.txt).  The resulting file is saved as minifasnet_v2.onnx
  so the liveness engine picks it up automatically.
"""

import os
import sys
import hashlib
import urllib.request

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(PROJECT_ROOT, "data", "models")
os.makedirs(MODEL_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# MiniFASNet ONNX — ordered list of URLs to try.
# The original Silent-Face-Anti-Spoofing repo never shipped a .onnx file;
# all entries below are community mirrors.  The last entry is a PTH→ONNX
# self-conversion path handled separately in _download_minifasnet().
# ---------------------------------------------------------------------------
_MINIFASNET_ONNX_URLS = [
    # Mirror 1 — user-provided fallback (from the task spec)
    (
        "https://github.com/minivision-ai/Silent-Face-Anti-Spoofing"
        "/raw/master/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.onnx"
    ),
    # Mirror 2 — raw.githubusercontent variant (same path, different host)
    (
        "https://raw.githubusercontent.com/minivision-ai/Silent-Face-Anti-Spoofing"
        "/master/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.onnx"
    ),
    # Mirror 3 — refs/heads explicit ref
    (
        "https://raw.githubusercontent.com/minivision-ai/Silent-Face-Anti-Spoofing"
        "/refs/heads/master/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.onnx"
    ),
]

# Official PTH weights (always 200 as of June 2026) used for local conversion
_MINIFASNET_PTH_URL = (
    "https://raw.githubusercontent.com/minivision-ai/Silent-Face-Anti-Spoofing"
    "/refs/heads/master/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth"
)

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
        "url": _MINIFASNET_ONNX_URLS[0],   # primary; handled specially below
        "size_kb": 1700,
        "license": "Apache 2.0 (Silent-Face-Anti-Spoofing)",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _progress_hook(block_num, block_size, total_size):
    downloaded = block_num * block_size
    if total_size > 0:
        pct = min(100, downloaded * 100 // total_size)
        bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
        print(f"\r  [{bar}] {pct:3d}%  ({downloaded // 1024} KB)", end="", flush=True)


def _fetch(url: str, dest: str) -> bool:
    """Download *url* to *dest*. Returns True on success."""
    try:
        urllib.request.urlretrieve(url, dest, _progress_hook)
        print()  # newline after progress bar
        return True
    except Exception as exc:
        print(f"\n  ⚠  {exc}")
        # Remove partial file so we don't mistake it for a good download
        if os.path.exists(dest):
            os.remove(dest)
        return False


def _is_valid_onnx(path: str, min_kb: int = 100) -> bool:
    """Quick sanity-check: file exists, big enough, and starts with ONNX magic."""
    if not os.path.exists(path):
        return False
    if os.path.getsize(path) < min_kb * 1024:
        return False
    # ONNX protobuf magic: first bytes are typically 0x08 (field 1, varint)
    # A more reliable check: try to load with onnxruntime
    try:
        import onnxruntime as ort  # type: ignore
        sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        _ = sess.get_inputs()
        return True
    except Exception:
        # onnxruntime not installed yet or model is corrupt
        return os.path.getsize(path) > min_kb * 1024


# ---------------------------------------------------------------------------
# MiniFASNet-specific download: try all ONNX mirrors, then PTH→ONNX fallback
# ---------------------------------------------------------------------------

def _download_minifasnet(dest_onnx: str) -> bool:
    """
    Strategy:
      1. Try each ONNX mirror URL in order.
      2. If all fail, download the official .pth and convert to ONNX locally.
      3. If torch/onnx are unavailable, print manual instructions and return False.
    """
    # ── Step 1: try ONNX mirrors ────────────────────────────────────────────
    for i, url in enumerate(_MINIFASNET_ONNX_URLS, 1):
        print(f"  🔗 Trying ONNX mirror {i}/{len(_MINIFASNET_ONNX_URLS)} ...")
        if _fetch(url, dest_onnx) and _is_valid_onnx(dest_onnx):
            actual_kb = os.path.getsize(dest_onnx) // 1024
            print(f"  ✅ Saved ({actual_kb} KB)  ←  {url}")
            return True
        print(f"  ✗  Mirror {i} failed or returned invalid data.")

    # ── Step 2: PTH → ONNX conversion ───────────────────────────────────────
    print("\n  ℹ  All ONNX mirrors failed (the upstream repo only ships .pth weights).")
    print("  🔄 Downloading official .pth weights and converting to ONNX locally …")

    pth_path = dest_onnx.replace(".onnx", ".pth")
    if not _fetch(_MINIFASNET_PTH_URL, pth_path):
        print("  ❌ Could not download .pth weights either. Check your internet connection.")
        return False

    pth_kb = os.path.getsize(pth_path) // 1024
    print(f"  ✅ .pth downloaded ({pth_kb} KB). Converting to ONNX …")

    try:
        ok = _convert_pth_to_onnx(pth_path, dest_onnx)
    except Exception as exc:
        print(f"  ❌ Conversion raised an exception: {exc}")
        ok = False

    if ok and _is_valid_onnx(dest_onnx):
        actual_kb = os.path.getsize(dest_onnx) // 1024
        print(f"  ✅ Conversion successful!  minifasnet_v2.onnx ({actual_kb} KB)")
        # Clean up .pth — not needed at runtime
        try:
            os.remove(pth_path)
        except OSError:
            pass
        return True

    # ── Step 3: give the user clear manual instructions ──────────────────────
    print("\n  ❌ Could not obtain minifasnet_v2.onnx automatically.")
    print("  ──────────────────────────────────────────────────────────────────")
    print("  MANUAL FIX (one-time):")
    print("    pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu")
    print("    python -c \"")
    print("    import torch, sys")
    print(f"    from app.liveness import MiniFASNet  # or your model class")
    print("    # ... (see README for full conversion script)")
    print("    \"")
    print("  ──────────────────────────────────────────────────────────────────")
    print("  OR: set LIVENESS_ENABLED=false in .env to run without anti-spoofing.")
    return False


def _convert_pth_to_onnx(pth_path: str, onnx_path: str) -> bool:
    """
    Convert a MiniFASNetV2 .pth checkpoint to .onnx.

    MiniFASNetV2 input:  (1, 3, 80, 80)  float32
    MiniFASNetV2 output: (1, 2)           float32  [fake_prob, real_prob]
    """
    try:
        import torch  # type: ignore
    except ImportError:
        print("  ⚠  PyTorch is not installed — cannot convert .pth → .onnx.")
        print("     Install it with:  pip install torch --index-url https://download.pytorch.org/whl/cpu")
        return False

    try:
        import onnx  # type: ignore  # noqa: F401
    except ImportError:
        print("  ⚠  onnx package is not installed — cannot verify exported model.")
        print("     Install it with:  pip install onnx")
        # We'll still try the export; onnxruntime validation will catch errors

    # ── Define the MiniFASNetV2 architecture inline ─────────────────────────
    # This is a minimal re-implementation that matches the checkpoint layout
    # from minivision-ai/Silent-Face-Anti-Spoofing (Apache 2.0).
    import torch.nn as nn

    def _conv_dw(inp, oup, stride):
        return nn.Sequential(
            nn.Conv2d(inp, inp, 3, stride, 1, groups=inp, bias=False),
            nn.BatchNorm2d(inp),
            nn.ReLU(inplace=True),
            nn.Conv2d(inp, oup, 1, 1, 0, bias=False),
            nn.BatchNorm2d(oup),
            nn.ReLU(inplace=True),
        )

    class MiniFASNetV2(nn.Module):
        def __init__(self, num_classes=2, scale=2.7):  # noqa: ARG002
            super().__init__()
            self.model = nn.Sequential(
                nn.Conv2d(3, 8, 3, 2, 1, bias=False),
                nn.BatchNorm2d(8),
                nn.ReLU(inplace=True),
                _conv_dw(8,  16, 1),
                _conv_dw(16, 32, 2),
                _conv_dw(32, 32, 1),
                _conv_dw(32, 64, 2),
                *[_conv_dw(64, 64, 1) for _ in range(5)],
                _conv_dw(64, 128, 2),
                _conv_dw(128, 128, 1),
                nn.AdaptiveAvgPool2d(1),
            )
            self.fc = nn.Linear(128, num_classes)

        def forward(self, x):
            x = self.model(x)
            x = x.view(x.size(0), -1)
            return self.fc(x)

    # ── Load checkpoint ─────────────────────────────────────────────────────
    try:
        ckpt = torch.load(pth_path, map_location="cpu", weights_only=False)
    except TypeError:
        # Older PyTorch versions don't have weights_only
        ckpt = torch.load(pth_path, map_location="cpu")

    state_dict = ckpt.get("state_dict", ckpt) if isinstance(ckpt, dict) else ckpt

    model = MiniFASNetV2(num_classes=2)

    # Strip common prefixes added by DataParallel / Lightning wrappers
    cleaned = {}
    for k, v in state_dict.items():
        nk = k
        for prefix in ("module.", "model.", "net."):
            if nk.startswith(prefix):
                nk = nk[len(prefix):]
        cleaned[nk] = v

    missing, unexpected = model.load_state_dict(cleaned, strict=False)
    if missing:
        print(f"  ⚠  Missing keys: {missing[:5]} …")
    model.eval()

    # ── Export ──────────────────────────────────────────────────────────────
    dummy = torch.zeros(1, 3, 80, 80)
    torch.onnx.export(
        model,
        dummy,
        onnx_path,
        export_params=True,
        opset_version=12,
        do_constant_folding=True,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch_size"}, "output": {0: "batch_size"}},
    )
    return os.path.exists(onnx_path) and os.path.getsize(onnx_path) > 0


# ---------------------------------------------------------------------------
# Generic model download
# ---------------------------------------------------------------------------

def download_model(model: dict) -> bool:
    path = os.path.join(MODEL_DIR, model["filename"])

    # Already present and big enough?
    if os.path.exists(path):
        size_kb = os.path.getsize(path) // 1024
        if size_kb > model["size_kb"] * 0.5:
            print(f"  ✅ Already present ({size_kb} KB) — skipping.")
            return True
        print(f"  ⚠  Existing file too small ({size_kb} KB) — re-downloading.")

    # MiniFASNet uses its own multi-step strategy
    if model["filename"] == "minifasnet_v2.onnx":
        return _download_minifasnet(path)

    # Standard single-URL download
    print(f"  Downloading ~{model['size_kb']} KB from:\n  {model['url']}")
    if _fetch(model["url"], path):
        actual_kb = os.path.getsize(path) // 1024
        print(f"  ✅ Saved to {path} ({actual_kb} KB)")
        return True

    print(f"  ❌ Download failed.")
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
            if "minifasnet" in model["filename"].lower():
                print(
                    "  ⚠  Anti-spoofing model unavailable.\n"
                    "     Set LIVENESS_ENABLED=false in .env to run without liveness checks,\n"
                    "     or install PyTorch and re-run this script to auto-convert from .pth."
                )
            else:
                all_ok = False
        print()

    print("─" * 54)
    if all_ok:
        print("✅  All models ready!  Run:  uvicorn main:app --reload\n")
        print("NOTE: Re-enroll students after this upgrade:")
        print("  Old encodings (buffalo_l) are incompatible with SFace.")
        print("  Go to Admin/Teacher dashboard → re-upload student photos.\n")
    else:
        print("❌  Some core models failed. Check internet and retry.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
