"""
Common UI components, CSS design tokens, helper functions, and shared video engine routines.
"""

import streamlit as st
import os
import time
import math
import shutil
import json
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# ─── Verification & Import Video Libraries ─────────────────────────────────
try:
    MOVIEPY_AVAILABLE = True
except ImportError as e:
    MOVIEPY_AVAILABLE = False
    IMPORT_ERROR = str(e)

# ─── Constants & Paths ──────────────────────────────────────────────────
OUTPUT_BASE = Path("output_clips")
OUTPUT_BASE.mkdir(exist_ok=True)

SUPPORTED_FORMATS = ["mp4", "mkv", "mov", "avi", "webm", "flv", "m4v"]
MAX_CLIP_DURATION = 300  # seconds (5 minutes)

# Check yt-dlp
try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False

# ─── CSS Design System (Lightweight & Clean Minimalist Edition) ───────────────────
CUSTOM_CSS = """
<style>
  :root {
    --bg-base: #0b0d12;
    --bg-surface: #13161f;
    --bg-input: #0e1017;
    --border-subtle: #202430;
    --border-hover: #0284c7;
    --text-primary: #f3f4f6;
    --text-secondary: #9ca3af;
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-pill: 9999px;
  }

  /* ── Base App ── */
  html, body, [class*="css"], .stApp {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    background-color: var(--bg-base) !important;
    color: var(--text-primary) !important;
    -webkit-font-smoothing: antialiased;
  }

  h1, h2, h3, h4, h5, h6, .hero-title, .card-title, .sidebar-section-title {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    color: var(--text-primary);
  }

  /* Header & Footer clean up */
  header, footer, [data-testid="stHeader"], [data-testid="stSidebarHeader"] {
    visibility: hidden !important;
    height: 0 !important;
    display: none !important;
  }

  /* ── Sidebar (Shifted Up & Perfectly Balanced) ── */
  section[data-testid="stSidebar"] {
    background: #0d1017 !important;
    border-right: 1px solid var(--border-subtle) !important;
  }
  
  section[data-testid="stSidebar"] > div:first-child,
  div[data-testid="stSidebarUserContent"],
  div[data-testid="stSidebarContent"] {
    padding-top: 0.6rem !important;
    padding-bottom: 1.5rem !important;
    padding-left: 0.75rem !important;
    padding-right: 0.75rem !important;
  }
  
  div[data-testid="stSidebarUserContent"] iframe {
    width: 100% !important;
  }

  .sidebar-section {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 1rem !important;
    margin-bottom: 1rem !important;
  }
  
  .sidebar-section-title {
    font-size: 0.82rem !important;
    font-weight: 700 !important;
    color: #38bdf8 !important;
    padding-bottom: 0.5rem !important;
    margin-bottom: 0.75rem !important;
    border-bottom: 1px solid var(--border-subtle);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  /* ── Hero Banner (Clean & Compact) ── */
  .hero-banner {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 1.35rem 1.5rem;
    margin-bottom: 1.25rem;
    text-align: left;
  }

  .hero-title {
    font-size: 1.65rem;
    font-weight: 800;
    line-height: 1.2;
    margin: 0;
    color: #ffffff;
    letter-spacing: -0.02em;
  }
  .hero-subtitle {
    color: var(--text-secondary);
    font-size: 0.92rem;
    margin-top: 0.35rem;
    line-height: 1.4;
  }

  /* ── Badges ── */
  .badge-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-top: 0.75rem;
  }
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.25rem 0.65rem;
    border-radius: var(--radius-sm);
    font-size: 0.76rem;
    font-weight: 600;
    background: rgba(34, 211, 238, 0.08);
    border: 1px solid rgba(34, 211, 238, 0.2);
    color: #7dd3fc;
  }

  /* ── Cards ── */
  .card {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 1.25rem;
    margin-bottom: 1.25rem;
  }

  .card-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: #ffffff;
    margin-bottom: 1rem;
    padding-bottom: 0.65rem;
    border-bottom: 1px solid var(--border-subtle);
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  /* ── Buttons ── */
  .stButton > button {
    background: #1c202b !important;
    color: #f3f4f6 !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-sm) !important;
    font-size: 0.88rem !important;
    font-weight: 600 !important;
    padding: 0.55rem 1.15rem !important;
    transition: background 0.15s ease, border-color 0.15s ease !important;
  }
  .stButton > button:hover {
    background: #252b3b !important;
    border-color: #4b5563 !important;
  }

  /* Primary Button */
  .stButton > button[kind="primary"], .stButton > button[data-testid="baseButton-primary"] {
    background: #0284c7 !important;
    color: #ffffff !important;
    border: 1px solid #0369a1 !important;
    font-weight: 600 !important;
  }
  .stButton > button[kind="primary"]:hover, .stButton > button[data-testid="baseButton-primary"]:hover {
    background: #0369a1 !important;
    border-color: #38bdf8 !important;
  }

  /* ── Inputs & Selectboxes ── */
  .stTextInput input, .stSelectbox select, .stNumberInput input, .stTextArea textarea {
    background: var(--bg-input) !important;
    border: 1px solid var(--border-subtle) !important;
    color: #f3f4f6 !important;
    border-radius: var(--radius-sm) !important;
    font-size: 0.88rem !important;
    padding: 0.55rem 0.8rem !important;
  }
  .stTextInput input:focus, .stSelectbox select:focus, .stTextArea textarea:focus {
    border-color: #0284c7 !important;
    outline: none !important;
    box-shadow: 0 0 0 2px rgba(2, 132, 199, 0.25) !important;
  }

  /* ── Dropzone (Upload) ── */
  [data-testid="stFileUploaderDropzone"] {
    background: var(--bg-input) !important;
    border: 1px dashed var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
    padding: 1.5rem 1rem !important;
  }

  /* ── Progress Bar ── */
  [data-testid="stProgress"] > div > div {
    background: #0284c7 !important;
    border-radius: var(--radius-pill) !important;
  }
  [data-testid="stProgress"] > div {
    background: #1e2330 !important;
    border-radius: var(--radius-pill) !important;
    height: 5px !important;
  }

  /* ── Metric Cards ── */
  [data-testid="metric-container"] {
    background: var(--bg-surface) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-sm) !important;
    padding: 0.85rem 1rem !important;
  }
  [data-testid="metric-container"] label { 
    color: var(--text-secondary) !important; 
    font-size: 0.78rem !important; 
    font-weight: 600 !important;
  }
  [data-testid="metric-container"] [data-testid="stMetricValue"] { 
    color: #ffffff !important; 
    font-weight: 700 !important; 
    font-size: 1.45rem !important; 
  }

  /* ── Status Alerts & Boxes ── */
  .stAlert, div[data-baseweb="notification"] {
    background: #141822 !important;
    border-radius: var(--radius-sm) !important;
    border: 1px solid var(--border-subtle) !important;
  }

  /* ── Scrollbars ── */
  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: #2a3040; border-radius: 4px; }

  /* ── Custom Alert Components ── */
  .success-box {
    background: rgba(16, 185, 129, 0.08);
    border: 1px solid rgba(16, 185, 129, 0.25);
    border-radius: var(--radius-sm);
    padding: 0.85rem 1.15rem;
    color: #6ee7b7;
    margin: 0.8rem 0;
    font-size: 0.88rem;
  }
  .info-box {
    background: rgba(2, 132, 199, 0.08);
    border: 1px solid rgba(2, 132, 199, 0.25);
    border-radius: var(--radius-sm);
    padding: 0.85rem 1.15rem;
    color: #7dd3fc;
    margin: 0.8rem 0;
    font-size: 0.88rem;
  }
  .warning-box {
    background: rgba(245, 158, 11, 0.08);
    border: 1px solid rgba(245, 158, 11, 0.25);
    border-radius: var(--radius-sm);
    padding: 0.85rem 1.15rem;
    color: #fcd34d;
    margin: 0.8rem 0;
    font-size: 0.88rem;
  }
  .error-box {
    background: rgba(239, 68, 68, 0.08);
    border: 1px solid rgba(239, 68, 68, 0.25);
    border-radius: var(--radius-sm);
    padding: 0.85rem 1.15rem;
    color: #fca5a5;
    margin: 0.8rem 0;
    font-size: 0.88rem;
  }
  .file-tag {
    display: inline-flex;
    align-items: center;
    background: #1a1e28;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-xs);
    padding: 0.2rem 0.55rem;
    font-size: 0.78rem;
    color: var(--text-secondary);
    font-family: ui-monospace, monospace;
  }
  .clip-item {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    padding: 0.65rem 0.85rem;
    margin: 0.35rem 0;
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }
  .clip-number {
    width: 24px;
    height: 24px;
    border-radius: 4px;
    background: #1e2433;
    color: #38bdf8;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 0.75rem;
    flex-shrink: 0;
  }
</style>
"""

