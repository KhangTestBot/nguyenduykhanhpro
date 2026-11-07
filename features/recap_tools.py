"""
Feature module: AI Video Recap & Highlight Storyteller Studio.
Automatically extracts highlight moments and writes storytelling narration scripts
from local video files or video URLs with strict visual grounding and frame-accurate sync.
"""

import os
import time
import shutil
import tempfile
from pathlib import Path
import streamlit as st

import importlib
import utils.recap_builder as recap_builder
import utils.capcut_draft_editor as capcut_draft_editor
from utils.capcut_tts_wrapper import generate_tts, get_available_voices, get_or_create_voice_preview
from utils.capcut_draft_editor import get_mac_capcut_projects, inject_broll_sequence_and_audio_to_draft
from features.common_ui import YTDLP_AVAILABLE, download_video_from_url, human_size

DEFAULT_GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

VIETNAMESE_VOICES = {
    "🇻🇳 Cô Gái Hoạt Ngôn (Thuyết Minh / Kể Chuyện)": {"voice_type": "BV074_streaming", "resource_id": "7102355709945188865"},
    "🇻🇳 Review Phim (Giọng Thuyết Minh Chuẩn)": {"voice_type": "multi_female_richgirl_uranus_bigtts", "resource_id": "7637460351541447956"},
    "🇻🇳 Ban Mai (Truyền Cảm & Tự Nhiên)": {"voice_type": "multi_female_yangguangnv_uranus_bigtts", "resource_id": "7637456432522218773"},
    "🇻🇳 Review Phim 2 (Sống Động)": {"voice_type": "multi_female_xyf04auto_uranus_bigtts", "resource_id": "7637458743197732117"},
    "🇻🇳 Review Phim 3 (Kịch Tính)": {"voice_type": "multi_female_daqi_uranus_bigtts", "resource_id": "7637451983389019409"},
    "🇻🇳 Giọng Nữ Phổ Thông": {"voice_type": "vi_female_huong", "resource_id": "7264854897953083905"},
    "🇻🇳 Kenny Đại Đế (Nam Mạnh Mẽ)": {"voice_type": "BV075_streaming_demon_dsp", "resource_id": "7569442422665661712"},
    "🇺🇸 Adam (Deep Narrator)": {"voice_type": "en_male_adam", "resource_id": "7525722920161725712"},
}


