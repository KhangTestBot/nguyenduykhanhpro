"""
Feature module: AI Vô Tri TV Studio Pro (Chuẩn phong cách @78votritv).
Tự động bóc tách các clip hài hước, tai nạn, meme, những pha xử lý cồng kềnh từ video dài
và viết lời bình bẻ lái logic 180 độ (deadpan humor) khớp 100% từng khung hình,
lồng tiếng Thanh Niên Tự Tin, hòa âm nhạc nền BGM tưng tửng và canvas 9:16.
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

DEFAULT_PUNCHLINES = (
    "tội nghiệp quá, chiếc xe chắc chắn phải đem đi bảo dưỡng lại lòng tin. "
    "đúng là một phương pháp làm đẹp từ thiên nhiên vô cùng tốn xà phòng. "
    "10 điểm tự tin nhưng âm vô cùng điểm thực tế. "
    "nhờ sự giúp đỡ hết mình của người anh em tốt, chàng trai nhanh chóng hoàn thành toàn bộ quy trình. "
    "đúng là đàn ông đích thực chưa bao giờ chừa cho mình đường lui. "
    "nhanh đến mức mặt đất còn chưa kịp chuẩn bị tâm lý đón nhận. "
    "nếu đang nấu canh mà làm đổ muối xuống đất thì không còn nghi ngờ gì nữa nồi canh này chắc chắn phải nấu lại. "
    "quả nhiên không phải ai cũng thích đùa. "
    "hóa ra người làm bạn tổn thương nhất chưa bao giờ là đối thủ ngoài xã hội. "
    "đúng là một pha xử lý đi thẳng vào lòng đất."
)


def render_votri_tools():
    """Renders the dedicated AI Vô Tri TV Studio tab."""
    importlib.reload(recap_builder)

    if "gemini_api_key" not in st.session_state or not st.session_state["gemini_api_key"]:
        st.session_state["gemini_api_key"] = DEFAULT_GEMINI_KEY

    api_key = st.session_state.get("gemini_api_key", DEFAULT_GEMINI_KEY)

    st.markdown("""
    <div class="hero-banner">
    <div class="hero-title">🤪 Vô Tri TV Studio Pro (Chuẩn @78votritv)</div>
    <div class="hero-subtitle">Tự động biến video tổng hợp clip hài hước & meme thành video recap bẻ lái logic 180° triệu view TikTok</div>
    <div class="badge-row">
    <span class="badge">🤖 Gemini Visual Grounding</span>
    <span class="badge">🤪 Bẻ Lái Logic 180°</span>
    <span class="badge">🗿 Deadpan Humor</span>
    <span class="badge">🎙️ Giọng Thanh Niên Tự Tin (BV075)</span>
    <span class="badge">🎨 Khung Hình Sage Green 9:16</span>
    <span class="badge">🎵 Nhạc Nền Tưng Tửng BGM</span>
    <span class="badge">🚀 Bơm Thẳng Vào CapCut Draft</span>
    </div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("🔑 Cấu hình Gemini API Key & Model AI (Mặc định đã kết nối sẵn)", expanded=False):
        c_k1, c_k2 = st.columns([3, 2])
        with c_k1:
            key_input = st.text_area(
                "Gemini API Key(s) - Nhập 1 hoặc nhiều Key cách nhau bằng dấu phẩy:",
                value=api_key,
                placeholder="AIzaSy..., AIzaSy...",
                key="votri_api_key_input",
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
            chosen_model_label = st.selectbox("🤖 Chọn Model AI:", list(model_options.keys()), index=0, key="votri_model_select")
            selected_model = model_options[chosen_model_label]
            if selected_model == "custom":
                selected_model = st.text_input("Nhập Model ID:", value="models/gemini-flash-latest", key="votri_custom_model_input")
        st.success("✅ Đã kết nối sẵn Gemini API Key & hỗ trợ tự động Fallback / Chống giới hạn hạn mức!")

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">📂 1. Chọn Video Tuyển Tập Hài Hước / Meme Gốc</div>', unsafe_allow_html=True)

    input_mode = st.radio(
        "Nguồn Video:",
        ["📂 Tải File Video từ máy tính (.mp4, .mkv, .mov)", "🔗 Nhập Đường Link Video (TikTok / YouTube / Douyin)"],
        horizontal=True,
        key="votri_input_mode"
    )

    uploaded_video = None
    url_to_process = ""

    if input_mode.startswith("📂"):
        uploaded_video = st.file_uploader("Kéo thả file video compilation/meme dài vào đây:", type=["mp4", "mov", "mkv", "avi", "webm"], key="votri_file_uploader")
    else:
        c_u1, c_u2 = st.columns([4, 1])
        with c_u1:
            url_to_process = st.text_input("Dán link video:", placeholder="https://www.tiktok.com/... hoặc https://www.youtube.com/watch?v=...", key="votri_url_input")
        with c_u2:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if not YTDLP_AVAILABLE:
                st.caption("⚠️ Chưa cài yt-dlp.")

    st.markdown('<br><div class="card-title">🤪 2. Cấp Độ "Vô Tri" & Bẻ Lái Logic 180° (@78votritv)</div>', unsafe_allow_html=True)
    c_vt1, c_vt2 = st.columns(2)
    with c_vt1:
        votri_choice = st.selectbox(
            "🌀 Chọn Cấp Độ 'Vô Tri' / Phong Cách Bình Luận:",
            [
                "🤪 Siêu Cấp Vô Tri - Nói Lái Đi & Bẻ Lái 180° (Chuẩn 100% @78votritv triệu view)",
                "🗿 Nói Lái Đi - Giả Vờ Nghiêm Túc & Triết Lý Dở Hơi (Vật lý Newton, sinh học nhảm)",
                "🤝 Nói Lái Đi - Tình Anh Em Cảm Lạnh & Nghĩa Khí Vô Tri (Khen bạn đểu, nhiệt tình giúp hại)",
                "⚡ Nói Lái Đi - Hài Bựa Gen Z & Cà Khịa TikTok (Trend slang, kiếp nạn 82, 10 điểm...)"
            ],
            key="votri_choice_select"
        )
        if "Giả Vờ Nghiêm Túc" in votri_choice:
            votri_style_val = "fake_serious"
        elif "Tình Anh Em" in votri_choice:
            votri_style_val = "brotherhood"
        elif "Gen Z" in votri_choice:
            votri_style_val = "genz_bua"
        else:
            votri_style_val = "max_absurd"

        votri_theme = st.text_input(
            "🎥 Chủ đề video (Tùy chọn):",
            placeholder="Ví dụ: Những pha xử lý cồng kềnh, Tuyển tập vô tri thế giới...",
            key="votri_theme_input"
        )
    with c_vt2:
        votri_phrases_val = st.text_area(
            "💡 Gợi ý phong cách Punchlines / Câu chốt vô tri (Khớp 100% video):",
            value=DEFAULT_PUNCHLINES,
            height=135,
            help="AI sẽ quan sát hình ảnh cụ thể của từng clip để tự chọn hoặc sáng tạo ra câu chốt (punchline) hài hước phù hợp nhất với bối cảnh, tuyệt đối không dùng bừa bãi những từ không liên quan.",
            key="votri_phrases_area"
        )

    st.markdown('<br><div class="card-title">🎙️ 3. Giọng Đọc AI & Ngôn Ngữ</div>', unsafe_allow_html=True)
    c_lang, c_voice = st.columns([1, 2])
    with c_lang:
        lang_choice = st.selectbox(
            "🌐 Ngôn ngữ thuyết minh:",
            ["Tiếng Việt", "English (US)", "Tiếng Trung (Giản thể)", "Tiếng Nhật", "Tây Ban Nha"],
            index=0,
            key="votri_lang_choice"
        )
    with c_voice:
        all_voices = get_available_voices()
        voice_label_map = {}
        voice_names_list = []
        default_voice_idx = 0

        for idx, v in enumerate(all_voices):
            v_name = v.get("name", "Giọng AI")
            v_type = v.get("id", "")
            lbl = f"🎙️ {v_name} ({v_type})"
            voice_label_map[lbl] = v
            voice_names_list.append(lbl)
            # Mặc định luôn là BV075_streaming (Thanh Niên Tự Tin)
            if v_type == "BV075_streaming" or "Thanh Niên Tự Tin" in v_name or "tu tin" in v_name.lower():
                default_voice_idx = idx

        c_v_sel, c_v_prev = st.columns([3, 1])
        with c_v_sel:
            chosen_voice_name = st.selectbox(
                "🎙️ Giọng đọc AI (Mặc định chuẩn kênh @78votritv):",
                voice_names_list,
                index=default_voice_idx,
                key="votri_voice_select"
            )
            chosen_voice_obj = voice_label_map[chosen_voice_name]
        with c_v_prev:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if st.button("🔊 Thử", key="btn_preview_votri_voice", help="Nghe thử giọng đọc"):
                with st.spinner("Đang tải giọng mẫu..."):
                    ok_p, p_path = get_or_create_voice_preview(chosen_voice_obj)
                    if ok_p:
                        st.audio(p_path)
                    else:
                        st.error(f"Lỗi: {p_path}")

    st.markdown('<br><div class="card-title">🔍 4. Mật Độ & Số Lượng Tiểu Phẩm Hài Hước</div>', unsafe_allow_html=True)
    c_seg1, c_seg2 = st.columns(2)
    with c_seg1:
        seg_density_mode = st.radio(
            "Chế độ phân bổ phân cảnh:",
            [
                "🚀 Tự động bóc tách từng tình huống (Khuyên dùng)",
                "⚡ Nhanh gọn (6 - 12 tình huống ngắn)",
                "🔥 Đầy đủ trọn vẹn (15 - 30 tình huống)",
                "🎯 Tùy chọn số lượng cụ thể (5 - 80 tình huống)"
            ],
            key="votri_seg_density_mode"
        )
    with c_seg2:
        if "Tùy chọn" in seg_density_mode:
            chosen_custom_segments = st.slider(
                "Số lượng phân cảnh chi tiết mong muốn:",
                min_value=5, max_value=80, value=15, step=1,
                help="Bóc tách video thành số lượng tình huống hài cụ thể.",
                key="votri_custom_segments_slider"
            )
        elif "Đầy đủ" in seg_density_mode:
            st.info("🔥 **Đầy đủ trọn vẹn**: Bóc tách khoảng 15–25 tình huống trải đều toàn bộ video.")
            chosen_custom_segments = 20
        elif "Nhanh gọn" in seg_density_mode:
            st.info("⚡ **Nhanh gọn**: Tuyển chọn 8–12 tình huống hài đắt giá nhất.")
            chosen_custom_segments = 10
        else:
            st.info("💡 **Tự động bóc tách**: Gemini sẽ tự phát hiện ranh giới từng cú ngã, trò đùa hoặc pha xử lý cồng kềnh.")
            chosen_custom_segments = None

    # Nút bấm Phân tích & Tạo Kịch Bản
    if st.button("🤖 Bước 1: Bóc Tách Từng Clip Hài & Viết Bình Luận Bẻ Lái Vô Tri Khớp Hình", use_container_width=True, type="primary"):
        if input_mode.startswith("📂") and not uploaded_video:
            st.warning("Vui lòng tải lên file video trước!")
            return
        elif input_mode.startswith("🔗") and not url_to_process.strip():
            st.warning("Vui lòng nhập link video!")
            return

        out_work_dir = Path("output_clips") / f"votri_{int(time.time())}"
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

            st.session_state["votri_video_path"] = str(target_video_path)

            analysis_res = recap_builder.analyze_and_generate_recap(
                video_path=target_video_path,
                target_duration_sec=None,
                target_ratio=0.35,
                target_lang_name=lang_choice,
                style="🤪 Tuyển Tập Clip Hài Hước / Vô Tri TV",
                movie_title=votri_theme.strip(),
                character_hints="",
                model_name=selected_model,
                api_key=api_key,
                custom_num_segments=chosen_custom_segments,
                recap_mode="votritv_comedy",
                votri_style=votri_style_val,
                custom_catchphrases=votri_phrases_val,
                progress_callback=progress_cb
            )

            progress_bar.empty()
            status_box.empty()

            if analysis_res["success"]:
                st.success("🎉 Đã phân tích thành công từng tiểu phẩm hài và viết kịch bản bẻ lái vô tri 100% khớp hình ảnh!")
                st.session_state["votri_analysis_result"] = analysis_res
                st.session_state["votri_temp_dir"] = str(out_work_dir)
            else:
                st.error(f"❌ Thất bại: {analysis_res.get('error')}")

        except Exception as e:
            st.error(f"Lỗi: {str(e)}")

    if st.session_state.get("votri_analysis_result"):
        if st.button("🔄 Nhập / Phân Tích Lại Video Khác", key="btn_reset_votri"):
            st.session_state.pop("votri_analysis_result", None)
            st.session_state.pop("votri_final_video", None)
            st.session_state.pop("votri_final_script", None)
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

    # Hiển thị kịch bản và xem trước phân cảnh
    if st.session_state.get("votri_analysis_result"):
        res = st.session_state["votri_analysis_result"]
        segments = res.get("segments", [])

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(f'<div class="card-title">📝 2. Xem & Chỉnh Sửa Kịch Bản Bình Luận ({len(segments)} Tiểu Phẩm Hài)</div>', unsafe_allow_html=True)

        if st.button("🖼️ Trích Xuất Khung Hình Ảnh Thumbnail Cho Tất Cả Tiểu Phẩm", key="btn_votri_thumbs"):
            with st.spinner("Đang trích xuất ảnh thumbnail song song..."):
                t_dir = Path(st.session_state.get("votri_temp_dir", "output_clips")) / "thumbs"
                v_p = Path(st.session_state["votri_video_path"])
                segments = recap_builder.generate_segment_thumbnails(v_p, segments, t_dir)
                res["segments"] = segments
                st.session_state["votri_analysis_result"] = res
                st.rerun()

        for idx, seg in enumerate(segments):
            st_disp = seg.get("start_time") or recap_builder.format_seconds_to_mmss(seg.get("start_sec", 0.0))
            et_disp = seg.get("end_time")
            if not et_disp or et_disp == "00:00":
                et_disp = recap_builder.format_seconds_to_mmss(seg.get("end_sec", seg.get("start_sec", 0.0) + 4.0))

            with st.expander(f"Phân cảnh #{seg.get('index', idx+1)}: {seg.get('title', 'Tình huống hài')} [{st_disp} ➔ {et_disp}]", expanded=True if idx < 3 else False):
                col_t, col_s = st.columns([1, 3])
                with col_t:
                    thumb_p = seg.get("thumb_path", "")
                    if thumb_p and Path(thumb_p).exists():
                        st.image(thumb_p, use_container_width=True)
                    else:
                        st.markdown(f"<div style='background:#1b2030; height:100px; border-radius:6px; display:flex; align-items:center; justify-content:center; color:#9ca3af; font-size:0.8rem;'>{st_disp} ➔ {et_disp}</div>", unsafe_allow_html=True)
                    st.caption(f"👀 Hành động: {seg.get('visual_action', 'Hành động hài')}")
                with col_s:
                    seg["script"] = st.text_area(
                        f"Lời bình vô tri #{seg.get('index', idx+1)}:",
                        value=seg.get("script", ""),
                        key=f"votri_seg_script_{idx}",
                        height=85
                    )
                    c_t1, c_t2 = st.columns(2)
                    with c_t1:
                        seg["start_time"] = st.text_input(f"Bắt đầu:", value=st_disp, key=f"votri_st_{idx}")
                    with c_t2:
                        seg["end_time"] = st.text_input(f"Kết thúc:", value=et_disp, key=f"votri_et_{idx}")

        st.markdown('</div>', unsafe_allow_html=True)

        # Stage 3: Thiết lập Canvas 9:16, Nhạc Nền BGM & Dựng Video
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">🎨 3. Cài Đặt Khung Hình Vintage 9:16 & Nhạc Nền BGM (@78votritv)</div>', unsafe_allow_html=True)

        c_opt1, c_opt2 = st.columns(2)
        with c_opt1:
            aspect_ratio_choice = st.selectbox(
                "📐 Tỷ lệ khung hình xuất:",
                [
                    "9:16 Chuẩn Vô Tri TV (Khung nền màu Vintage)",
                    "9:16 Dọc Toàn Màn Hình (Fill/Crop dọc TikTok)",
                    "16:9 Ngang Chuẩn (YouTube/Facebook)"
                ],
                index=0,
                key="votri_aspect_ratio_select"
            )
            if "Chuẩn Vô Tri TV" in aspect_ratio_choice:
                aspect_ratio = "9:16_votritv"
            elif "Toàn Màn Hình" in aspect_ratio_choice:
                aspect_ratio = "9:16"
            else:
                aspect_ratio = "16:9"

        with c_opt2:
            burn_sub = st.checkbox("✍️ Đóng Cháy Phụ Đề Chữ Vàng Lên Video (Tắt mặc định)", value=False, key="votri_burn_sub")

        # Cài đặt Canvas Pastel
        color_preset = st.selectbox(
            "🎨 Màu nền Canvas Pastel:",
            [
                "🌿 Xanh Rêu Vintage (#94A48A - Chuẩn mẫu @78votritv)",
                "☕ Be Cổ Điển (#E2D9C8)",
                "🌑 Xám Khói Hiện Đại (#323842)",
                "🌸 Hồng Pastel (#E8D1D1)",
                "🛠️ Tùy chỉnh mã màu Hex"
            ],
            key="votri_canvas_preset"
        )
        if "Xanh Rêu" in color_preset:
            canvas_color = "0x94A48A"
        elif "Be Cổ Điển" in color_preset:
            canvas_color = "0xE2D9C8"
        elif "Xám Khói" in color_preset:
            canvas_color = "0x323842"
        elif "Hồng Pastel" in color_preset:
            canvas_color = "0xE8D1D1"
        else:
            custom_hex = st.text_input("Nhập mã màu Hex:", value="#94A48A", key="votri_custom_hex")
            canvas_color = custom_hex.replace("#", "0x")

        # Cài đặt Nhạc Nền Vô Tri & Âm lượng
        c_bgm1, c_bgm2 = st.columns([3, 2])
        with c_bgm1:
            use_votri_bgm = st.checkbox(
                "🎵 Chèn Nhạc Nền Vô Tri Hài Hước (@78votritv Goofy BGM)",
                value=True,
                help="Tự động hòa âm bản nhạc nền tưng tửng đặc trưng của kênh @78votritv với âm lượng nhẹ nhàng chạy xuyên suốt video."
            )
            votri_bgm_path = "assets/audio/votritv_funny_bgm.mp3" if use_votri_bgm else None
        with c_bgm2:
            bgm_vol = st.slider(
                "🎶 Âm lượng nhạc nền BGM:",
                min_value=5, max_value=40, value=18, format="%d%%",
                key="votri_bgm_vol_slider"
            ) / 100.0

        c_vvol1, c_sync = st.columns(2)
        with c_vvol1:
            voice_vol = st.slider(f"🔊 Âm lượng giọng đọc ({chosen_voice_name}):", min_value=80, max_value=250, value=160, format="%d%%", key="votri_voice_vol_slider") / 100.0
        with c_sync:
            selected_sync_mode = st.radio(
                "Cơ chế đồng bộ thời lượng:",
                [
                    "smart_motion",  # Smart Motion: Giữ nguyên tốc độ clip, lặp cảnh nếu cần
                    "voice_paced"    # Voice Paced: Khớp thời lượng video với giọng đọc
                ],
                format_func=lambda x: "✨ Smart Motion (Chuyển động mượt, thoại liên tục)" if x == "smart_motion" else "⚡ Voice Paced (Khớp chuẩn từng từ, thoại liên tục)",
                horizontal=True,
                key="votri_sync_mode"
            )

        # Tích hợp CapCut Draft
        mac_projects = get_mac_capcut_projects()
        selected_draft = None
        if mac_projects:
            draft_names = [f"🎬 {p.get('name', 'Dự án')}" for p in mac_projects]
            chosen_idx = st.selectbox("📂 Chọn Dự án CapCut muốn bơm vào (Tùy chọn):", range(len(draft_names)), format_func=lambda i: draft_names[i], key="votri_capcut_select")
            selected_draft = mac_projects[chosen_idx]["path"]

        if st.button("✨ Bắt Đầu Cắt Highlight, Lồng Tiếng & Dựng Video Vô Tri TV", use_container_width=True, type="primary"):
            st.session_state.pop("votri_final_video", None)
            st.session_state.pop("votri_final_script", None)
            video_path = Path(st.session_state["votri_video_path"])
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

            out_temp_dir = Path("output_clips") / f"votri_render_{int(time.time())}"
            out_temp_dir.mkdir(parents=True, exist_ok=True)
            status_box2 = st.empty()
            pbar2 = st.progress(0)

            def pcb2(pct, msg):
                pbar2.progress(pct)
                status_box2.info(msg)

            try:
                final_video_path = out_temp_dir / f"VotriTV_{int(time.time())}.mp4"

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
                    recap_mode="votritv_comedy",
                    canvas_color=canvas_color,
                    footer_text="",
                    custom_bgm_path=votri_bgm_path,
                    progress_callback=pcb2
                )

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
                    st.success("🎉 Video Vô Tri TV đã được dựng hoàn tất chuẩn phong cách @78votritv!")
                    st.session_state["votri_final_video"] = str(final_video_path)
                    full_script = "\n\n".join([f"• Phân cảnh #{s['index']} ({s['title']}): {s['script']}" for s in segments if s.get('script')])
                    st.session_state["votri_final_script"] = full_script
                else:
                    st.error(f"Không thể hoàn tất quá trình dựng video: {res_path_or_err}")

            except Exception as e:
                st.error(f"Lỗi: {str(e)}")

        st.markdown('</div>', unsafe_allow_html=True)

    # Xem trước & tải về
    if st.session_state.get("votri_final_video"):
        final_v_path = Path(st.session_state["votri_final_video"])
        if final_v_path.exists():
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="card-title">🎬 4. Xem Trước & Tải Về Video Vô Tri TV</div>', unsafe_allow_html=True)

            file_size_mb = final_v_path.stat().st_size / (1024 * 1024)
            full_script_txt = st.session_state.get("votri_final_script", "")

            c_v1, c_v2 = st.columns([3, 2])
            with c_v1:
                st.video(str(final_v_path))
                st.markdown("<div style='margin-top: 12px;'></div>", unsafe_allow_html=True)
                with open(final_v_path, "rb") as vf:
                    video_bytes = vf.read()

                st.download_button(
                    label=f"📥 TẢI VIDEO VÔ TRI TV VỀ MÁY (.MP4 - {file_size_mb:.1f} MB)",
                    data=video_bytes,
                    file_name=f"VotriTV_Recap_{int(time.time())}.mp4",
                    mime="video/mp4",
                    use_container_width=True,
                    type="primary"
                )

            with c_v2:
                st.text_area("📜 Kịch bản thuyết minh tổng hợp:", value=full_script_txt, height=320, key="votri_final_script_area")
                st.download_button(
                    label="📄 Tải Kịch Bản (.txt)",
                    data=full_script_txt,
                    file_name=f"VotriTV_Script_{int(time.time())}.txt",
                    mime="text/plain",
                    use_container_width=True
                )

            st.markdown('</div>', unsafe_allow_html=True)
