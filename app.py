"""
╔══════════════════════════════════════════════════════════╗
║         VIDEO SPLITTER PRO - TikTok/Reels/Shorts         ║
║         Tự động cắt video & xử lý lách bản quyền        ║
╚══════════════════════════════════════════════════════════╝

Main entrypoint for Video Splitter Pro.
All feature tab implementations are housed in independent modular files inside features/
"""

import streamlit as st
import threading
import time
import os
import subprocess
from streamlit_option_menu import option_menu

from features.common_ui import load_custom_css

# ─── Auto-Shutdown Monitor ─────────────────────────────────────────────
def start_auto_shutdown_monitor(timeout_seconds=10, startup_grace_seconds=30):
    """
    Theo dõi các tab trình duyệt kết nối với Streamlit.
    Nếu không có tab nào mở trong hơn `timeout_seconds` giây (sau thời gian khởi động), 
    tự động hủy tất cả tiến trình ffmpeg ngầm và tắt hẳn server Streamlit.
    Tự động vô hiệu hóa nếu đang chạy trên Google Colab / Cloud.
    """
    if getattr(st, "_auto_shutdown_started", False):
        return
    st._auto_shutdown_started = True

    is_colab = any(k in os.environ for k in ["COLAB_GPU", "COLAB_RELEASE_TAG", "COLAB_BACKEND_VERSION"]) or os.environ.get("DISABLE_AUTO_SHUTDOWN") == "1"
    if is_colab:
        print("[Auto-Shutdown] Đang chạy trên môi trường Google Colab / Cloud. Đã tắt tính năng tự động shutdown.")
        return

    def monitor():
        from streamlit.runtime import get_instance
        zero_session_start = None
        server_start_time = time.time()
        has_had_session = False

        while True:
            time.sleep(1)
            try:
                runtime = get_instance()
                sessions = runtime._session_mgr.list_active_sessions()
                count = len(sessions)

                if count > 0:
                    has_had_session = True
                    zero_session_start = None
                else:
                    if not has_had_session and (time.time() - server_start_time < startup_grace_seconds):
                        continue

                    if zero_session_start is None:
                        zero_session_start = time.time()
                    elif time.time() - zero_session_start >= timeout_seconds:
                        print("\n[Auto-Shutdown] Không còn tab trình duyệt nào mở. Đang tắt app và hủy các tác vụ ngầm...")
                        try:
                            subprocess.run(["pkill", "-9", "-f", "ffmpeg"], stderr=subprocess.DEVNULL)
                            subprocess.run(["pkill", "-9", "-f", "autocut"], stderr=subprocess.DEVNULL)
                        except Exception:
                            pass
                        os._exit(0)
            except Exception:
                pass

    t = threading.Thread(target=monitor, daemon=True)
    t.start()

start_auto_shutdown_monitor(timeout_seconds=10, startup_grace_seconds=30)

# ─── Page Configuration ────────────────────────────────────────────────
st.set_page_config(
    page_title="NgDuyKhanh Pro",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Load Custom CSS Styling ───────────────────────────────────────────
load_custom_css()

# ─── Global Process State Initialization ──────────────────────────────
if "process_lock" not in st.session_state:
    st.session_state["process_lock"] = threading.Lock()
if "stop_event" not in st.session_state:
    st.session_state["stop_event"] = threading.Event()
if "active_processes" not in st.session_state:
    st.session_state["active_processes"] = []
if "is_running" not in st.session_state:
    st.session_state["is_running"] = False
# Load local .env if present (keeps API keys out of Git)
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path, "r", encoding="utf-8") as _ef:
        for _line in _ef:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

if "gemini_api_key" not in st.session_state:
    st.session_state["gemini_api_key"] = os.environ.get("GEMINI_API_KEY", "")
if st.session_state["gemini_api_key"]:
    os.environ["GEMINI_API_KEY"] = st.session_state["gemini_api_key"]