def render_recap_tools(is_votritv_mode: bool = False):
    """Renders the AI Video Recap tab."""
    importlib.reload(recap_builder)

    if "gemini_api_key" not in st.session_state or not st.session_state["gemini_api_key"]:
        st.session_state["gemini_api_key"] = DEFAULT_GEMINI_KEY

    api_key = st.session_state.get("gemini_api_key", DEFAULT_GEMINI_KEY)

    st.markdown("""
    <div class="hero-banner">
    <div class="hero-title">🎬 AI Video Recap & Review Phim Studio Pro</div>
    <div class="hero-subtitle">Tự động bóc tách cảnh đắt giá, viết kịch bản đa hồi chuẩn kênh 'Não Động Review' & Lách bản quyền điện ảnh 100%</div>
    <div class="badge-row">
    <span class="badge">🔥 Chuẩn Kênh Não Động Review</span>
    <span class="badge">🎭 Phân Hồi Đa Tầng (15-25 Phút)</span>
    <span class="badge">🛡️ Lật Hình + Cắt Sub + Logo Tròn</span>
    <span class="badge">🧬 Nhân Bản Giọng Từ Link Mẫu</span>
    <span class="badge">🚀 Tăng Tốc GPU NVENC</span>
    </div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("🔑 Cấu hình Gemini API Key & Model AI (Mặc định đã kết nối sẵn)", expanded=False):
        c_k1, c_k2 = st.columns([3, 2])
        with c_k1:
            key_input = st.text_area(
                "Gemini API Key(s) - Nhập 1 hoặc nhiều Key cách nhau bằng dấu phẩy để không bị giới hạn hạn mức:",
                value=api_key,
                placeholder="AIzaSy..., AIzaSy...",
                key="recap_api_key_input",
                height=68
            )
            if key_input:
                st.session_state["gemini_api_key"] = key_input.strip()
                api_key = key_input.strip()
        with c_k2:
            model_options = {
                "⚡ Gemini Flash (Tối ưu Video & Siêu tốc - Khuyên dùng)": "models/gemini-flash-latest",
                "🔥 Gemini Flash Lite (Siêu nhẹ, Ổn định Quota)": "models/gemini-flash-lite-latest",
                "🚀 Gemini 3.5 Flash Lite (Mới nhất)": "models/gemini-3.5-flash-lite",
                "✨ Gemini 3.6 Flash (Bản thử nghiệm)": "models/gemini-3.6-flash",
                "🛠️ Tùy chỉnh (Nhập ID Model khác)": "custom"
            }
            chosen_model_label = st.selectbox("🤖 Chọn Model AI:", list(model_options.keys()), index=0, key="recap_model_select")
            selected_model = model_options[chosen_model_label]
            if selected_model == "custom":
                selected_model = st.text_input("Nhập Model ID:", value="models/gemini-flash-latest", key="recap_custom_model_input")
        st.success("✅ Đã kết nối sẵn Gemini API Key & hỗ trợ tự động Fallback / Chống giới hạn hạn mức!")

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">📥 1. Nguồn Video Phim Gốc & Phụ Đề Tham Chiếu</div>', unsafe_allow_html=True)

    input_mode = st.radio(
        "Chọn nguồn video:",
        ["📂 Tải File Video Lên (Máy tính)", "🔗 Dán Link Video (YouTube, TikTok, Facebook...)"],
        horizontal=True,
        key="recap_input_mode"
    )

    uploaded_video = None
    url_to_process = ""

    if input_mode.startswith("📂"):
        uploaded_video = st.file_uploader(
            "Kéo thả video cần Review / Recap vào đây (MP4, MOV, MKV, WebM):",
            type=["mp4", "mov", "mkv", "webm", "avi", "flv"],
            key="recap_file_uploader"
        )
        st.caption("✨ Tải file trực tiếp từ máy tính sẽ giữ trọn vẹn 100% độ phân giải 1080p gốc sắc nét nhất.")
    else:
        if not YTDLP_AVAILABLE:
            st.error("⚠️ Cần cài `yt-dlp` để tải video từ Link: `pip install yt-dlp`")
        url_to_process = st.text_input(
            "Dán link video vào đây:",
            placeholder="https://www.youtube.com/watch?v=... hoặc link TikTok/Facebook",
            key="recap_url_input"
        )
        st.caption("💡 Hệ thống tự động vượt xác minh tuổi, lấy luồng 1080p nét nhất và khử mờ bằng thuật toán Unsharp Lanczos.")

    st.markdown('<br><div class="card-title">🎨 2. Cấu Hình Phong Cách Review Phim, Thời Lượng & Giọng Đọc</div>', unsafe_allow_html=True)
    
    col_dur1, col_dur2 = st.columns([1.2, 1.8])
    with col_dur1:
        dur_mode = st.radio(
            "Mục tiêu thời lượng bản Review:",
            [
                "🔥 Chuẩn Review Phim Chuyên Sâu YouTube (12 - 22 phút)",
                "📊 Theo % Thời Lượng Video Gốc",
                "⏱️ Số Giây / Phút Cố Định (Tới 30 phút)"
            ],
            index=0 if not is_votritv_mode else 1,
            key="recap_dur_mode"
        )
    with col_dur2:
        if "Chuẩn Review Phim Chuyên Sâu" in dur_mode:
            target_minutes = st.slider(
                "Thời lượng Review Phim chuyên sâu mong muốn (Phút):",
                min_value=8,
                max_value=25,
                value=18,
                step=1,
                format="%d phút",
                help="Chuẩn kênh Não Động Review thường kéo dài từ 15 đến 21 phút để kể trọn vẹn mọi nút thắt và thông điệp cuối phim."
            )
            recap_dur = target_minutes * 60
            recap_ratio = 0.25
            st.caption(f"🎬 Mục tiêu: **{target_minutes} phút ({recap_dur} giây)** — Tự động chia thành nhiều Hồi nối tiếp liền mạch.")
        elif "Theo %" in dur_mode:
            default_pct = 40 if is_votritv_mode else 25
            recap_percent = st.slider(
                "Tỷ lệ tóm tắt (% thời lượng video gốc):",
                min_value=10,
                max_value=90,
                value=default_pct,
                step=5,
                format="%d%%",
                help="Ví dụ chọn 25%: Phim gốc dài 80 phút sẽ được tóm tắt thành 20 phút Review chi tiết."
            )
            recap_ratio = recap_percent / 100.0
            recap_dur = None
        else:
            default_sec = 60 if is_votritv_mode else 900
            recap_dur = st.slider(
                "Thời lượng mong muốn (giây - tối đa 1800s = 30 phút):",
                min_value=20,
                max_value=1800,
                value=default_sec,
                step=10,
                help="Thời lượng tóm tắt cố định sau khi tổng hợp các cảnh highlight (900s = 15 phút, 1260s = 21 phút)."
            )
            recap_ratio = 0.40 if is_votritv_mode else 0.25
            st.caption(f"⏱️ Tương đương: **{recap_dur // 60} phút {recap_dur % 60} giây**")

    col_c1, col_c2 = st.columns([1.2, 1])

    with col_c1:
        if is_votritv_mode:
            style_options = [
                "🤪 Vô Tri TV / Hài Hước Châm Biếm (Chuẩn kênh @78votritv)",
                "😂 Dí Dỏm Bắt Trend / Tưng Tửng",
                "⚡ Nhịp Nhanh / TikTok Shorts Viral"
            ]
        else:
            style_options = [
                "🔥 Review Phim Chuyên Sâu (Chuẩn Kênh Não Động Review - Kể chuyện liền mạch & Thông điệp cuối phim)",
                "🎬 Review Phim Điện Ảnh / Kịch Tính & Lôi Cuốn",
                "🕵️ Trinh Thám / Giải Mã Âm Mưu & Nút Thắt Cao Trào",
                "😂 Review Hài Hước / Bắt Trend & Cà Khịa",
                "🏛️ Phân Tích Tư Liệu & Tâm Lý Nhân Vật Điềm Đạm",
                "⚡ Nhịp Nhanh / TikTok & YouTube Shorts Viral"
            ]
        style_choice = st.selectbox(
            "🎭 Phong cách kịch bản:",
            style_options,
            key="recap_style_select"
        )

    with col_c2:
        lang_filter_map = {
            "🇻🇳 Tiếng Việt (Vietnamese)": ("vi", "Tiếng Việt"),
            "🇺🇸 Tiếng Anh (English - US/UK)": ("en", "English"),
            "🇨🇳 Tiếng Trung (Chinese - Mandarin)": ("zh", "Chinese (Mandarin)"),
            "🇯🇵 Tiếng Nhật (Japanese)": ("ja", "Japanese"),
            "🇰🇷 Tiếng Hàn (Korean)": ("ko", "Korean"),
            "🇪🇸 Tiếng Tây Ban Nha (Spanish)": ("es", "Spanish"),
            "🇫🇷 Tiếng Pháp (French)": ("fr", "French"),
            "🇩🇪 Tiếng Đức (German)": ("de", "German"),
            "🇷🇺 Tiếng Nga (Russian)": ("ru", "Russian"),
            "🇹🇭 Tiếng Thái (Thai)": ("th", "Thai"),
            "🇮🇩 Tiếng Indonesia": ("id", "Indonesian"),
            "🌐 Tất Cả Ngôn Ngữ": ("all", "Tiếng Việt")
        }
        chosen_lang_label = st.selectbox("🌐 Ngôn Ngữ Kịch Bản:", list(lang_filter_map.keys()), index=0, key="recap_lang_select")
        lang_code, actual_lang_name = lang_filter_map[chosen_lang_label]

    is_naodong_selected = "Não Động Review" in style_choice

    # Cấu hình Giọng đọc: Kho Giọng AI Chuẩn Review Phim HOẶC Nhân Bản Giọng Từ Link YouTube Mẫu (OmniVoice)
    st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
    voice_mode_choice = st.radio(
        "🎙️ Chế độ Giọng Đọc Thuyết Minh:",
        [
            "🎙️ Kho Giọng Đọc AI Chuẩn Review Phim (Siêu tốc, Đa luồng)",
            "🧬 Nhân Bản Giọng Đọc Từ Link YouTube Mẫu / File Audio (OmniVoice Zero-Shot)"
        ],
        horizontal=True,
        key="recap_voice_engine_mode"
    )
    selected_voice_engine = "omnivoice" if "Nhân Bản" in voice_mode_choice else "capcut"

    all_voices = get_available_voices(lang_filter=lang_code)
    if not all_voices:
        all_voices = get_available_voices("all")

    # Ưu tiên sắp xếp các giọng chuẩn Review Phim (Nam Trầm, Nam Minh, Thanh Niên Tự Tin, Cô Gái Hoạt Ngôn, Review Phim) lên đầu
    priority_ids = [
        "multi_male_felipe_uranus_bigtts",  # Giọng Nam Trầm (Chuẩn Não Động Review)
        "vi-VN-NamMinhNeural",              # Nam Minh (Thuyết minh điềm đạm)
        "BV075_streaming",                  # Thanh Niên Tự Tin
        "BV074_streaming",                  # Cô Gái Hoạt Ngôn
        "multi_female_richgirl_uranus_bigtts",
        "multi_female_daqi_uranus_bigtts",
        "multi_female_xyf04auto_uranus_bigtts"
    ]
    def _voice_sort_key(v_item):
        vid = v_item.get("id", "")
        if vid in priority_ids:
            return (0, priority_ids.index(vid))
        return (1, v_item.get("name", ""))

    all_voices = sorted(all_voices, key=_voice_sort_key)
    voice_label_map = {}
    for v in all_voices:
        vid = v.get("id", "")
        disp = v.get("name", vid)
        if vid == "multi_male_felipe_uranus_bigtts":
            disp = "🔥 Giọng Nam Trầm (Chuẩn Não Động Review - Điềm Đạm & Sâu Sắc)"
        elif vid == "vi-VN-NamMinhNeural":
            disp = "🎙️ Nam Minh (Giọng Nam Thuyết Minh Điện Ảnh)"
        elif vid == "BV075_streaming":
            disp = "⚡ Thanh Niên Tự Tin (Giọng Nam Review Mạch Lạc)"
        elif vid == "BV074_streaming":
            disp = "🎬 Cô Gái Hoạt Ngôn (Giọng Nữ Review Phim Quốc Dân)"
        voice_label_map[disp] = v

    voice_names_list = list(voice_label_map.keys())
    default_voice_idx = 0

    col_v1, col_v2, col_v3 = st.columns([2.2, 0.6, 1.2])
    with col_v1:
        chosen_voice_name = st.selectbox(
            "🎙️ Chọn Giọng Đọc AI (Hoặc giọng dự phòng khi Nhân bản):",
            voice_names_list,
            index=default_voice_idx,
            key="recap_voice_select_rich"
        )
        chosen_voice_obj = voice_label_map[chosen_voice_name]
    with col_v2:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if st.button("🔊 Thử", key="btn_preview_recap_voice", use_container_width=True, help="Nghe thử giọng đọc đã chọn"):
            with st.spinner("..."):
                ok_p, p_path = get_or_create_voice_preview(chosen_voice_obj)
                if ok_p:
                    st.audio(p_path)
                else:
                    st.error(f"Lỗi: {p_path}")
    with col_v3:
        voice_speed_val = st.slider(
            "⏩ Tốc độ đọc thuyết minh:",
            min_value=0.90,
            max_value=1.30,
            value=1.05 if is_naodong_selected else 1.00,
            step=0.05,
            format="%.2fx",
            key="recap_voice_speed_slider",
            help="Tăng nhẹ lên 1.05x - 1.15x giúp nhịp đọc cuốn hút, dứt khoát chuẩn các kênh Review Phim lớn."
        )

    # Nếu chọn Nhân Bản Giọng Từ Link YouTube Mẫu (OmniVoice)
    ref_audio_path_for_clone = st.session_state.get("recap_cloned_ref_wav", None)
    ref_start_s = 5.0
    ref_dur_s = 8.0
    if selected_voice_engine == "omnivoice":
        st.markdown('<div style="background: rgba(56,189,248,0.08); border: 1px solid rgba(56,189,248,0.25); border-radius: 10px; padding: 12px; margin-top: 8px;">', unsafe_allow_html=True)
        st.markdown("**🧬 Cấu Hình Nhân Bản Giọng Đọc Từ Video Mẫu (Ví dụ: Kênh Não Động Review)**")
        c_cl1, c_cl2, c_cl3 = st.columns([2.2, 0.9, 0.9])
        with c_cl1:
            clone_yt_url = st.text_input(
                "🔗 Link YouTube chứa giọng đọc mẫu muốn nhái theo:",
                value="https://youtu.be/Ue-1hlIagDE",
                key="recap_clone_yt_url"
            )
            clone_upload_file = st.file_uploader(
                "Hoặc tải file âm thanh/video giọng mẫu (.mp3, .wav, .mp4):",
                type=["mp3", "wav", "m4a", "mp4"],
                key="recap_clone_file_up"
            )
        with c_cl2:
            ref_start_s = st.number_input("Bắt đầu lấy mẫu (s):", min_value=0.0, max_value=600.0, value=5.0, step=1.0, key="recap_clone_st")
            ref_dur_s = st.number_input("Độ dài mẫu (4-12s):", min_value=4.0, max_value=12.0, value=8.0, step=1.0, key="recap_clone_dur")
        with c_cl3:
            st.markdown("<div style='height: 26px;'></div>", unsafe_allow_html=True)
            if st.button("📥 Trích Xuất Giọng Mẫu", use_container_width=True, key="btn_extract_clone_ref"):
                with st.spinner("Đang trích xuất & lọc sạch 24kHz đoạn giọng mẫu..."):
                    from utils.omnivoice_wrapper import prepare_clean_reference_wav
                    ref_work_dir = Path("output_voiceovers") / "recap_ref"
                    ref_work_dir.mkdir(parents=True, exist_ok=True)
                    src_media = None
                    if clone_upload_file:
                        tmp_f = ref_work_dir / clone_upload_file.name
                        with open(tmp_f, "wb") as f:
                            f.write(clone_upload_file.getbuffer())
                        src_media = str(tmp_f)
                    elif clone_yt_url.strip():
                        dl_r = download_video_from_url(clone_yt_url.strip(), ref_work_dir, audio_only=True)
                        if dl_r.get("success"):
                            src_media = dl_r["path"]
                        else:
                            st.error(f"Lỗi tải giọng mẫu: {dl_r.get('error')}")
                    if src_media:
                        ok_w, clean_w = prepare_clean_reference_wav(src_media, start_sec=ref_start_s, duration_sec=ref_dur_s)
                        if ok_w and Path(clean_w).exists():
                            st.session_state["recap_cloned_ref_wav"] = clean_w
                            ref_audio_path_for_clone = clean_w
                            st.success("✅ Đã trích xuất giọng mẫu thành công!")
        if ref_audio_path_for_clone and Path(ref_audio_path_for_clone).exists():
            st.audio(ref_audio_path_for_clone)
            st.caption("✅ Đoạn giọng mẫu này sẽ được OmniVoice dùng để nhân bản giọng thuyết minh (Yêu cầu chạy trên Colab GPU T4 đã cài `omnivoice`).")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<br><div class="card-title">🔍 3. Mật Độ Phân Cảnh, Cấu Trúc Đầu-Cuối & Phụ Đề Phim Gốc</div>', unsafe_allow_html=True)
    c_seg1, c_seg2 = st.columns(2)
    with c_seg1:
        seg_density_mode = st.radio(
            "Chế độ phân bổ phân cảnh:",
            [
                "🚀 Tự động tối ưu theo thời lượng (Khuyên dùng cho Review 15-22 phút)",
                "🔥 Chi tiết đầy đủ (35 - 55 cảnh Highlight)",
                "🎬 Đại Review Phim Siêu Chi Tiết (70 - 130 cảnh, chia 4-8 Hồi cho phim dài)",
                "🎯 Tùy chọn số lượng cảnh cụ thể (10 - 160 cảnh)"
            ],
            index=0,
            key="recap_seg_density_mode"
        )
    with c_seg2:
        if "Tùy chọn" in seg_density_mode:
            chosen_custom_segments = st.slider(
                "Số lượng phân cảnh chi tiết mong muốn:",
                min_value=10,
                max_value=160,
                value=85,
                step=5,
                help="Chia nhỏ video thành nhiều phân cảnh để bắt trọn từng tình tiết."
            )
        elif "Đại Review" in seg_density_mode:
            st.info("🎬 **Đại Review Phim Siêu Chi Tiết**: Tự động chia phim dài 1.5 - 3 tiếng thành 5–8 Hồi (95 phân cảnh) để kể trọn vẹn cốt truyện từ đầu đến cuối như kênh Não Động Review.")
            chosen_custom_segments = 95
        elif "Chi tiết đầy đủ" in seg_density_mode:
            st.info("💡 **Chi tiết đầy đủ**: Phân bổ khoảng 45 phân cảnh chọn lọc trải đều toàn bộ video.")
            chosen_custom_segments = 45
        else:
            st.info("💡 **Tự động tối ưu**: Hệ thống tự động tính số cảnh chuẩn xác (khoảng 5–6 cảnh / mỗi phút video xuất ra).")
            chosen_custom_segments = None

        c_hk1, c_hk2 = st.columns(2)
        with c_hk1:
            use_cold_open = st.checkbox(
                "🔥 Mở đầu Cold Open giật gân",
                value=True,
                key="recap_cold_open_chk",
                help="Mở màn trực diện vào cảnh căng thẳng/bí ẩn nhất thay vì giới thiệu dài dòng (Chuẩn Não Động Review)."
            )
        with c_hk2:
            use_moral_outro = st.checkbox(
                "🌟 Đúc kết Thông điệp cuối phim",
                value=True,
                key="recap_moral_outro_chk",
                help="Tự động viết đoạn bình luận chiều sâu & bài học cảnh giác ở cuối video (Đặc sản Não Động Review)."
            )

    st.markdown('<br><div class="card-title">🎭 4. Thông Tin Tác Phẩm & File Phụ Đề Gốc (Giúp AI Gọi Đúng 100% Tên Nhân Vật)</div>', unsafe_allow_html=True)
    c_m1, c_m2, c_m3 = st.columns([1, 1, 1])
    with c_m1:
        movie_title = st.text_input(
            "🎥 Tên Phim / Tác Phẩm (nếu có):",
            placeholder="Ví dụ: No More Bets (Được Ăn Cả Ngã Về Không)...",
            help="Cung cấp tên phim giúp AI truy xuất đúng tên nhân vật và bối cảnh điện ảnh.",
            key="recap_movie_title_input"
        )
    with c_m2:
        character_hints = st.text_input(
            "👥 Tên Các Nhân Vật Chính (nếu có):",
            placeholder="Ví dụ: Pan Sheng (lập trình viên), Anna (người mẫu), Lục Bỉnh Khôn...",
            help="Giúp AI gọi đúng tên riêng nhân vật xuyên suốt kịch bản thuyết minh.",
            key="recap_character_hints_input"
        )
    with c_m3:
        uploaded_srt_file = st.file_uploader(
            "📄 File Phụ Đề Phim Gốc (.SRT / .VTT - Tùy chọn):",
            type=["srt", "vtt", "txt"],
            help="Nếu có file sub của phim, AI sẽ đọc toàn bộ lời thoại gốc để nắm chính xác 100% tình tiết và tên nhân vật!",
            key="recap_srt_ref_uploader"
        )

    # Nút bấm Phân tích & Tạo Kịch Bản
    if st.button("🤖 Bước 1: Phân Tích Phim Đa Hồi & Viết Kịch Bản Chuẩn 'Não Động Review'", use_container_width=True, type="primary"):
        if input_mode.startswith("📂") and not uploaded_video:
            st.warning("Vui lòng tải lên file video trước!")
            return
        elif input_mode.startswith("🔗") and not url_to_process.strip():
            st.warning("Vui lòng nhập link video!")
            return

        out_work_dir = Path("output_clips") / f"recap_{int(time.time())}"
        out_work_dir.mkdir(parents=True, exist_ok=True)
        status_box = st.empty()
        progress_bar = st.progress(0)

        def progress_cb(pct, msg):
            progress_bar.progress(min(100, max(0, int(pct))))
            status_box.info(msg)

        try:
            target_video_path = None
            if input_mode.startswith("📂"):
                progress_cb(5, "⏳ Đang nạp video tải lên...")
                target_video_path = out_work_dir / uploaded_video.name
                with open(target_video_path, "wb") as f:
                    f.write(uploaded_video.getbuffer())
            else:
                progress_cb(5, "⏳ Đang tải video từ đường link...")
                dl_res = download_video_from_url(url_to_process, out_work_dir, status_box)
                if not dl_res["success"]:
                    st.error(f"❌ Lỗi tải video: {dl_res.get('error')}")
                    return
                target_video_path = Path(dl_res["path"])

            # Đọc nội dung file phụ đề .srt/.vtt nếu người dùng tải lên
            srt_content_str = ""
            if uploaded_srt_file:
                try:
                    srt_content_str = uploaded_srt_file.getvalue().decode("utf-8", errors="ignore")
                except Exception:
                    srt_content_str = ""

            st.session_state["recap_video_path"] = str(target_video_path)

            active_recap_mode = "votritv_comedy" if is_votritv_mode else ("naodong_review" if is_naodong_selected else "movie_recap")

            # Gọi phân tích Recap Đa Hồi
            analysis_res = recap_builder.analyze_and_generate_recap(
                video_path=target_video_path,
                target_duration_sec=float(recap_dur) if recap_dur else None,
                target_ratio=float(recap_ratio),
                target_lang_name=actual_lang_name,
                style=style_choice,
                movie_title=movie_title.strip(),
                character_hints=character_hints.strip(),
                model_name=selected_model,
                api_key=api_key,
                custom_num_segments=chosen_custom_segments,
                recap_mode=active_recap_mode,
                srt_text=srt_content_str,
                include_cold_open_hook=use_cold_open,
                include_deep_moral_outro=use_moral_outro,
                progress_callback=progress_cb
            )

            progress_bar.empty()
            status_box.empty()

            if analysis_res["success"]:
                st.success(f"🎉 Đã phân tích thành công {len(analysis_res['segments'])} phân cảnh và viết kịch bản thuyết minh liền mạch khớp hình ảnh!")
                st.session_state["recap_analysis_result"] = analysis_res
                st.session_state["recap_temp_dir"] = str(out_work_dir)
            else:
                st.error(f"❌ Thất bại: {analysis_res.get('error')}")

        except Exception as e:
            st.error(f"Lỗi: {str(e)}")

    if st.session_state.get("recap_analysis_result"):
        if st.button("🔄 Nhập / Phân Tích Lại Video Khác", key="btn_reset_recap"):
            st.session_state.pop("recap_analysis_result", None)
            st.session_state.pop("recap_video_path", None)
            st.session_state.pop("recap_final_video", None)
            st.session_state.pop("recap_final_script", None)
            st.session_state.pop("recap_final_srt", None)
            st.session_state.pop("recap_final_audio", None)
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

    # BƯỚC 2: Hiển thị danh sách phân cảnh với Thumbnail trực quan, kịch bản thuyết minh và xuất video
    if st.session_state.get("recap_analysis_result"):
        res = st.session_state["recap_analysis_result"]
        segments = res["segments"]
        total_words_est = sum(len(s.get("script", "").split()) for s in segments)
        est_duration_min = round((total_words_est / 3.15) / 60.0, 1)

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(
            f'<div class="card-title">📝 Danh Sách {len(segments)} Phân Cảnh & Kịch Bản (~{total_words_est} từ ≈ {est_duration_min} phút thuyết minh)</div>',
            unsafe_allow_html=True
        )
        st.caption("💡 Bạn có thể kiểm tra hình ảnh đại diện từng cảnh, nghe thử giọng đọc và chỉnh sửa lời bình trước khi xuất video Master.")

        with st.expander(f"👁️ Xem & Chỉnh Sửa Chi Tiết {len(segments)} Phân Cảnh (Bấm để mở rộng/thu gọn)", expanded=(len(segments) <= 30)):
            for i, seg in enumerate(segments):
                c_col1, c_col2, c_col3 = st.columns([1.2, 3.2, 0.9])
                
                with c_col1:
                    st.markdown(f"**Phân cảnh #{seg['index']}**")
                    thumb_p = seg.get("thumb_path")
                    if thumb_p and Path(thumb_p).exists():
                        st.image(thumb_p, use_container_width=True)
                    
                    c_st, c_en = st.columns(2)
                    with c_st:
                        seg["start_sec"] = st.number_input(f"Bắt đầu (s) #{seg['index']}", value=float(seg["start_sec"]), step=0.5, key=f"recap_seg_st_{i}")
                    with c_en:
                        seg["end_sec"] = st.number_input(f"Kết thúc (s) #{seg['index']}", value=float(seg["end_sec"]), step=0.5, key=f"recap_seg_en_{i}")
                    
                    seg["duration"] = round(max(1.0, seg["end_sec"] - seg["start_sec"]), 2)

                with c_col2:
                    if seg.get("visual_action"):
                        st.markdown(f"<span style='font-size:0.8rem; color:#38bdf8;'>👁️ <b>Hình ảnh:</b> {seg['visual_action']}</span>", unsafe_allow_html=True)
                    
                    seg["script"] = st.text_area(
                        f"Lời thoại #{seg['index']} ({seg['title']}):",
                        value=seg["script"],
                        key=f"recap_seg_script_{i}",
                        height=75
                    )

                with c_col3:
                    st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True)
                    if st.button("🔊 Nghe thử", key=f"btn_preview_seg_{i}", help=f"Nghe thử giọng đọc câu #{seg['index']}"):
                        with st.spinner("..."):
                            t_mp3 = Path(tempfile.gettempdir()) / f"recap_prev_seg_{i}.mp3"
                            ok_t, _ = generate_tts(
                                text=seg["script"],
                                voice_type=chosen_voice_obj.get("id", "BV074_streaming"),
                                resource_id=chosen_voice_obj.get("resource_id", "7102355709945188865"),
                                output_path=str(t_mp3)
                            )
                            if ok_t and t_mp3.exists():
                                st.audio(str(t_mp3))
                            else:
                                st.error("Lỗi tạo giọng")

                st.markdown("<hr style='border-color: rgba(255,255,255,0.06); margin: 10px 0;'>", unsafe_allow_html=True)

        st.markdown("<hr style='border-color: rgba(34,211,238,0.2); margin: 20px 0;'>", unsafe_allow_html=True)
        st.markdown('<div class="card-title">🛡️ 5. Bộ Lọc Lách Bản Quyền & Giao Diện Chuẩn Kênh "Não Động Review"</div>', unsafe_allow_html=True)

        c_bp1, c_bp2, c_bp3 = st.columns(3)
        with c_bp1:
            mirror_flip_chk = st.checkbox(
                "🔄 Lật Ngang Khung Hình (Mirror Flip)",
                value=True if not is_votritv_mode else False,
                key="recap_mirror_flip_chk",
                help="Lật ngược khung hình trái-phải như video mẫu của Não Động Review để vượt qua quét bản quyền hình ảnh Content ID."
            )
            cinematic_letterbox_chk = st.checkbox(
                "🎬 Đóng Viền Đen Điện Ảnh 2.35:1 (Letterbox)",
                value=True if not is_votritv_mode else False,
                key="recap_letterbox_chk",
                help="Tạo 2 dải viền đen điện ảnh ở trên và dưới khung hình giống hệt giao diện kênh Não Động Review."
            )
        with c_bp2:
            crop_sub_pct_val = st.slider(
                "✂️ Cắt bỏ phụ đề cứng ở đáy phim gốc (%):",
                min_value=0,
                max_value=16,
                value=8 if not is_votritv_mode else 0,
                step=1,
                format="%d%%",
                key="recap_crop_sub_slider",
                help="Phóng nhẹ và cắt bỏ phần đáy chứa hardsub tiếng Trung/Anh của phim gốc (Khuyên dùng: 8%)."
            )
            color_enhance_chk = st.checkbox(
                "🎨 Chỉnh Màu Điện Ảnh & Khử Mờ Lanczos",
                value=True,
                key="recap_color_enhance_chk",
                help="Tăng nhẹ độ tương phản, độ nét và biến đổi ma trận màu vi mô chống quét bản quyền."
            )
        with c_bp3:
            logo_watermark_file = st.file_uploader(
                "🏷️ Tải Logo / Avatar Kênh (Đóng dấu tròn góc Trái-Trên):",
                type=["png", "jpg", "jpeg", "webp"],
                key="recap_logo_uploader",
                help="Tự động bo tròn thành Huy Hiệu Kênh có viền gắn ở góc trên bên trái giống hệt logo kênh Não Động Review!"
            )
            custom_bgm_file = st.file_uploader(
                "🎵 Nhạc Nền BGM Kịch Tính (.MP3/.WAV - Tùy chọn):",
                type=["mp3", "wav", "m4a"],
                key="recap_bgm_uploader",
                help="Tải lên nhạc nền hồi hộp/điện ảnh để tự động hòa âm dưới giọng đọc thuyết minh."
            )

        st.markdown("<hr style='border-color: rgba(255,255,255,0.08); margin: 16px 0;'>", unsafe_allow_html=True)
        st.markdown('<div class="card-title">🎛️ 6. Đồng Bộ Khung Hình, Âm Lượng & Xuất Video Master</div>', unsafe_allow_html=True)

        col_sync1, col_sync2 = st.columns(2)
        with col_sync1:
            sync_mode_choice = st.selectbox(
                "🎯 Chế độ đồng bộ Video & Lời đọc:",
                [
                    "🎯 Khớp Chuyển Động Trực Quan (Smart Motion - Thoại liên tục, co giãn vi mô vừa khít 100% câu nói)",
                    "✂️ Cắt Tự Nhiên Theo Lời Đọc (Voice-Paced Cut - Thoại liên tục 1.0x tốc độ gốc + 0.25s đệm)",
                    "⏳ Giữ Nguyên Độ Dài Cảnh Gốc (Có khoảng nghỉ giữa các câu thoại)"
                ],
                key="recap_sync_mode_select"
            )
            if "Cắt Tự Nhiên" in sync_mode_choice:
                selected_sync_mode = "voice_paced"
            elif "Giữ Nguyên" in sync_mode_choice:
                selected_sync_mode = "keep_original"
            else:
                selected_sync_mode = "smart_motion"

        with col_sync2:
            burn_sub = st.checkbox(
                "💬 Chèn Phụ Đề Vàng Viền Đen Lên Video (Tắt để khung hình sạch đẹp chuẩn Não Động Review)",
                value=True if is_votritv_mode else False,
                key="recap_burn_sub_checkbox",
                help="Kênh Não Động Review thường để khung hình sạch và xuất file phụ đề .SRT riêng để bật CC trên YouTube."
            )

        col_act1, col_act2 = st.columns(2)
        with col_act1:
            aspect_choice = st.selectbox(
                "📐 Định dạng khung hình xuất bản:",
                [
                    "🎬 16:9 Ngang Chuẩn Điện Ảnh (YouTube / Facebook)",
                    "📱 9:16 Dọc Toàn Màn Hình (TikTok / Reels / Shorts)"
                ],
                key="recap_aspect_select"
            )
            aspect_ratio = "9:16" if "9:16" in aspect_choice else "16:9"

        with col_act2:
            mac_projects = get_mac_capcut_projects()
            selected_draft = None
            if mac_projects:
                draft_names = [f"🎬 {p.get('name', 'Dự án')}" for p in mac_projects]
                chosen_idx = st.selectbox("📂 Chọn Dự án CapCut muốn bơm vào (Tùy chọn):", range(len(draft_names)), format_func=lambda i: draft_names[i], key="recap_capcut_select")
                selected_draft = mac_projects[chosen_idx]["path"]

        col_vol1, col_vol2 = st.columns(2)
        with col_vol1:
            bgm_vol = st.slider("🔉 Âm lượng tiếng phim gốc / Nhạc nền:", min_value=0, max_value=50, value=10, format="%d%%", key="recap_bgm_vol_slider") / 100.0
        with col_vol2:
            voice_vol = st.slider(f"🔊 Âm lượng giọng thuyết minh AI:", min_value=80, max_value=250, value=165, format="%d%%", key="recap_voice_vol_slider") / 100.0

        if st.button("✨ Bước 2: Tiến Hành Cắt Cảnh, Lách Bản Quyền, Lồng Tiếng & Xuất Video Review Phim", use_container_width=True, type="primary"):
            st.session_state.pop("recap_final_video", None)
            st.session_state.pop("recap_final_script", None)
            st.session_state.pop("recap_final_srt", None)
            st.session_state.pop("recap_final_audio", None)
            video_path = Path(st.session_state["recap_video_path"])
            if not video_path.exists():
                st.error("Không tìm thấy file video nguồn. Vui lòng thực hiện lại từ Bước 1.")
                return

            # Đồng bộ lại chính xác tuyệt đối start_sec và end_sec từ các trường nhập liệu
            for s in segments:
                st_s = float(s.get("start_sec", 0.0))
                et_s = float(s.get("end_sec", st_s + 4.0))
                if et_s <= st_s:
                    et_s = st_s + 4.0
                s["start_sec"] = round(st_s, 2)
                s["end_sec"] = round(et_s, 2)
                s["start_time"] = recap_builder.format_seconds_to_mmss(st_s)
                s["end_time"] = recap_builder.format_seconds_to_mmss(et_s)
                s["duration"] = round(et_s - st_s, 2)

            out_temp_dir = Path("output_clips") / f"recap_render_{int(time.time())}"
            out_temp_dir.mkdir(parents=True, exist_ok=True)
            status_box2 = st.empty()
            pbar2 = st.progress(0)

            def pcb2(pct, msg):
                pbar2.progress(min(100, max(0, int(pct))))
                status_box2.info(msg)

            try:
                saved_logo_path = None
                if logo_watermark_file:
                    saved_logo_path = out_temp_dir / f"logo_{logo_watermark_file.name}"
                    with open(saved_logo_path, "wb") as lf:
                        lf.write(logo_watermark_file.getbuffer())

                saved_bgm_path = None
                if custom_bgm_file:
                    saved_bgm_path = out_temp_dir / f"bgm_{custom_bgm_file.name}"
                    with open(saved_bgm_path, "wb") as bf:
                        bf.write(custom_bgm_file.getbuffer())

                final_video_path = out_temp_dir / f"Review_Phim_{int(time.time())}.mp4"
                active_recap_mode = "votritv_comedy" if is_votritv_mode else ("naodong_review" if is_naodong_selected else "movie_recap")

                build_ok, res_path_or_err, broll_items, merged_audio_path = recap_builder.render_synced_recap_pipeline(
                    video_path=video_path,
                    segments=segments,
                    voice_info=chosen_voice_obj,
                    output_video_path=final_video_path,
                    aspect_ratio=aspect_ratio,
                    bgm_volume=bgm_vol,
                    voice_volume=voice_vol,
                    sync_mode=selected_sync_mode,
                    burn_subtitles=burn_sub,
                    recap_mode=active_recap_mode,
                    custom_bgm_path=str(saved_bgm_path) if saved_bgm_path else None,
                    mirror_flip=mirror_flip_chk,
                    cinematic_letterbox=cinematic_letterbox_chk,
                    crop_bottom_sub_pct=crop_sub_pct_val / 100.0,
                    color_enhance=color_enhance_chk,
                    logo_watermark_path=str(saved_logo_path) if saved_logo_path else None,
                    voice_speed=voice_speed_val,
                    voice_engine=selected_voice_engine,
                    ref_audio_path=ref_audio_path_for_clone,
                    ref_start_sec=ref_start_s,
                    ref_duration_sec=ref_dur_s,
                    progress_callback=pcb2
                )

                # Bơm vào CapCut Draft nếu được chọn
                if build_ok and selected_draft and broll_items:
                    pcb2(95, "✂️ Đang tự động bơm các clip highlight và giọng đọc vào CapCut Draft...")
                    inject_broll_sequence_and_audio_to_draft(
                        draft_json_path=selected_draft,
                        video_clips_list=broll_items,
                        audio_path=merged_audio_path
                    )

                pbar2.progress(100)
                status_box2.empty()

                if build_ok and final_video_path.exists():
                    st.success("🎉 Video Review Phim đã được dựng hoàn tất và đồng bộ khớp 100% từng phân cảnh!")
                    st.session_state["recap_final_video"] = str(final_video_path)
                    full_script = "\n\n".join([f"{s['script']}" for s in segments if s.get('script')])
                    st.session_state["recap_final_script"] = full_script
                    srt_cand = final_video_path.with_suffix(".srt")
                    if srt_cand.exists():
                        st.session_state["recap_final_srt"] = str(srt_cand)
                    if merged_audio_path and Path(merged_audio_path).exists():
                        saved_voice_mp3 = out_temp_dir / f"Voiceover_{int(time.time())}.mp3"
                        shutil.copy2(merged_audio_path, saved_voice_mp3)
                        st.session_state["recap_final_audio"] = str(saved_voice_mp3)
                else:
                    st.error(f"Không thể hoàn tất quá trình dựng video Recap: {res_path_or_err}")

            except Exception as e:
                st.error(f"Lỗi: {str(e)}")

        st.markdown('</div>', unsafe_allow_html=True)

    # Hiển thị kết quả video đã hoàn thành
    if st.session_state.get("recap_final_video"):
        final_v_path = Path(st.session_state["recap_final_video"])
        if final_v_path.exists():
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="card-title">🎬 7. Xem Trước & Tải Về Trọn Bộ Video Review Phim (.MP4 + .SRT + .MP3 + .TXT)</div>', unsafe_allow_html=True)

            file_size_mb = final_v_path.stat().st_size / (1024 * 1024)
            full_script_txt = st.session_state.get("recap_final_script", "")
            final_srt_path = st.session_state.get("recap_final_srt", "")
            final_audio_path = st.session_state.get("recap_final_audio", "")

            c_v1, c_v2 = st.columns([3, 2])
            with c_v1:
                st.video(str(final_v_path))

                st.markdown("<div style='margin-top: 12px;'></div>", unsafe_allow_html=True)
                with open(final_v_path, "rb") as vf:
                    video_bytes = vf.read()

                st.download_button(
                    label=f"📥 TẢI VIDEO REVIEW PHIM 1080P (.MP4 - {file_size_mb:.1f} MB)",
                    data=video_bytes,
                    file_name=f"Review_Phim_1080p_{int(time.time())}.mp4",
                    mime="video/mp4",
                    use_container_width=True,
                    type="primary",
                    key="btn_download_recap_main"
                )

                col_dl1, col_dl2 = st.columns(2)
                with col_dl1:
                    if final_srt_path and Path(final_srt_path).exists():
                        with open(final_srt_path, "rb") as sf:
                            srt_bytes = sf.read()
                        st.download_button(
                            label="💬 Tải Phụ Đề YouTube CC (.SRT)",
                            data=srt_bytes,
                            file_name=f"Phu_De_Review_{int(time.time())}.srt",
                            mime="text/plain",
                            use_container_width=True,
                            key="btn_download_recap_srt"
                        )
                with col_dl2:
                    if final_audio_path and Path(final_audio_path).exists():
                        with open(final_audio_path, "rb") as af:
                            aud_bytes = af.read()
                        st.download_button(
                            label="🎙️ Tải File Giọng Đọc (.MP3)",
                            data=aud_bytes,
                            file_name=f"Giong_Doc_Review_{int(time.time())}.mp3",
                            mime="audio/mpeg",
                            use_container_width=True,
                            key="btn_download_recap_audio"
                        )

                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    if st.button("📂 Mở Trong Finder (Máy Mac)", use_container_width=True, key="btn_open_recap_finder"):
                        import sys, subprocess
                        try:
                            if sys.platform == "darwin":
                                subprocess.run(["open", "-R", str(final_v_path)])
                            elif sys.platform == "win32":
                                subprocess.run(["explorer", f"/select,{str(final_v_path)}"])
                            else:
                                subprocess.run(["xdg-open", str(final_v_path.parent)])
                            st.toast("📂 Đã mở thư mục chứa video trên máy!")
                        except Exception as e_f:
                            st.error(f"Không thể mở thư mục: {e_f}")

                with col_b2:
                    if st.button("💾 Lưu Sang Thư Mục Downloads", use_container_width=True, key="btn_copy_to_downloads"):
                        try:
                            downloads_dir = Path.home() / "Downloads"
                            if downloads_dir.exists():
                                dest_path = downloads_dir / f"Review_Phim_{int(time.time())}.mp4"
                                shutil.copy2(final_v_path, dest_path)
                                st.success(f"✅ Đã lưu vào: `{dest_path.name}` trong Downloads!")
                                st.toast("💾 Đã lưu thành công vào Downloads!")
                            else:
                                st.error("Không tìm thấy thư mục Downloads trên máy.")
                        except Exception as e_cp:
                            st.error(f"Lỗi sao chép: {e_cp}")

            with c_v2:
                st.markdown("### 📋 Kịch Bản Thuyết Minh Liền Mạch:")
                st.text_area("Nội dung kịch bản hoàn chỉnh:", value=full_script_txt, height=360, key="recap_full_script_preview_area")

                if full_script_txt:
                    st.download_button(
                        label="📄 Tải Kịch Bản Thuyết Minh (.TXT)",
                        data=full_script_txt,
                        file_name=f"Kich_Ban_Review_Phim_{int(time.time())}.txt",
                        mime="text/plain",
                        use_container_width=True,
                        key="btn_download_recap_script"
                    )

            st.markdown('</div>', unsafe_allow_html=True)