def load_custom_css():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ─── Process Management ─────────────────────────────────────────────────
PROCESSES_LOCK = threading.Lock()
ACTIVE_PROCESSES = []

def cleanup_old_processes():
    """Dọn dẹp các tiến trình cũ đã chạy xong hoặc đang treo"""
    global ACTIVE_PROCESSES
    with PROCESSES_LOCK:
        active = []
        for p in ACTIVE_PROCESSES:
            if p.poll() is None:
                active.append(p)
            else:
                try:
                    p.terminate()
                except Exception:
                    pass
        ACTIVE_PROCESSES = active

def format_duration(seconds: float) -> str:
    """Chuyển giây sang định dạng mm:ss"""
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def human_size(num_bytes: int) -> str:
    """Chuyển bytes sang MB/GB dễ đọc"""
    for unit in ["B", "KB", "MB", "GB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.2f} TB"

def get_video_info(path: str) -> dict:
    """Lấy thông tin cơ bản của video bằng FFprobe"""
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,duration:format=duration",
            "-of",
            "json",
            path
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        info = json.loads(result.stdout)

        stream = info.get("streams", [{}])[0]
        fmt = info.get("format", {})

        fps_str = stream.get("r_frame_rate", "30/1")
        if "/" in fps_str:
            num, den = fps_str.split("/")
            fps = float(num) / float(den) if float(den) > 0 else 30.0
        else:
            fps = float(fps_str)

        duration_str = stream.get("duration") or fmt.get("duration")
        duration = float(duration_str) if duration_str else 0.0

        width = int(stream.get("width", 0))
        height = int(stream.get("height", 0))

        n_clips = math.ceil(duration / 60) if duration > 0 else 1

        return {
            "duration": duration,
            "fps": fps,
            "size": [width, height],
            "n_clips": n_clips,
        }
    except Exception as e:
        return {"error": str(e)}

def safe_filename(name: str) -> str:
    """Làm sạch tên file, bỏ ký tự đặc biệt"""
    import re
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    return name.strip()

def render_download_progress_card(
    status_text: str = "Đang tải dữ liệu...",
    pct_val: float = 0.0,
    downloaded_str: str = "",
    total_str: str = "",
    speed_str: str = "",
    eta_str: str = "",
    phase: str = "downloading"
) -> str:
    """Render thẻ HTML tiến độ tải & tốc độ tải thời gian thực cực đẹp và sắc nét."""
    try:
        pct_clamped = max(0.0, min(100.0, float(pct_val if pct_val is not None else 0.0)))
    except Exception:
        pct_clamped = 0.0

    if phase == "completed":
        dot_color = "#10b981"
        glow_color = "rgba(16, 185, 129, 0.5)"
        bar_gradient = "linear-gradient(90deg, #10b981 0%, #34d399 100%)"
        speed_badge_color = "#34d399"
        speed_badge_bg = "rgba(16, 185, 129, 0.15)"
        speed_badge_border = "rgba(16, 185, 129, 0.35)"
    elif phase == "merging":
        dot_color = "#a855f7"
        glow_color = "rgba(168, 85, 247, 0.5)"
        bar_gradient = "linear-gradient(90deg, #8b5cf6 0%, #c084fc 100%)"
        speed_badge_color = "#c084fc"
        speed_badge_bg = "rgba(168, 85, 247, 0.15)"
        speed_badge_border = "rgba(168, 85, 247, 0.35)"
    elif phase == "connecting":
        dot_color = "#f59e0b"
        glow_color = "rgba(245, 158, 11, 0.5)"
        bar_gradient = "linear-gradient(90deg, #f59e0b 0%, #fbbf24 100%)"
        speed_badge_color = "#fbbf24"
        speed_badge_bg = "rgba(245, 158, 11, 0.15)"
        speed_badge_border = "rgba(245, 158, 11, 0.35)"
    else:
        dot_color = "#38bdf8"
        glow_color = "rgba(56, 189, 248, 0.5)"
        bar_gradient = "linear-gradient(90deg, #0284c7 0%, #38bdf8 100%)"
        speed_badge_color = "#38bdf8"
        speed_badge_bg = "rgba(14, 165, 233, 0.15)"
        speed_badge_border = "rgba(56, 189, 248, 0.35)"

    speed_display = speed_str if speed_str else "--"
    if speed_display and not speed_display.startswith("⚡") and phase == "downloading":
        speed_display = f"⚡ {speed_display}"

    size_display = ""
    if downloaded_str and total_str and total_str != downloaded_str:
        size_display = f"{downloaded_str} / {total_str}"
    elif downloaded_str:
        size_display = downloaded_str

    eta_display = f"⏱️ Còn lại: ~{eta_str}" if (eta_str and eta_str != "--" and eta_str != "Unknown") else ""

    html = (
        f'<div style="background: #11141e; border: 1px solid #1e293b; border-radius: 12px; padding: 15px 18px; margin: 10px 0 15px 0; box-shadow: 0 6px 22px rgba(0, 0, 0, 0.4); font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif;">'
        f'<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">'
        f'<div style="font-weight: 600; font-size: 0.92rem; color: #f8fafc; display: flex; align-items: center; gap: 8px;">'
        f'<span style="display: inline-block; width: 9px; height: 9px; background: {dot_color}; border-radius: 50%; box-shadow: 0 0 10px {glow_color};"></span>'
        f'<span>{status_text}</span>'
        f'</div>'
        f'<div style="background: {speed_badge_bg}; color: {speed_badge_color}; border: 1px solid {speed_badge_border}; padding: 4px 12px; border-radius: 6px; font-weight: 700; font-size: 0.86rem; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;">'
        f'{speed_display}'
        f'</div>'
        f'</div>'
        f'<div style="background: #1a202c; border-radius: 9999px; height: 8px; overflow: hidden; width: 100%; margin-bottom: 10px; border: 1px solid #2d3748;">'
        f'<div style="background: {bar_gradient}; height: 100%; width: {pct_clamped:.1f}%; transition: width 0.2s ease-out; border-radius: 9999px;"></div>'
        f'</div>'
        f'<div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.82rem; color: #94a3b8;">'
        f'<div><b style="color: #ffffff; font-size: 0.88rem;">{pct_clamped:.1f}%</b>'
        f'{f"""<span style="color: #475569; margin: 0 6px;">•</span><span style="color: #cbd5e1;">{size_display}</span>""" if size_display else ""}'
        f'</div>'
        f'<div>{eta_display}</div>'
        f'</div>'
        f'</div>'
    )
    return html

class YtdlpLogger:
    def __init__(self):
        self.logs = []

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        self.logs.append(str(msg))

    def error(self, msg):
        self.logs.append(str(msg))

def download_video_from_url(
        url: str,
        output_dir: Path,
        progress_placeholder=None,
        audio_only: bool = False) -> dict:
    
    def ui_updater(status_text="Đang kết nối...", pct_val=0.0, downloaded_str="", total_str="", speed_str="", eta_str="", phase="downloading"):
        try:
            if progress_placeholder:
                html = render_download_progress_card(
                    status_text=status_text,
                    pct_val=pct_val,
                    downloaded_str=downloaded_str,
                    total_str=total_str,
                    speed_str=speed_str,
                    eta_str=eta_str,
                    phase=phase
                )
                progress_placeholder.markdown(html, unsafe_allow_html=True)
        except Exception:
            pass

    ui_updater(
        status_text="⏳ Đang kết nối máy chủ và phân tích video 1080p...",
        pct_val=0.0,
        speed_str="Đang kết nối...",
        phase="connecting"
    )

    # Lọc URL sạch từ chuỗi dán vào (tránh dán kèm chữ tiếng Trung/Mô tả/Tiêu đề/Tracking query)
    import re
    url_match = re.search(r'''https?://[^\s<>"'()\[\]{}|]+''', url)
    clean_url = url_match.group(0) if url_match else url.strip()

    # Loại bỏ query tracking rác của Bilibili/TikTok/Douyin để tránh bị CDN redirect/bóp socket
    if "bilibili.com/video/" in clean_url:
        p_match = re.search(r'[?&](p=\d+)', clean_url)
        clean_url = clean_url.split("?")[0]
        if p_match:
            clean_url = f"{clean_url}?{p_match.group(1)}"
    elif "b23.tv" in clean_url:
        clean_url = clean_url.split("?")[0]
    elif "tiktok.com" in clean_url or "douyin.com" in clean_url:
        clean_url = clean_url.split("?")[0]

    def clean_output_dir():
        """Xóa sạch các file nháp cũ để tránh dồn dung lượng giữa các lần thử chiến lược."""
        for p in list(output_dir.glob("*")):
            try:
                if p.is_file():
                    p.unlink(missing_ok=True)
            except Exception:
                pass

    clean_output_dir()
    output_template = str(output_dir / "%(title)s.%(ext)s")

    try:
        import yt_dlp

        download_status = {"last_update": time.time(), "active": True}

        def progress_hook(d):
            if not download_status["active"]:
                return
            try:
                if d['status'] == 'downloading':
                    now = time.time()
                    if now - download_status["last_update"] >= 0.2:
                        down_bytes = d.get('downloaded_bytes', 0)
                        total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                        
                        pct_val = 0.0
                        pct_str = d.get('_percent_str', '').strip()
                        if pct_str:
                            try:
                                pct_val = float(pct_str.replace('%', '').strip())
                            except Exception:
                                pct_val = 0.0
                        elif total_bytes > 0:
                            pct_val = (down_bytes / total_bytes) * 100.0
                        
                        speed_str = d.get('_speed_str', '').strip()
                        if not speed_str and d.get('speed'):
                            speed_str = f"{human_size(d['speed'])}/s"
                        elif not speed_str:
                            speed_str = "Đang tải..."
                            
                        eta_str = d.get('_eta_str', '').strip()
                        if not eta_str and d.get('eta'):
                            eta_str = f"{int(d['eta'])}s"
                        
                        down_mb = human_size(down_bytes)
                        total_mb = human_size(total_bytes) if total_bytes > 0 else ""
                        
                        # Nhận diện luồng tải đang chạy
                        info_dict = d.get('info_dict', {})
                        vcodec = info_dict.get('vcodec')
                        acodec = info_dict.get('acodec')
                        if vcodec and vcodec != 'none':
                            status_title = "🎬 Đang tải hình ảnh Video (1080p)..."
                        elif acodec and acodec != 'none':
                            status_title = "🎵 Đang tải âm thanh gốc..."
                        else:
                            status_title = "⚡ Đang tải dữ liệu video..."
                        
                        ui_updater(
                            status_text=status_title,
                            pct_val=pct_val,
                            downloaded_str=down_mb,
                            total_str=total_mb,
                            speed_str=speed_str,
                            eta_str=eta_str,
                            phase="downloading"
                        )
                        download_status["last_update"] = now
                elif d['status'] == 'finished':
                    ui_updater(
                        status_text="🔄 Đang ghép nối âm thanh & tối ưu định dạng MP4 1080p...",
                        pct_val=100.0,
                        speed_str="Hoàn tất tải",
                        eta_str="Đang ghép file",
                        phase="merging"
                    )
            except Exception:
                pass

        ytdlp_logger = YtdlpLogger()

        node_bin = shutil.which('node') or ('/usr/bin/node' if os.path.exists('/usr/bin/node') else None) or ('/usr/local/bin/node' if os.path.exists('/usr/local/bin/node') else None)
        ffmpeg_bin = shutil.which('ffmpeg') or ('/usr/local/bin/ffmpeg' if os.path.exists('/usr/local/bin/ffmpeg') else None)

        is_youtube = ("youtube.com" in clean_url or "youtu.be" in clean_url)
        is_bilibili = ("bilibili.com" in clean_url or "b23.tv" in clean_url)

        base_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best' if audio_only else 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/bestvideo+bestaudio/best',
            'outtmpl': output_template,
            'merge_output_format': None if audio_only else 'mp4',
            'ffmpeg_location': ffmpeg_bin,
            'writethumbnail': not audio_only,
            'no_warnings': True,
            'noplaylist': True,
            'progress_hooks': [progress_hook],
            'quiet': True,
            'noprogress': True,
            'logger': ytdlp_logger,
            'socket_timeout': 15,
            'retries': 3,
            'fragment_retries': 4,
            'concurrent_fragment_downloads': 8,
            'file_access_retries': 2,
            'continuedl': True,
            'nocheckcertificate': True,
            'buffersize': 1024 * 1024,
        }

        if node_bin:
            base_opts['js_runtimes'] = {'node': {'path': node_bin}}

        cookie_file = None
        for c_cand in ["cookies.txt", "/content/cookies.txt"]:
            if os.path.exists(c_cand):
                cookie_file = c_cand
                break

        # Danh sách chiến lược tải thích ứng 1080p siêu tốc (Ưu tiên Android VR & Web Embedded để tự động vượt xác minh độ tuổi / bot trên Colab)
        download_strategies = []
        if is_youtube:
            cookie_kwargs = {"cookiefile": cookie_file} if cookie_file else {}
            download_strategies.extend([
                {
                    "name": "YouTube Web Embedded (Bypass Xác Minh & Bot 1080p)",
                    "opts": {
                        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
                        "extractor_args": {
                            "youtube": {
                                "player_client": ["web_embedded"]
                            }
                        },
                        **cookie_kwargs
                    }
                },
                {
                    "name": "YouTube Android VR (Auto-Bypass 1080p)",
                    "opts": {
                        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
                        "extractor_args": {
                            "youtube": {
                                "player_client": ["android_vr"]
                            }
                        },
                        **cookie_kwargs
                    }
                },
                {
                    "name": "YouTube Siêu Tốc 1080p (Direct)",
                    "opts": {
                        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
                        **cookie_kwargs
                    }
                },
                {
                    "name": "YouTube 1080p Native (Brave Cookies)",
                    "opts": {
                        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
                        "cookiesfrombrowser": ("brave",)
                    }
                },
                {
                    "name": "YouTube 1080p Native (Chrome Cookies)",
                    "opts": {
                        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
                        "cookiesfrombrowser": ("chrome",)
                    }
                },
                {
                    "name": "YouTube Fallback 1080p",
                    "opts": {
                        "format": "best[height<=1080]/best",
                        **cookie_kwargs
                    }
                }
            ])
        elif is_bilibili:
            base_opts['socket_timeout'] = 30
            base_opts['retries'] = 5
            base_opts['fragment_retries'] = 5
            base_opts['http_headers'] = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Referer': 'https://www.bilibili.com/',
                'Origin': 'https://www.bilibili.com',
            }
            # Ưu tiên AV1 (100026) và AVC/H.264 (30080) 1080p vì CDN tải cực kỳ ổn định.
            # Không ưu tiên HEVC (30077) vì CDN Bilibili thường ngắt kết nối sau 450KB với người dùng ngoài Trung Quốc.
            bili_format = (
                "bestvideo[vcodec^=av01][height<=1080]+bestaudio/"
                "bestvideo[vcodec^=avc1][height<=1080]+bestaudio/"
                "bestvideo[height<=1080]+bestaudio/"
                "bestvideo[height<=720]+bestaudio/"
                "bestvideo+bestaudio"
            )
            base_opts['format'] = bili_format
            
            download_strategies = [
                {
                    "name": "Bilibili Full HD 1080p (AV1/AVC Siêu Tốc)",
                    "opts": {
                        "format": bili_format,
                    }
                },
                {
                    "name": "Bilibili Full HD 1080p (Brave Cookies)",
                    "opts": {
                        "format": bili_format,
                        "cookiesfrombrowser": ("brave",)
                    }
                },
                {
                    "name": "Bilibili Full HD 1080p (Chrome Cookies)",
                    "opts": {
                        "format": bili_format,
                        "cookiesfrombrowser": ("chrome",)
                    }
                },
                {
                    "name": "Bilibili 720p HD",
                    "opts": {
                        "format": "bestvideo[height<=720]+bestaudio/bestvideo+bestaudio"
                    }
                },
                {
                    "name": "Bilibili Universal Stream",
                    "opts": {
                        "format": "bestvideo+bestaudio/best"
                    }
                }
            ]
        elif "douyin.com" in clean_url or "tiktok.com" in clean_url:
            base_opts['http_headers'] = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.douyin.com/',
            }
            download_strategies = [
                {"name": "TikTok/Douyin 1080p Direct", "opts": {"format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"}},
                {"name": "TikTok/Douyin Universal", "opts": {}}
            ]
        else:
            download_strategies = [
                {"name": "Direct 1080p Full HD", "opts": {"format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"}},
                {"name": "Direct Universal", "opts": {"format": "bestvideo+bestaudio/bestvideo/best"}}
            ]

        last_exception = None
        download_success = False

        try:
            for strat in download_strategies:
                clean_output_dir()
                ydl_opts = dict(base_opts)
                ydl_opts.update(strat.get("opts", {}))
                if audio_only:
                    ydl_opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
                    ydl_opts.pop("merge_output_format", None)

                ui_updater(
                    status_text=f"🔍 [{strat['name']}] Đang kết nối máy chủ và tải dữ liệu...",
                    pct_val=5.0,
                    speed_str="Đang kết nối...",
                    phase="connecting"
                )

                try:
                    ytdlp_logger.logs.clear()
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([clean_url])
                    download_success = True
                    break
                except Exception as e_strat:
                    last_exception = e_strat
                    continue

            if not download_success and is_youtube:
                from utils.youtube_bypass import (
                    extract_youtube_id,
                    download_via_pytubefix,
                    download_via_cloud_mirrors,
                )

                # Fallback 1: Try pytubefix multi-client bypass (WEB_EMBED / MWEB / ANDROID_VR)
                clean_output_dir()
                pt_res = download_via_pytubefix(
                    clean_url,
                    output_dir,
                    audio_only=audio_only,
                    ui_updater=ui_updater
                )
                if pt_res.get("success"):
                    download_success = True

                # Fallback 2: Public Cloud Mirror APIs (Piped / Invidious)
                if not download_success:
                    yt_id = extract_youtube_id(clean_url)
                    if yt_id:
                        clean_output_dir()
                        mirror_res = download_via_cloud_mirrors(
                            yt_id,
                            output_dir,
                            audio_only=audio_only,
                            ui_updater=ui_updater
                        )
                        if mirror_res.get("success"):
                            download_success = True

            if not download_success:
                if last_exception:
                    raise last_exception
                else:
                    raise Exception("Không thể tải video từ đường dẫn này.")
        finally:
            download_status["active"] = False

    except ImportError:
        return {
            "success": False,
            "error": "Không tìm thấy thư viện yt-dlp. Hãy chạy: pip install yt-dlp"
        }
    except Exception as e:
        err_raw = str(e)
        if "unavailable" in err_raw.lower():
            err_msg = "⚠️ Video không tồn tại, đường dẫn sai hoặc video đã bị gỡ bỏ/đặt chế độ riêng tư."
        elif "private video" in err_raw.lower():
            err_msg = "⚠️ Video này ở chế độ riêng tư, không thể tải."
        elif "sign in" in err_raw.lower() or "confirm your age" in err_raw.lower():
            err_msg = "⚠️ Video yêu cầu xác minh độ tuổi hoặc đăng nhập."
        elif "broken pipe" in err_raw.lower() or "errno 32" in err_raw.lower():
            err_msg = "Lỗi kết nối mạng trong quá trình tải. Vui lòng thử lại."
        elif "more expected" in err_raw.lower() or "bytes read" in err_raw.lower():
            err_msg = "Kết nối mạng bị gián đoạn khi tải video. Vui lòng kiểm tra kết nối và thử lại."
        else:
            err_msg = err_raw.splitlines()[0] if err_raw else "Lỗi không xác định khi tải video."
            if ytdlp_logger.logs:
                for l in reversed(ytdlp_logger.logs):
                    if "ERROR:" in l or "unavailable" in l.lower() or "private" in l.lower():
                        err_msg = l
                        break

        return {
            "success": False,
            "error": err_msg
        }

    downloaded_files = list(output_dir.glob("*"))
    if not downloaded_files:
        return {
            "success": False,
            "error": "Không tìm thấy file sau khi tải xong. Link video có thể bị lỗi."
        }

    video_file = str(downloaded_files[0])
    thumbnail_file = None
    
    for f in downloaded_files:
        if f.suffix.lower() in ['.mp4', '.mkv', '.mov', '.webm', '.avi', '.m4a', '.mp3', '.wav', '.ogg', '.flac', '.aac', '.opus']:
            video_file = str(f)
        elif f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']:
            thumbnail_file = str(f)

    video_title = Path(video_file).stem

    ui_updater(
        status_text=f"✅ Đã tải xong: {video_title}",
        pct_val=100.0,
        speed_str="Hoàn tất 100%",
        phase="completed"
    )

    return {
        "success": True,
        "path": video_file,
        "title": video_title,
        "thumbnail_path": thumbnail_file
    }