def main():
    """Main routing orchestrator delegating to modular feature files."""
    with st.sidebar:
        st.markdown("""
        <div style="display:flex; align-items:center; gap:10px; padding:0.1rem 0.25rem 0.85rem; border-bottom: 1px solid #202430; margin-bottom: 0.85rem; margin-top: -0.5rem;">
            <div style="width:36px; height:36px; background:linear-gradient(135deg, #0284c7, #06b6d4); border-radius:9px; display:flex; align-items:center; justify-content:center; box-shadow:0 2px 10px rgba(2,132,199,0.4); font-size:18px; flex-shrink:0;">🎬</div>
            <div>
                <div style="font-size:1.1rem; font-weight:800; color:#ffffff; line-height:1.15; letter-spacing:-0.02em;">NgDuyKhanh <span style="color:#38bdf8;">Pro</span></div>
                <div style="font-size:0.68rem; color:#9ca3af; font-weight:600; text-transform:uppercase; letter-spacing:0.06em; margin-top:2px;">Video Studio Pro</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        app_mode = option_menu(
            menu_title=None,
            options=["Cắt Video", "Xử lý SRT", "Auto-Cut", "Video Recap", "Vô Tri TV", "Tải Video", "Tách Giọng & Nhạc", "Google Flow", "Tạo Giọng Đọc", "Audio to Text"],
            icons=["scissors", "file-earmark-text", "film", "camera-reels", "emoji-laughing", "cloud-download", "music-note-beamed", "robot", "mic", "file-music"],
            default_index=0,
            orientation="vertical",
            styles={
                "container": {
                    "padding": "6px !important",
                    "background-color": "#13161f",
                    "border": "1px solid #202430",
                    "border-radius": "10px",
                    "margin-bottom": "0.85rem",
                    "width": "100%",
                },
                "icon": {"color": "#38bdf8", "font-size": "15px"},
                "nav-link": {
                    "font-size": "14px",
                    "text-align": "left",
                    "margin": "3px 0px",
                    "color": "#f1f5f9",
                    "padding": "9px 12px",
                    "border-radius": "8px",
                    "font-weight": "600",
                    "--hover-color": "#1e293b",
                },
                "nav-link-selected": {
                    "background": "linear-gradient(135deg, #0284c7 0%, #0369a1 100%)",
                    "color": "#ffffff",
                    "font-weight": "700",
                    "border-radius": "8px",
                    "box-shadow": "0 2px 10px rgba(2,132,199,0.45)",
                },
            }
        )

        from utils.hardware_accelerator import (
            detect_best_video_encoder,
            get_optimal_onnx_providers,
            get_storage_stats,
            cleanup_output_caches,
        )
        hw_enc = detect_best_video_encoder()
        _, onnx_label = get_optimal_onnx_providers()
        storage_info = get_storage_stats()

        with st.expander("⚙️ Hệ Thống & Dọn Bộ Nhớ", expanded=False):
            st.markdown(
                f"""
                <div style="font-size:0.76rem; color:#cbd5e1; line-height:1.65;">
                    <div>🎬 <b>Render:</b> <span style="color:#38bdf8;">{hw_enc['encoder']}</span></div>
                    <div>🧠 <b>AI Engine:</b> <span style="color:#a855f7;">{onnx_label}</span></div>
                    <div>💾 <b>File tạm:</b> <span style="color:#f59e0b;">{storage_info['total_cache_gb']:.2f} GB</span> (Trống: {storage_info['free_disk_gb']:.1f} GB)</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("🧹 Dọn Sạch File Tạm / Cache", use_container_width=True, key="sidebar_clean_cache_btn"):
                n_del, mb_freed = cleanup_output_caches()
                st.toast(f"Đã xóa {n_del} file tạm, giải phóng {mb_freed:.1f} MB!", icon="🧹")
                st.success(f"Đã giải phóng {mb_freed:.1f} MB ({n_del} file)!")
                time.sleep(0.6)
                st.rerun()

            api_k = st.text_input(
                "🔑 Gemini API Key:",
                value=st.session_state.get("gemini_api_key", ""),
                type="password",
                key="sidebar_gemini_key_input",
            )
            if api_k and api_k != st.session_state.get("gemini_api_key"):
                st.session_state["gemini_api_key"] = api_k.strip()
                os.environ["GEMINI_API_KEY"] = api_k.strip()

        st.markdown("""
        <div style="padding:0.6rem 0.25rem; border-top:1px solid #202430; margin-top:0.4rem; display:flex; align-items:center; justify-content:space-between;">
            <div style="display:flex; align-items:center; gap:6px;">
                <span style="width:6px; height:6px; background:#10b981; border-radius:50%; box-shadow:0 0 6px #10b981;"></span>
                <span style="font-size:0.72rem; color:#9ca3af; font-weight:600;">Turbo Ready</span>
            </div>
            <span style="font-size:0.68rem; color:#38bdf8; font-weight:700; font-family:ui-monospace, monospace;">v3.0 Pro</span>
        </div>
        """, unsafe_allow_html=True)

    if app_mode == "Cắt Video":
        from features.video_splitter import render_video_splitter_tab
        render_video_splitter_tab()
    elif app_mode == "Xử lý SRT":
        from features.srt_tools import render_srt_tools
        render_srt_tools()
    elif app_mode == "Auto-Cut":
        from features.autocut_tools import render_autocut_tools
        render_autocut_tools()
    elif app_mode == "Video Recap":
        from features.recap_tools import render_recap_tools
        render_recap_tools()
    elif app_mode == "Vô Tri TV":
        from features.votri_tools import render_votri_tools
        render_votri_tools()
    elif app_mode == "Tải Video":
        from features.downloader_tools import render_downloader_tools
        render_downloader_tools()
    elif app_mode == "Tách Giọng & Nhạc":
        from features.vocal_separation_tools import render_vocal_separation_tools
        render_vocal_separation_tools()
    elif app_mode == "Google Flow":
        from features.gf_ui import render_google_flow
        render_google_flow()
    elif app_mode == "Tạo Giọng Đọc":
        from features.tts_tools import render_tts_tools
        render_tts_tools()
    elif app_mode == "Audio to Text":
        from features.stt_tools import render_stt_tools
        render_stt_tools()


if __name__ == "__main__":
    main()

