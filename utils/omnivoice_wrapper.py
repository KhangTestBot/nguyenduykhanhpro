"""
Wrapper module for k2-fsa/OmniVoice Zero-Shot Voice Cloning & TTS Engine.
Supports hardware acceleration on Google Colab (CUDA T4), Apple Silicon (MPS), and CPU fallback.
Includes automatic reference audio extraction, trimming (3-12s optimal window), and WAV/MP3 export.
"""

import os
import sys
import time
import shutil
import threading
import subprocess
from pathlib import Path

_model_instance = None
_model_lock = threading.Lock()

def is_omnivoice_available() -> bool:
    """Checks if omnivoice and its core dependencies are installed."""
    try:
        import torch
        import soundfile
        import omnivoice
        return True
    except ImportError:
        return False

def get_device_info() -> dict:
    """Detects available hardware acceleration (CUDA, MPS, or CPU)."""
    try:
        import torch
        if torch.cuda.is_available():
            return {
                "device": "cuda:0",
                "dtype": "float16",
                "name": torch.cuda.get_device_name(0),
                "is_gpu": True,
                "badge": f"🚀 GPU: {torch.cuda.get_device_name(0)}"
            }
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return {
                "device": "mps",
                "dtype": "float32",
                "name": "Apple Silicon (MPS)",
                "is_gpu": True,
                "badge": "⚡ Apple Silicon GPU (MPS)"
            }
        else:
            return {
                "device": "cpu",
                "dtype": "float32",
                "name": "CPU",
                "is_gpu": False,
                "badge": "💻 CPU Mode (Khuyên dùng Colab GPU T4 để tối ưu)"
            }
    except Exception:
        return {
            "device": "cpu",
            "dtype": "float32",
            "name": "CPU (Fallback)",
            "is_gpu": False,
            "badge": "💻 CPU Mode"
        }

def prepare_clean_reference_wav(
    input_media_path: str,
    start_sec: float = 0.0,
    duration_sec: float = 8.0
) -> tuple[bool, str]:
    """
    Extracts and normalizes a clean 24kHz mono WAV reference clip (3-12s) from any audio or video file
    so OmniVoice gets an optimal reference signal without running out of memory on long files.
    """
    from utils.hardware_accelerator import get_ffmpeg_bin
    ffmpeg = get_ffmpeg_bin()

    out_dir = Path("output_voiceovers") / "temp_ref"
    out_dir.mkdir(parents=True, exist_ok=True)
    clean_wav = out_dir / f"ref_prepared_{int(time.time())}.wav"

    cmd = [
        ffmpeg, "-y",
        "-ss", str(max(0.0, start_sec)),
        "-t", str(max(2.0, min(15.0, duration_sec))),
        "-i", str(input_media_path),
        "-vn",
        "-ac", "1",
        "-ar", "24000",
        "-af", "highpass=f=70,lowpass=f=11000,dynaudnorm",
        str(clean_wav)
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode == 0 and clean_wav.exists() and clean_wav.stat().st_size > 1000:
            return True, str(clean_wav)
        return False, str(input_media_path)
    except Exception:
        return False, str(input_media_path)

def get_omnivoice_model():
    """Loads the pre-trained OmniVoice model (singleton to avoid reloading)."""
    global _model_instance
    with _model_lock:
        if _model_instance is None:
            import torch
            from omnivoice import OmniVoice

            dev_info = get_device_info()
            dtype = torch.float16 if dev_info["dtype"] == "float16" else torch.float32
            
            _model_instance = OmniVoice.from_pretrained(
                "k2-fsa/OmniVoice",
                device_map=dev_info["device"],
                dtype=dtype,
                load_asr=True
            )
        return _model_instance

def generate_cloned_voice(
    text: str,
    ref_audio_path: str,
    output_path: str = None,
    ref_text: str = None,
    ref_start_sec: float = 0.0,
    ref_duration_sec: float = 8.0,
    progress_callback = None
) -> tuple[bool, str]:
    """
    Generates speech cloned from ref_audio using OmniVoice.
    """
    if not is_omnivoice_available():
        return (
            False,
            "Thư viện `omnivoice` chưa được cài đặt. Vui lòng chạy lệnh: "
            "`pip install omnivoice torch torchaudio soundfile` (Đặc biệt khuyên dùng trên Google Colab có GPU T4)."
        )

    if not os.path.exists(ref_audio_path):
        return False, f"Không tìm thấy file âm thanh mẫu: {ref_audio_path}"

    if not text.strip():
        return False, "Nội dung văn bản cần đọc không được để trống."

    try:
        import torch
        import soundfile as sf
        import numpy as np

        if progress_callback:
            progress_callback(10, "Đang chuẩn hóa đoạn âm thanh giọng mẫu (24kHz Clean Reference)...")

        _, prepared_ref = prepare_clean_reference_wav(
            ref_audio_path,
            start_sec=ref_start_sec,
            duration_sec=ref_duration_sec
        )

        if progress_callback:
            progress_callback(25, "Đang nạp mô hình OmniVoice & ASR (k2-fsa/OmniVoice)...")

        model = get_omnivoice_model()

        if progress_callback:
            progress_callback(55, "Đang phân tích âm sắc giọng mẫu và tạo giọng đọc (Zero-Shot Synthesis)...")

        gen_kwargs = {
            "text": text.strip(),
            "ref_audio": str(prepared_ref)
        }
        if ref_text and ref_text.strip():
            gen_kwargs["ref_text"] = ref_text.strip()

        audio_output = model.generate(**gen_kwargs)

        if progress_callback:
            progress_callback(85, "Đang định dạng và lưu file âm thanh chất lượng cao...")

        if not output_path:
            out_dir = Path("output_voiceovers") / "omnivoice"
            out_dir.mkdir(parents=True, exist_ok=True)
            timestamp = int(time.time())
            output_path = str(out_dir / f"cloned_{timestamp}.wav")
        else:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        if isinstance(audio_output, (list, tuple)):
            audio_data = audio_output[0]
        else:
            audio_data = audio_output

        if hasattr(audio_data, "cpu"):
            audio_data = audio_data.cpu().numpy()

        if hasattr(audio_data, "squeeze"):
            audio_data = audio_data.squeeze()

        sample_rate = 24000
        sf.write(output_path, audio_data, sample_rate)

        if progress_callback:
            progress_callback(100, "Đã tạo giọng nhân bản thành công!")

        return True, output_path

    except Exception as e:
        import traceback
        err_detail = traceback.format_exc()
        print(f"[OmniVoice Error] {err_detail}")
        return False, f"Lỗi khi nhân bản giọng với OmniVoice: {str(e)}"