def render_clips(
    input_path: str,
    output_dir: Path,
    title: str,
    show_part_number: bool,
    clip_duration: int,
    zoom_pct: float = 0.0,
    flip_horizontal: bool = False,
    noise_overlay: bool = False,
    micro_rotation: bool = False,
    frame_drop: bool = False,
    add_noise: bool = False,
    pitch_shift: int = 0,
    speed_factor: float = 1.0,
    dynamic_speed: bool = False,
    dynamic_amplitude: float = 0.03,
    micro_cut: bool = False,
    micro_cut_duration: float = 0.15,
    brightness: float = 0.0,
    contrast: float = 1.0,
    dynamic_shake: bool = False,
    audio_reverb: bool = False,
    output_format: str = "mp4",
    use_gpu: bool = True,
    blur_bg: bool = True,
    output_aspect: str = "9:16 (TikTok/Reels)",
    is_fast_mode: bool = False,
    max_workers: int = 2,
    video_bitrate: str = "4500k",
    progress_bar = None,
    status_text = None,
) -> list[dict]:
    results = []
    safe_title = safe_filename(title) if title else "Clip"

    try:
        info = get_video_info(input_path)
        if "error" in info:
            raise Exception(f"Lỗi đọc video: {info['error']}")

        total_duration = info["duration"]
        src_w, src_h = info["size"]

        # ── 1. TÍNH TOÁN PHÂN ĐOẠN (CHUNKS) ──────────────────────────────
        effective_speed = 1.0 if is_fast_mode else speed_factor
        chunks = []
        start_t = 0.0
        while start_t < total_duration:
            end_t = min(start_t + (clip_duration * effective_speed), total_duration)
            chunks.append({"start": start_t, "end": end_t})
            start_t = end_t

        if len(chunks) > 1:
            last_dur = (chunks[-1]["end"] - chunks[-1]["start"]) / effective_speed
            if last_dur < 60.0:
                chunks[-2]["end"] = chunks[-1]["end"]
                chunks.pop()

        n_clips = len(chunks)

        # ── 2. XÁC ĐỊNH KÍCH THƯỚC VÀ TỈ LỆ ĐẦU RA ────────────────────────
        if "16:9" in output_aspect:
            target_w, target_h = 1920, 1080
            target_dar = "16/9"
        elif "1:1" in output_aspect:
            target_w, target_h = 1080, 1080
            target_dar = "1/1"
        else:  # Mặc định 9:16 (TikTok/Reels/Shorts)
            target_w, target_h = 1080, 1920
            target_dar = "9/16"

        src_aspect = src_w / src_h if src_h > 0 else (16 / 9)
        tgt_aspect = target_w / target_h
        need_blur = blur_bg and abs(src_aspect - tgt_aspect) > 0.05
        z = 1.0 + (zoom_pct / 100.0) if zoom_pct > 0 else 1.0

        commands = []
        for i, chunk in enumerate(chunks):
            start_time = chunk["start"]
            end_time = chunk["end"]
            chunk_duration = (end_time - start_time) / effective_speed
            part_num = i + 1
            output_filename = output_dir / f"{safe_title}_Part_{part_num}.{output_format}"

            # ── CHẾ ĐỘ 1: CẮT SIÊU TỐC (STREAM COPY - 0.2s/clip) ──────────
            if is_fast_mode:
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(start_time),
                    "-i", input_path,
                    "-t", str(end_time - start_time),
                    "-c", "copy",
                    "-movflags", "+faststart",
                    str(output_filename)
                ]
                commands.append(
                    (cmd, None, i, chunk_duration, part_num, output_filename)
                )
                continue

            # ── CHẾ ĐỘ 2: GPU TURBO RENDER (LÁCH BẢN QUYỀN TỐI ƯU) ────────
            v_filters = []
            a_filters = []

            # Khởi tạo đồng bộ Video
            v_filters.append("[0:v]fps=30,setpts=PTS-STARTPTS[v_sync_init]")
            v_node = "[v_sync_init]"
            v_step = 1

            # Nền mờ thông minh: Chỉ render khi cần, gộp zoom foreground
            fg_w = int(target_w * z)
            fg_h = int(target_h * z)
            if need_blur:
                v_filters.append(f"{v_node}split=2[orig][blur]")
                v_filters.append(
                    f"[blur]scale=180:320:force_original_aspect_ratio=increase,crop=180:320,boxblur=2:2,scale={target_w}:{target_h}[bg]"
                )
                v_filters.append(
                    f"[orig]scale={fg_w}:{fg_h}:force_original_aspect_ratio=decrease[fg]"
                )
                v_filters.append(f"[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1[v{v_step}]")
                v_node = f"[v{v_step}]"
                v_step += 1
            else:
                # Video cùng tỉ lệ hoặc người dùng tắt Blur -> Render trực tiếp siêu nhanh
                if z > 1.0:
                    v_filters.append(
                        f"{v_node}scale={fg_w}:{fg_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h}[v{v_step}]"
                    )
                else:
                    v_filters.append(
                        f"{v_node}scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2[v{v_step}]"
                    )
                v_node = f"[v{v_step}]"
                v_step += 1

            # Lật ngang (Mirror Flip)
            if flip_horizontal:
                v_filters.append(f"{v_node}hflip[v{v_step}]")
                v_node = f"[v{v_step}]"
                v_step += 1

            # Xoay nghiêng vi mô
            if micro_rotation:
                v_filters.append(
                    f"{v_node}crop=iw-4:ih-4:2:2,scale={target_w}:{target_h}[v{v_step}]")
                v_node = f"[v{v_step}]"
                v_step += 1

            # Lắc lư động vi mô
            if dynamic_shake:
                v_filters.append(
                    f"{v_node}crop=iw-10:ih-10:x='5+5*sin(t*2)':y='5+5*cos(t*3)',scale={target_w}:{target_h}[v{v_step}]")
                v_node = f"[v{v_step}]"
                v_step += 1

            # Gộp toàn bộ bộ lọc màu (Brightness, Contrast, Dynamic Wave) vào 1 lệnh eq duy nhất
            eq_params = []
            if brightness != 0.0:
                eq_params.append(f"brightness={brightness}")
            if noise_overlay:
                base_c = contrast if contrast != 1.0 else 1.0
                eq_params.append(f"contrast={base_c}+0.005*cos(t*3)")
                eq_params.append("gamma=1.0+0.008*sin(t*2)")
            elif contrast != 1.0:
                eq_params.append(f"contrast={contrast}")

            if eq_params:
                v_filters.append(f"{v_node}eq={':'.join(eq_params)}[v{v_step}]")
                v_node = f"[v{v_step}]"
                v_step += 1

            # Tăng tốc độ video
            if dynamic_speed or speed_factor != 1.0:
                v_filters.append(f"{v_node}setpts=PTS/{speed_factor}[v{v_step}]")
                v_node = f"[v{v_step}]"
                v_step += 1

            # Cắt phân đoạn vi mô (Micro-cut video & audio)
            if micro_cut:
                cut_dur = micro_cut_duration if micro_cut_duration > 0 else 0.15
                v_filters.append(
                    f"{v_node}select='not(between(mod(t,10),0,{cut_dur}))',setpts=N/(30*TB)[v{v_step}]")
                v_node = f"[v{v_step}]"
                v_step += 1

            # Bỏ khung hình (Stutter)
            if frame_drop:
                v_filters.append(
                    f"{v_node}tblend=all_mode=average:all_opacity=0.08[v{v_step}]")
                v_node = f"[v{v_step}]"
                v_step += 1

            # Tiêu đề & Đánh số tập dạng Watermark Text
            text_overlay_path = None
            if title.strip():
                top_txt = title.strip()
                bottom_txt = f"Part {part_num}" if show_part_number else ""

                overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
                draw = ImageDraw.Draw(overlay)

                fontfile = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
                if not os.path.exists(fontfile):
                    fontfile = "/System/Library/Fonts/Helvetica.ttc"

                try:
                    font = ImageFont.truetype(fontfile, 65)
                except BaseException:
                    font = ImageFont.load_default()

                def draw_wrapped_stroke(text, start_y, max_width=target_w - 120, line_spacing=20):
                    words = text.split()
                    lines = []
                    current_line = []
                    for word in words:
                        test_line = " ".join(current_line + [word]) if current_line else word
                        tw = draw.textlength(test_line, font=font)
                        if tw <= max_width:
                            current_line.append(word)
                        else:
                            if current_line:
                                lines.append(" ".join(current_line))
                                current_line = [word]
                            else:
                                lines.append(word)
                                current_line = []
                    if current_line:
                        lines.append(" ".join(current_line))

                    line_data = []
                    for line in lines:
                        bbox = draw.textbbox((0, 0), line, font=font)
                        w = bbox[2] - bbox[0]
                        h = bbox[3] - bbox[1]
                        line_data.append({"text": line, "bbox": bbox, "w": w, "h": h})

                    total_height = sum(ld["h"] for ld in line_data) + line_spacing * (len(lines) - 1)
                    max_w = max(ld["w"] for ld in line_data) if line_data else 0

                    x_start = (target_w - max_w) // 2
                    pad_x, pad_y = 40, 20
                    bg_bbox = [
                        x_start - pad_x,
                        start_y - pad_y,
                        x_start + max_w + pad_x,
                        start_y + total_height + pad_y
                    ]
                    draw.rectangle(bg_bbox, fill=(0, 0, 0, 160))

                    current_y = start_y
                    for ld in line_data:
                        line = ld["text"]
                        bbox = ld["bbox"]
                        w = ld["w"]
                        h = ld["h"]
                        lx = (target_w - w) // 2
                        draw_x = lx - bbox[0]
                        draw_y = current_y - bbox[1]
                        for dx, dy in [(-3, -3), (3, -3), (-3, 3), (3, 3), (0, -3), (-3, 0), (3, 0), (0, 3)]:
                            draw.text((draw_x + dx, draw_y + dy), line, font=font, fill=(0, 0, 0, 255))
                        draw.text((draw_x, draw_y), line, font=font, fill=(255, 235, 59, 255))
                        current_y += h + line_spacing

                if top_txt:
                    draw_wrapped_stroke(top_txt, int(target_h * 0.13))
                if bottom_txt:
                    draw_wrapped_stroke(bottom_txt, int(target_h * 0.80))

                text_overlay_path = output_dir / f"temp_text_{part_num}.png"
                overlay.save(text_overlay_path)

                text_img_idx = 1 if not add_noise else 2
                v_filters.append(
                    f"{v_node}[{text_img_idx}:v]overlay=0:0:format=yuv420:eof_action=repeat[v{v_step}]"
                )
                v_node = f"[v{v_step}]"
                v_step += 1

            v_filters.append(f"{v_node}setsar=1:1,setdar={target_dar}[v_out]")

            # ── Âm Thanh Tối Ưu (Audio Filter Chain tinh gọn) ──────────────
            a_chain = ["asetpts=PTS-STARTPTS"]
            if micro_cut:
                cut_dur = micro_cut_duration if micro_cut_duration > 0 else 0.15
                a_chain.append(f"aselect='not(between(mod(t,10),0,{cut_dur}))'")
                a_chain.append("asetpts=N/(48000*TB)")

            if pitch_shift != 0 or speed_factor != 1.0 or dynamic_speed:
                ratio = 2 ** (pitch_shift / 12)
                final_atempo = speed_factor / ratio
                atempo_chain = []
                temp = final_atempo
                while temp > 2.0:
                    atempo_chain.append("atempo=2.0")
                    temp /= 2.0
                while temp < 0.5:
                    atempo_chain.append("atempo=0.5")
                    temp *= 2.0
                if temp != 1.0 or not atempo_chain:
                    atempo_chain.append(f"atempo={temp:.3f}")
                atempo_str = ",".join(atempo_chain)

                if pitch_shift != 0:
                    a_chain.append(f"asetrate=48000*{ratio:.4f}")
                    a_chain.append(atempo_str)
                else:
                    a_chain.append(atempo_str)

            if audio_reverb:
                a_chain.append("aecho=0.8:0.88:6:0.4")

            a_chain.append("aresample=48000:async=1000:first_pts=0")
            a_chain.append("asetpts=PTS-STARTPTS")

            a_filters.append(f"[0:a]{','.join(a_chain)}[a_sync]")
            a_node = "[a_sync]"

            if add_noise:
                a_filters.append(f"{a_node}[1:a]amix=inputs=2:duration=first:weights=100 1[a_out]")
            else:
                a_filters.append(f"{a_node}anull[a_out]")

            filter_complex_str = ";".join(v_filters + a_filters)

            cmd = [
                "ffmpeg", "-y",
                "-threads", "4",
                "-accurate_seek",
                "-ss", str(start_time),
                "-t", str(end_time - start_time),
                "-i", input_path
            ]

            if add_noise:
                cmd.extend(["-f", "lavfi", "-i", "aevalsrc=random(0)-0.5:s=44100"])

            if text_overlay_path:
                cmd.extend(["-i", str(text_overlay_path)])

            cmd.extend([
                "-filter_complex", filter_complex_str,
                "-map", "[v_out]",
                "-map", "[a_out]"
            ])

            from utils.hardware_accelerator import get_optimal_h264_encoder_args
            cmd.extend(
                get_optimal_h264_encoder_args(
                    use_gpu=use_gpu,
                    bitrate=str(video_bitrate),
                    crf="23",
                    preset="veryfast",
                    fps=30
                )
            )

            cmd.extend(["-c:a", "aac", "-movflags", "+faststart", str(output_filename)])
            commands.append(
                (cmd, text_overlay_path, i, chunk_duration, part_num, output_filename)
            )

        # ── 3. THỰC THI TIẾN TRÌNH FFMPEG ─────────────────────────────────
        import concurrent.futures

        def run_ffmpeg(item):
            cmd, txt_path, idx, chunk_dur, part_n, out_file = item
            start_render = time.time()
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )

            with PROCESSES_LOCK:
                ACTIVE_PROCESSES.append(process)

            error_details = ""
            for line in process.stdout:
                if "Error" in line or "Invalid" in line or "matches no streams" in line:
                    error_details += line
            process.wait()

            with PROCESSES_LOCK:
                if process in ACTIVE_PROCESSES:
                    ACTIVE_PROCESSES.remove(process)

            if txt_path and os.path.exists(txt_path):
                try:
                    os.remove(txt_path)
                except BaseException:
                    pass

            if process.returncode != 0:
                if not error_details:
                    error_details = f"Return code = {process.returncode}"
                with open("ffmpeg_crash_cmd.txt", "w") as f:
                    f.write(" ".join(cmd))
                raise Exception(f"Phần {part_n} lỗi: {error_details}")

            return {
                "part": part_n,
                "name": f"Phần {part_n}",
                "file": str(out_file),
                "duration": chunk_dur,
                "time_taken": time.time() - start_render,
                "size": os.path.getsize(out_file),
                "success": True
            }

        completed = 0
        start_render_all = time.time()
        if status_text:
            if is_fast_mode:
                status_text.markdown(f"**⚡ Đang cắt siêu tốc (Stream Copy) {n_clips} clip... (Đang khởi động)**")
            else:
                status_text.markdown(f"**🚀 Đang nén GPU tối ưu {n_clips} clip ({max_workers} luồng song song)... (Đang khởi động)**")

        # Chạy đa luồng theo cấu hình tối ưu
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=max(1, int(max_workers)))
        try:
            futures = [executor.submit(run_ffmpeg, item) for item in commands]
            for future in concurrent.futures.as_completed(futures):
                try:
                    res = future.result()
                    results.append(res)
                    completed += 1
                    
                    elapsed = time.time() - start_render_all
                    avg_time_per_clip = elapsed / completed
                    remaining_clips = n_clips - completed
                    est_remaining_sec = int(remaining_clips * avg_time_per_clip)
                    
                    elapsed_min, elapsed_sec = divmod(int(elapsed), 60)
                    rem_min, rem_sec = divmod(est_remaining_sec, 60)
                    pct = int((completed / n_clips) * 100)
                    
                    if progress_bar:
                        progress_bar.progress(completed / n_clips)
                    if status_text:
                        mode_title = "⚡ Siêu Tốc" if is_fast_mode else f"🚀 GPU T4 ({max_workers} luồng)"
                        rem_str = f"{rem_min}p {rem_sec:02d}s" if rem_min > 0 else f"{rem_sec}s"
                        status_text.markdown(
                            f"**{mode_title} | Đã xong: {completed}/{n_clips} clip ({pct}%)**\n\n"
                            f"⏱️ Đã chạy: `{elapsed_min:02d}:{elapsed_sec:02d}` | ⏳ **Ước tính còn lại: ~`{rem_str}`**"
                        )
                except Exception as thread_err:
                    executor.shutdown(wait=False, cancel_futures=True)
                    with PROCESSES_LOCK:
                        for p in ACTIVE_PROCESSES:
                            try:
                                p.kill()
                            except Exception:
                                pass
                        ACTIVE_PROCESSES.clear()
                    raise thread_err
        finally:
            executor.shutdown(wait=False)

        results.sort(key=lambda x: x["part"])
        return results

    except Exception as e:
        if status_text:
            status_text.error(f"❌ Lỗi: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

