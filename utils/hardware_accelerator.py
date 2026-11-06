"""
Centralized Hardware Acceleration & System Optimization Utility for NgDuyKhanh Pro.
Automatically detects NVIDIA NVENC (Google Colab / Linux / Windows), Apple VideoToolbox (macOS),
ONNX Runtime Execution Providers (CUDA / CoreML / CPU), and manages disk cache.
"""

import os
import sys
import shutil
import platform
import subprocess
from pathlib import Path
from functools import lru_cache

@lru_cache(maxsize=1)
def get_ffmpeg_bin() -> str:
    """Locates the optimal ffmpeg binary on macOS, Linux, or Windows."""
    for candidate in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"]:
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return shutil.which("ffmpeg") or "ffmpeg"

@lru_cache(maxsize=1)
def detect_best_video_encoder() -> dict:
    """
    Tests and detects the fastest working H.264 hardware encoder on the current machine.
    Returns dict with keys: 'encoder', 'label', 'is_hw', 'platform'.
    """
    ffmpeg = get_ffmpeg_bin()
    sys_plat = platform.system().lower()

    def _test_encoder(enc_name: str, extra_args: list[str] = None) -> bool:
        try:
            cmd = [
                ffmpeg, "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black:s=320x240:d=0.1",
                "-pix_fmt", "yuv420p",
                "-c:v", enc_name,
            ]
            if extra_args:
                cmd.extend(extra_args)
            cmd.extend(["-f", "null", "-"])
            res = subprocess.run(cmd, capture_output=True, timeout=5)
            return res.returncode == 0
        except Exception:
            return False

    # 1. Check NVIDIA NVENC (Google Colab T4 / Linux / Windows GPU)
    if _test_encoder("h264_nvenc"):
        return {
            "encoder": "h264_nvenc",
            "label": "🚀 NVIDIA NVENC (GPU Hardware)",
            "is_hw": True,
            "platform": sys_plat
        }

    # 2. Check Apple VideoToolbox (macOS Intel & Apple Silicon)
    if sys_plat == "darwin" and _test_encoder("h264_videotoolbox", ["-allow_sw", "1"]):
        return {
            "encoder": "h264_videotoolbox",
            "label": "⚡ Apple VideoToolbox (Mac GPU)",
            "is_hw": True,
            "platform": sys_plat
        }

    # 3. Fallback to multi-threaded libx264 CPU
    return {
        "encoder": "libx264",
        "label": f"💻 CPU Multi-Thread ({os.cpu_count() or 4} Threads)",
        "is_hw": False,
        "platform": sys_plat
    }

def get_optimal_h264_encoder_args(
    use_gpu: bool = True,
    bitrate: str = "5000k",
    crf: str = "23",
    preset: str = "veryfast",
    fps: int = 30
) -> list[str]:
    """
    Returns the optimal FFmpeg video encoding arguments for the current platform.
    Automatically switches between h264_nvenc (Colab), h264_videotoolbox (Mac), and libx264 (CPU).
    """
    if use_gpu:
        hw_info = detect_best_video_encoder()
        enc = hw_info["encoder"]
        if enc == "h264_nvenc":
            return [
                "-c:v", "h264_nvenc",
                "-preset", "p4",
                "-b:v", str(bitrate),
                "-maxrate", str(bitrate),
                "-bufsize", "10000k",
                "-pix_fmt", "yuv420p",
                "-r", str(fps)
            ]
        elif enc == "h264_videotoolbox":
            return [
                "-c:v", "h264_videotoolbox",
                "-allow_sw", "1",
                "-b:v", str(bitrate),
                "-prio_speed", "1",
                "-pix_fmt", "yuv420p",
                "-r", str(fps)
            ]

    return [
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", str(preset),
        "-pix_fmt", "yuv420p",
        "-r", str(fps)
    ]

@lru_cache(maxsize=1)
def get_optimal_onnx_providers() -> tuple[list[str], str]:
    """
    Returns prioritized ONNX Runtime Execution Providers (CUDA -> CoreML -> CPU)
    and a human-readable badge string.
    """
    try:
        import onnxruntime as ort
        avail = ort.get_available_providers()
        providers = []
        label = "CPU Parallel"

        if "CUDAExecutionProvider" in avail:
            providers.append("CUDAExecutionProvider")
            label = "🚀 NVIDIA CUDA GPU"
        if "CoreMLExecutionProvider" in avail:
            providers.append("CoreMLExecutionProvider")
            if label == "CPU Parallel":
                label = "⚡ Apple CoreML Accelerator"
        providers.append("CPUExecutionProvider")
        return providers, label
    except Exception:
        return ["CPUExecutionProvider"], "💻 CPU Parallel"

def is_colab_environment() -> bool:
    """Checks if the app is currently running inside Google Colab or Cloud container."""
    return any(
        k in os.environ
        for k in ["COLAB_GPU", "COLAB_RELEASE_TAG", "COLAB_BACKEND_VERSION"]
    ) or os.path.exists("/content")

def get_storage_stats(base_dir: Path = Path(".")) -> dict:
    """
    Calculates disk usage of output and cache folders so the user can monitor & clean up space.
    """
    target_folders = [
        "output_clips",
        "output_voiceovers",
        "output_videos",
        "output_vocal_separation",
        "output_v2v_videos",
        "google_flow_output",
    ]
    folder_sizes = {}
    total_cache_bytes = 0

    for fname in target_folders:
        fpath = base_dir / fname
        if fpath.exists() and fpath.is_dir():
            size_b = sum(
                f.stat().st_size for f in fpath.rglob("*") if f.is_file()
            )
            folder_sizes[fname] = size_b
            total_cache_bytes += size_b
        else:
            folder_sizes[fname] = 0

    try:
        disk_usage = shutil.disk_usage(str(base_dir.resolve()))
        free_gb = disk_usage.free / (1024 ** 3)
        total_gb = disk_usage.total / (1024 ** 3)
    except Exception:
        free_gb, total_gb = 0.0, 0.0

    return {
        "folders": folder_sizes,
        "total_cache_bytes": total_cache_bytes,
        "total_cache_gb": total_cache_bytes / (1024 ** 3),
        "total_cache_mb": total_cache_bytes / (1024 ** 2),
        "free_disk_gb": free_gb,
        "total_disk_gb": total_gb,
    }

def cleanup_output_caches(base_dir: Path = Path("."), folders_to_clean: list[str] = None) -> tuple[int, float]:
    """
    Safely deletes old generated files in output folders to free up disk space.
    Returns (deleted_files_count, freed_megabytes).
    """
    if folders_to_clean is None:
        folders_to_clean = [
            "output_clips",
            "output_voiceovers",
            "output_videos",
            "output_vocal_separation",
            "output_v2v_videos",
        ]

    deleted_count = 0
    freed_bytes = 0

    for fname in folders_to_clean:
        fpath = base_dir / fname
        if fpath.exists() and fpath.is_dir():
            for item in list(fpath.rglob("*")):
                if item.is_file():
                    try:
                        sz = item.stat().st_size
                        item.unlink(missing_ok=True)
                        deleted_count += 1
                        freed_bytes += sz
                    except Exception:
                        pass

    return deleted_count, freed_bytes / (1024 ** 2)
