"""
Feature module: STT Tools (Audio/Video to Text & Subtitles)
Dedicated file for speech-to-text transcription from Video Links or local Files.
"""

import streamlit as st
import time
import tempfile
import shutil
import subprocess
from pathlib import Path

def extract_lightweight_audio(input_file: Path, output_file: Path) -> bool:
    """Tách và nén âm thanh thành mp3 siêu nhẹ (mono, 64kbps, 16kHz) để upload lên AI STT nhanh chóng và không bị quá 200MB."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_file),
        "-vn",
        "-acodec", "libmp3lame",
        "-ac", "1",
        "-ar", "16000",
        "-b:a", "64k",
        str(output_file)
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        return res.returncode == 0 and output_file.exists() and output_file.stat().st_size > 0
    except Exception:
        return False

def render_stt_tools():
    """Renders the 'Audio to Text' feature tab."""
    from utils.capcut_stt_wrapper import generate_stt, payload_to_text, payload_to_srt
    from features.common_ui import YTDLP_AVAILABLE, download_video_from_url
    
    plain_text = ""
    srt_text = ""
    timestamp_str = int(time.time())
    
    st.markdown("""
    <div class="hero-banner">
    <div class="hero-title">🎧 Lấy File Nội Dung (.txt) Từ Video</div>
    <div class="hero-subtitle">Bóc băng Video thành File Text (.txt) & Phụ Đề (.srt) qua Link hoặc File tải lên</div>
    <div class="badge-row">
    <span class="badge">🌐 Đa nguồn (Link & File)</span>
    <span class="badge">🇻🇳 Tiếng Việt & Đa ngôn ngữ</span>
    <span class="badge">⚡ Tự động nén Audio siêu nhẹ</span>
    <span class="badge">📝 Xuất File .txt & .srt</span>
    </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">📌 Nguồn Đầu Vào</div>', unsafe_allow_html=True)
    
    input_mode = st.radio(
        "Chọn nguồn video/audio:",
        ["📂 Tải File Lên (Máy tính)", "🔗 Dán Link Video (YouTube, TikTok, Facebook...)"],
        horizontal=True
    )
    
    file_to_process = None
    url_to_process = ""
    
    if input_mode == "📂 Tải File Lên (Máy tính)":
        uploaded_file = st.file_uploader(
            "Kéo thả Audio hoặc Video vào đây", 
            type=["mp3", "wav", "m4a", "ogg", "flac", "webm", "mp4", "mov", "mkv"]
        )
        if uploaded_file:
            file_to_process = uploaded_file
    else:
        if not YTDLP_AVAILABLE:
            st.error("⚠️ Cần cài `yt-dlp` để tải video từ Link: `pip install yt-dlp`")
        url_to_process = st.text_input(
            "Dán link video vào đây:", 
            placeholder="https://www.youtube.com/watch?v=... hoặc link TikTok/Facebook",
            key="stt_url_input"
        )
    
    st.markdown('<br><div class="card-title">⚙️ Cấu Hình Ngôn Ngữ & Độ Dài Phụ Đề</div>', unsafe_allow_html=True)
    col_cfg1, col_cfg2 = st.columns(2)
    with col_cfg1:
        lang_map = {
            "Tiếng Việt (vi-VN)": "vi-VN",
            "English (en-US)": "en-US",
            "Tiếng Trung Quốc (zh-CN)": "zh-CN",
            "Tiếng Hàn Quốc (ko-KR)": "ko-KR",
            "Tiếng Nhật (ja-JP)": "ja-JP"
        }
        selected_lang = st.selectbox("🌐 Ngôn ngữ phát âm trong Video/Audio:", list(lang_map.keys()), index=0, key="stt_lang_select")
    
    with col_cfg2:
        srt_style = st.selectbox(
            "📏 Độ dài dòng phụ đề (.srt):",
            [
                "🎯 Chuẩn phụ đề Video (Tự nhiên 6–12 từ / câu)",
                "📜 Cả câu dài đầy đủ (Full sentence 12–20 từ)",
                "⚡ Từng cụm ngắn (TikTok / Shorts 3–6 từ)"
            ],
            index=0,
            key="stt_style_select"
        )
    
    if "Cả câu dài" in srt_style:
        max_dur = 8000
        max_words = 18
    elif "Từng cụm ngắn" in srt_style:
        max_dur = 2800
        max_words = 6
    else:
        max_dur = 4800
        max_words = 11
    
    if st.button("🚀 Trích Xuất File Nội Dung (.txt & .srt)", use_container_width=True, type="primary"):
        if input_mode.startswith("📂") and not file_to_process:
            st.warning("Vui lòng chọn hoặc kéo thả file audio/video lên trước!")
        elif input_mode.startswith("🔗") and not url_to_process.strip():
            st.warning("Vui lòng nhập link video!")
        else:
            temp_dir = Path(tempfile.mkdtemp())
            status_box = st.empty()
            
            try:
                target_audio_path = None
                
                # 1. Xử lý nguồn file hoặc link
                if input_mode.startswith("📂"):
                    status_box.info("⏳ Đang đọc file tải lên...")
                    target_audio_path = temp_dir / file_to_process.name
                    with open(target_audio_path, "wb") as f:
                        f.write(file_to_process.getbuffer())
                else:
                    status_box.info("⏳ Đang tải luồng âm thanh tốc độ cao từ Link...")
                    dl_res = download_video_from_url(
                        url=url_to_process,
                        output_dir=temp_dir,
                        progress_placeholder=status_box,
                        audio_only=True
                    )
                    if not dl_res["success"]:
                        st.error(f"❌ Không thể lấy video từ link: {dl_res.get('error', 'Lỗi không xác định')}")
                        return
                    target_audio_path = Path(dl_res["path"])
                
                # 2. Tự động bóc tách & nén audio siêu nhẹ (tránh lỗi file quá 200MB)
                status_box.info("🎵 Đang tối ưu hóa âm thanh (nén file & lọc tạp âm) để xử lý nhanh nhất...")
                opt_audio_path = temp_dir / "stt_optimized_audio.mp3"
                if extract_lightweight_audio(target_audio_path, opt_audio_path):
                    stt_file_path = str(opt_audio_path)
                else:
                    stt_file_path = str(target_audio_path)
                
                # 3. Gọi AI Bóc Băng (STT)
                status_box.info("🤖 Đang phân tích giọng nói và tạo file văn bản... Quá trình này có thể mất ít phút.")
                success, payload_or_error = generate_stt(stt_file_path, lang_map[selected_lang])
                
                status_box.empty()
                
                if success:
                    st.success("🎉 Trích xuất nội dung văn bản thành công!")
                    
                    plain_text = payload_to_text(payload_or_error)
                    srt_text = payload_to_srt(payload_or_error, max_duration_ms=max_dur, max_words_per_line=max_words)
                    timestamp_str = int(time.time())
                    
                    st.session_state["stt_plain_text"] = plain_text
                    st.session_state["stt_srt_text"] = srt_text
                    st.session_state["stt_timestamp"] = timestamp_str
                    
                else:
                    st.error(f"❌ Thất bại: {payload_or_error}")
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)
                
    # Hiển thị kết quả nếu đã có trong session_state
    if st.session_state.get("stt_plain_text"):
        plain_text = st.session_state["stt_plain_text"]
        srt_text = st.session_state.get("stt_srt_text", "")
        timestamp_str = st.session_state.get("stt_timestamp", int(time.time()))
        
        st.markdown("<hr style='border-color: rgba(255,255,255,0.1); margin: 20px 0;'>", unsafe_allow_html=True)
        st.markdown('<div class="card-title">📊 Kết Quả Trích Xuất</div>', unsafe_allow_html=True)
        
        # 3. Download & Quick Action Buttons
        col1, col2, col3 = st.columns(3)
        with col1:
            st.download_button(
                "📄 Tải File Văn Bản (.txt)",
                data=plain_text,
                file_name=f"noi_dung_video_{timestamp_str}.txt",
                mime="text/plain",
                use_container_width=True,
                type="primary"
            )
        with col2:
            st.download_button(
                "🎬 Tải File Phụ Đề (.srt)",
                data=srt_text,
                file_name=f"phu_de_video_{timestamp_str}.srt",
                mime="text/plain",
                use_container_width=True
            )
        with col3:
            if st.button("🎙️ Gửi Sang Tạo Giọng Đọc / OmniVoice", use_container_width=True, key="btn_send_stt_to_tts"):
                st.session_state["capcut_text_input"] = plain_text
                st.session_state["omni_target_text"] = plain_text
                st.toast("✅ Đã nạp văn bản vào Tab Tạo Giọng Đọc (CapCut TTS & OmniVoice)!", icon="🎙️")
                st.success("✅ Đã gửi văn bản sang mục 'Tạo Giọng Đọc'!")
        
        # 4. Preview Tabs
        tab_txt, tab_srt = st.tabs(["📄 Xem Trước File Text (.txt)", "🎬 Xem Trước Phụ Đề (.srt)"])
        with tab_txt:
            render_copy_button(plain_text, "📋 Sao Chép Nội Dung TXT", "copy_txt_btn")
            st.text_area("Nội dung bài nói (.txt)", value=plain_text, height=320)
        with tab_srt:
            render_copy_button(srt_text, "📋 Sao Chép Phụ Đề SRT", "copy_srt_btn")
            st.code(srt_text, language="text")
                    
    st.markdown('</div>', unsafe_allow_html=True)


