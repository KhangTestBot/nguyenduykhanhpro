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
    <div class="hero-subtitle">Tự động bóc tách cảnh Highlight đắt giá & Thuyết minh Review Phim / Tóm tắt điện ảnh khớp 100% từng khung hình</div>
    <div class="badge-row">
    <span class="badge">🤖 Gemini Visual Grounding</span>
    <span class="badge">🎭 Phân Hồi Timeline Acts</span>
    <span class="badge">🎯 Khớp Lời & Hình Ảnh 100%</span>
    <span class="badge">🎙️ Giọng Thuyết Minh Chuẩn Điện Ảnh</span>
    <span class="badge">🚀 Bơm Thẳng Vào CapCut Draft</span>
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
    st.markdown('<div class="card-title">📥 1. Nguồn Video Phim Gốc</div>', unsafe_allow_html=True)

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
            "Kéo thả video cần Recap vào đây (MP4, MOV, MKV, WebM):",
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
        st.caption("💡 Nếu tải từ link YouTube, hệ thống sẽ tự động tìm luồng nét nhất và khử mờ bằng thuật toán Unsharp Lanczos.")

    st.markdown('<br><div class="card-title">🎨 3. Cấu Hình Phong Cách, Ngôn Ngữ & Giọng Đọc</div>', unsafe_allow_html=True)
    
    col_dur1, col_dur2 = st.columns([1, 2])
    with col_dur1:
        dur_mode = st.radio(
            "Mục tiêu thời lượng:",
            ["📊 Theo % Video Gốc (Khuyên dùng)", "⏱️ Số giây cố định"],
            key="recap_dur_mode"
        )
    with col_dur2:
        if "Theo %" in dur_mode:
            default_pct = 40 if is_votritv_mode else 30
            recap_percent = st.slider(
                "Tỷ lệ tóm tắt (% thời lượng video gốc):",
                min_value=10,
                max_value=90,
                value=default_pct,
                step=5,
                format="%d%%",
                help="Ví dụ chọn 40%: Video gốc dài 10 phút sẽ được tuyển chọn thành 4 phút highlight các tiểu phẩm hay nhất."
            )
            recap_ratio = recap_percent / 100.0
            recap_dur = None
        else:
            default_sec = 60 if is_votritv_mode else 60
            recap_dur = st.slider(
                "Thời lượng mong muốn (giây):",
                min_value=20,
                max_value=600,
                value=default_sec,
                step=5,
                help="Thời lượng tóm tắt cố định sau khi tổng hợp các cảnh highlight."
            )
            recap_ratio = 0.40 if is_votritv_mode else 0.30

    col_c1, col_c2, col_c3 = st.columns([1, 1, 1.2])

    with col_c1:
        if is_votritv_mode:
            style_options = [
                "🤪 Vô Tri TV / Hài Hước Châm Biếm (Chuẩn kênh @78votritv)",
                "😂 Dí Dỏm Bắt Trend / Tưng Tửng",
                "⚡ Nhịp Nhanh / TikTok Shorts Viral"
            ]
        else:
            style_options = [
                "🎬 Review Phim / Kịch Tính & Lôi Cuốn",
                "🔥 Giật Gân / Nút Thắt & Cao Trào",
                "😂 Hài Hước / Bắt Trend & Dí Dỏm",
                "🏛️ Phân Tích Tư Liệu / Điềm Đạm",
                "⚡ Nhịp Nhanh / TikTok Shorts Viral"
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

    with col_c3:
        all_voices = get_available_voices(lang_filter=lang_code)
        if not all_voices:
            all_voices = get_available_voices("all")
        
        voice_label_map = {f"{v['name']}": v for v in all_voices}
        voice_names_list = list(voice_label_map.keys())

        # TỰ ĐỘNG CHỌN MẶC ĐỊNH CHO REVIEW PHIM: "Cô Gái Hoạt Ngôn" (BV074_streaming)
        default_voice_idx = 0
        for v_i, v_obj in enumerate(all_voices):
            if v_obj.get("id") == "BV074_streaming" or "Cô Gái Hoạt Ngôn" in v_obj.get("name", "") or "hoat ngon" in v_obj.get("name", "").lower():
                default_voice_idx = v_i
                break

        c_v_sel, c_v_prev = st.columns([3, 1])
        with c_v_sel:
            chosen_voice_name = st.selectbox(
                "🎙️ Giọng đọc AI (Mặc định: Cô Gái Hoạt Ngôn):",
                voice_names_list,
                index=default_voice_idx,
                key="recap_voice_select_rich"
            )
            chosen_voice_obj = voice_label_map[chosen_voice_name]
        with c_v_prev:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if st.button("🔊 Thử", key="btn_preview_recap_voice", help="Nghe thử giọng đọc đã chọn"):
                with st.spinner("Đang tải giọng mẫu..."):
                    ok_p, p_path = get_or_create_voice_preview(chosen_voice_obj)
                    if ok_p:
                        st.audio(p_path)
                    else:
                        st.error(f"Lỗi: {p_path}")

    st.markdown('<br><div class="card-title">🔍 3. Mật Độ Phân Cảnh & Phân Hồi Cốt Truyện</div>', unsafe_allow_html=True)
    c_seg1, c_seg2 = st.columns(2)
    with c_seg1:
        seg_density_mode = st.radio(
            "Chế độ phân bổ phân cảnh:",
            [
                "🚀 Tự động tối ưu (Theo thời lượng & độ dài video)",
                "🔥 Chi tiết đầy đủ (30 - 50 cảnh Highlight)",
                "🎬 Đại Recap Siêu Chi Tiết (60 - 120 cảnh, phân hồi cho phim dài 2-3 tiếng)",
                "🎯 Tùy chọn số lượng cảnh cụ thể (10 - 150 cảnh)"
            ],
            key="recap_seg_density_mode"
        )
    with c_seg2:
        if "Tùy chọn" in seg_density_mode:
            chosen_custom_segments = st.slider(
                "Số lượng phân cảnh chi tiết mong muốn:",
                min_value=10,
                max_value=150,
                value=70,
                step=5,
                help="Chia nhỏ video thành nhiều phân cảnh để bắt trọn từng tình tiết."
            )
        elif "Đại Recap" in seg_density_mode:
            st.info("🎬 **Đại Recap Siêu Chi Tiết**: Tự động chia video dài 2-3 tiếng thành 3–5 Hồi theo timeline (60–100 cảnh) để bắt trọn từng tình tiết.")
            chosen_custom_segments = 85
        elif "Chi tiết đầy đủ" in seg_density_mode:
            st.info("💡 **Chi tiết đầy đủ**: Phân bổ khoảng 30–50 phân cảnh chọn lọc trải đều toàn bộ video.")
            chosen_custom_segments = 40
        else:
            st.info("💡 **Tự động tối ưu**: Hệ thống tính toán số lượng phân cảnh phù hợp nhất dựa trên thời lượng video gốc.")
            chosen_custom_segments = None

    st.markdown('<br><div class="card-title">🎭 4. Thông Tin Tác Phẩm & Điểm Nhấn (Tùy Chọn)</div>', unsafe_allow_html=True)
    c_m1, c_m2 = st.columns(2)
    with c_m1:
        movie_title = st.text_input(
            "🎥 Tên Phim / Tác Phẩm (nếu có):",
            placeholder="Ví dụ: Interstellar, John Wick 4, Lật Mặt 7...",
            help="Cung cấp tên phim giúp AI truy xuất cốt truyện điện ảnh chính xác.",
            key="recap_movie_title_input"
        )
    with c_m2:
        character_hints = st.text_input(
            "👥 Tên Các Nhân Vật Chính (nếu có):",
            placeholder="Ví dụ: Cooper (phi hành gia), Murph (con gái)...",
            help="Giúp AI gọi đúng tên nhân vật trong kịch bản thuyết minh.",
            key="recap_character_hints_input"
        )

    # Nút bấm Phân tích & Tạo Kịch Bản
    if st.button("🤖 Bước 1: Phân Tích Highlight & Viết Kịch Bản Đồng Bộ Hình Ảnh", use_container_width=True, type="primary"):
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
            progress_bar.progress(pct)
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

            # Lưu đường dẫn video đang xử lý vào session state
            st.session_state["recap_video_path"] = str(target_video_path)

            # Gọi phân tích Recap
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
                recap_mode="votritv_comedy" if is_votritv_mode else "movie_recap",
                progress_callback=progress_cb
            )

            progress_bar.empty()
            status_box.empty()

            if analysis_res["success"]:
                st.success("🎉 Đã phân tích thành công các tiểu phẩm và kịch bản thuyết minh khớp hình ảnh!")
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
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

    # BƯỚC 2: Hiển thị danh sách phân cảnh với Thumbnail trực quan, kịch bản thuyết minh và xuất video
    if st.session_state.get("recap_analysis_result"):
        res = st.session_state["recap_analysis_result"]
        segments = res["segments"]

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(f'<div class="card-title">📝 Danh Sách {len(segments)} Phân Cảnh Highlight & Kịch Bản Thuyết Minh (Đã Neo Khung Hình Thực Tế)</div>', unsafe_allow_html=True)
        st.caption("💡 Bạn có thể kiểm tra hình ảnh đại diện, nghe thử giọng đọc từng câu và chỉnh sửa nội dung thoại/thời gian trước khi xuất video master.")

        for i, seg in enumerate(segments):
            c_col1, c_col2, c_col3 = st.columns([1.2, 3.2, 0.9])
            
            with c_col1:
                st.markdown(f"**Phân cảnh #{seg['index']}**")
                # Hiển thị Thumbnail nếu có
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
        st.markdown('<div class="card-title">🎛️ 3. Cân Bằng Âm Lượng, Khung Hình & Xuất Video Hoàn Chỉnh</div>', unsafe_allow_html=True)

        col_sync1, col_sync2 = st.columns(2)
        with col_sync1:
            sync_mode_choice = st.selectbox(
                "🎯 Chế độ đồng bộ Video & Lời đọc:",
                [
                    "🎯 Khớp Chuyển Động Trực Quan (Smart Motion - Thoại liên tục, co giãn vi mô vừa khít 100% câu nói)",
                    "✂️ Cắt Tự Nhiên Theo Lời Đọc (Voice-Paced Cut - Thoại liên tục 1.0x tốc độ gốc + 0.3s đệm chuyển cảnh)",
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
                "💬 Chèn Phụ Đề Chữ Vàng Viền Đen Nổi Bật (Chuẩn mẫu @78votritv / Review Phim)",
                value=True if is_votritv_mode else False,
                key="recap_burn_sub_checkbox",
                help="Tự động hiển thị phụ đề lớn, chữ vàng viền đen dày nổi bật đập vào mắt người xem."
            )

        col_act1, col_act2 = st.columns(2)
        with col_act1:
            aspect_choice = st.selectbox(
                "📐 Định dạng khung hình xuất bản:",
                [
                    "🎬 16:9 Ngang Chuẩn (YouTube / Facebook)",
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
            bgm_vol = st.slider("🔉 Âm lượng tiếng video gốc (Background / Âm thanh cảnh):", min_value=0, max_value=50, value=12, format="%d%%", key="recap_bgm_vol_slider") / 100.0
        with col_vol2:
            voice_vol = st.slider(f"🔊 Âm lượng giọng đọc AI ({chosen_voice_name}):", min_value=80, max_value=250, value=160, format="%d%%", key="recap_voice_vol_slider") / 100.0

        if st.button("✨ Tiến Hành Cắt Highlight, Lồng Tiếng & Dựng Video", use_container_width=True, type="primary"):
            st.session_state.pop("recap_final_video", None)
            st.session_state.pop("recap_final_script", None)
            video_path = Path(st.session_state["recap_video_path"])
            if not video_path.exists():
                st.error("Không tìm thấy file video nguồn. Vui lòng thực hiện lại từ Bước 1.")
                return

            # Đồng bộ lại chính xác tuyệt đối start_sec và end_sec từ các trường nhập liệu
            for s in segments:
                st_str = s.get("start_time", "00:00")
                et_str = s.get("end_time", "00:00")
                st_s = recap_builder.parse_time_to_seconds(st_str, default=s.get("start_sec", 0.0))
                et_s = recap_builder.parse_time_to_seconds(et_str, default=s.get("end_sec", st_s + 4.0))
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
                pbar2.progress(pct)
                status_box2.info(msg)

            try:
                final_video_path = out_temp_dir / f"Recap_{int(time.time())}.mp4"
                
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
                    recap_mode="votritv_comedy" if is_votritv_mode else "movie_recap",
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
                    st.success("🎉 Video Recap đã được dựng hoàn tất và đồng bộ khớp 100% từng phân cảnh!")
                    st.session_state["recap_final_video"] = str(final_video_path)
                    full_script = "\n\n".join([f"• Phân cảnh #{s['index']} ({s['title']}): {s['script']}" for s in segments if s.get('script')])
                    st.session_state["recap_final_script"] = full_script
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
            st.markdown('<div class="card-title">🎬 4. Xem Trước & Tải Về Video Recap</div>', unsafe_allow_html=True)

            file_size_mb = final_v_path.stat().st_size / (1024 * 1024)
            full_script_txt = st.session_state.get("recap_final_script", "")

            c_v1, c_v2 = st.columns([3, 2])
            with c_v1:
                st.video(str(final_v_path))

                # CÁC NÚT TẢI ĐẶT NGAY BÊN DƯỚI VIDEO ĐỂ DỄ BẤM NHẤT
                st.markdown("<div style='margin-top: 12px;'></div>", unsafe_allow_html=True)
                with open(final_v_path, "rb") as vf:
                    video_bytes = vf.read()

                st.download_button(
                    label=f"📥 TẢI VIDEO RECAP VỀ MÁY (.MP4 - {file_size_mb:.1f} MB)",
                    data=video_bytes,
                    file_name=f"Video_Recap_1080p_{int(time.time())}.mp4",
                    mime="video/mp4",
                    use_container_width=True,
                    type="primary",
                    key="btn_download_recap_main"
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
                        import shutil
                        try:
                            downloads_dir = Path.home() / "Downloads"
                            if downloads_dir.exists():
                                dest_path = downloads_dir / f"Video_Recap_{int(time.time())}.mp4"
                                shutil.copy2(final_v_path, dest_path)
                                st.success(f"✅ Đã lưu vào: `{dest_path.name}` trong Downloads!")
                                st.toast("💾 Đã lưu thành công vào Downloads!")
                            else:
                                st.error("Không tìm thấy thư mục Downloads trên máy.")
                        except Exception as e_cp:
                            st.error(f"Lỗi sao chép: {e_cp}")

            with c_v2:
                st.markdown("### 📋 Kịch Bản Thuyết Minh:")
                st.info(full_script_txt)

                if full_script_txt:
                    st.download_button(
                        label="📄 Tải Kịch Bản Thuyết Minh (.txt)",
                        data=full_script_txt,
                        file_name=f"Kich_Ban_Recap_{int(time.time())}.txt",
                        mime="text/plain",
                        use_container_width=True,
                        key="btn_download_recap_script"
                    )

            st.markdown('</div>', unsafe_allow_html=True)