def render_copy_button(text_to_copy: str, button_label: str = "📋 Sao chép nội dung TXT", element_id: str = "btn_copy"):
    """Hiển thị nút sao chép văn bản vào clipboard người dùng qua HTML/JS."""
    import json
    import streamlit.components.v1 as components
    
    escaped_text = json.dumps(text_to_copy)
    html_code = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin-bottom: 6px;">
        <button id="{element_id}" onclick="copyToClipboard_{element_id}()" style="
            width: 100%;
            background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%);
            color: #ffffff;
            border: none;
            padding: 9px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            font-size: 14px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.25);
            transition: all 0.2s ease;
        " onmouseover="this.style.opacity='0.9'; this.style.transform='translateY(-1px)';" onmouseout="this.style.opacity='1'; this.style.transform='translateY(0)';" onmousedown="this.style.transform='scale(0.98)';">
            <span>{button_label}</span>
        </button>
        <div id="toast_{element_id}" style="display:none; margin-top: 6px; color: #10b981; font-size: 13px; font-weight: 600; text-align: center;">
            ✅ Đã sao chép vào bộ nhớ tạm!
        </div>
    </div>
    <script>
    function copyToClipboard_{element_id}() {{
        const text = {escaped_text};
        if (navigator.clipboard && window.isSecureContext) {{
            navigator.clipboard.writeText(text).then(function() {{
                showToast_{element_id}("✅ Đã sao chép vào bộ nhớ tạm!");
            }}).catch(function(err) {{
                fallbackCopy_{element_id}(text);
            }});
        }} else {{
            fallbackCopy_{element_id}(text);
        }}
    }}
    function fallbackCopy_{element_id}(text) {{
        try {{
            const textArea = document.createElement("textarea");
            textArea.value = text;
            textArea.style.position = "fixed";
            textArea.style.left = "-999999px";
            textArea.style.top = "-999999px";
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            document.execCommand("copy");
            document.body.removeChild(textArea);
            showToast_{element_id}("✅ Đã sao chép vào bộ nhớ tạm!");
        }} catch(e) {{
            showToast_{element_id}("⚠️ Không thể tự động copy. Vui lòng copy thủ công.");
        }}
    }}
    function showToast_{element_id}(msg) {{
        const toast = document.getElementById('toast_{element_id}');
        toast.innerText = msg;
        toast.style.display = 'block';
        setTimeout(function() {{
            toast.style.display = 'none';
        }}, 3000);
    }}
    </script>
    """
    components.html(html_code, height=65)


