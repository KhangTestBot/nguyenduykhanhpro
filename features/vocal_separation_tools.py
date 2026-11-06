"""
Feature module: Vocal & Music Separation Studio Pro (Tách Giọng Nói, Bóc Tách BGM & Triệt Tiêu Nhạc Bản Quyền)
Tích hợp Động Cơ DSP Studio Siêu Tốc (File 5-6 tiếng) & AI UVR MDX-Net chuẩn CapCut Pro.
Hỗ trợ loại bỏ 100% bài hát/BGM bản quyền lồng trong video recap/kinh dị và xuất thẳng CapCut Mac Timeline.
"""

import os
import time
import shutil
from pathlib import Path
import streamlit as st
from utils.vocal_separator import separate_audio_ai, separate_audio_dsp, separate_video_with_audio_track
from utils.capcut_draft_editor import get_mac_capcut_projects, add_separated_audio_to_draft
from features.common_ui import download_video_from_url

def render_vocal_separation_tools():
    """Renders the 'Tách Giọng & Nhạc' feature tab."""
    st.markdown("""
    <div class="hero-banner">
        <div class="hero-title">🎙️ Tách Giọng Nói & Triệt Tiêu Nhạc Nền / Bài Hát (Vocal & BGM Studio Pro)</div>
        <div class="hero-subtitle">Bóc tách giọng nói, loại bỏ sạch các bài hát & BGM bản quyền lồng trong video hoặc bóc tách nhạc nền không lời chuẩn phòng thu.</div>
        <div class="badge-row">
            <span class="badge">🛡️ Khử 100% Nhạc Bản Quyền</span>
            <span class="badge">⚡ DSP Siêu Tốc &lt;30s (Hỗ trợ 5–6 tiếng)</span>
            <span class="badge">🧠 AI UVR MDX-Net Studio</span>
            <span class="badge">🎬 Ghép Video 1-Click</span>
            <span class="badge">✂️ Xuất Thẳng CapCut Mac</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 1. Chọn Nguồn Media Card
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">📂 1. Chọn Nguồn Video / Âm Thanh</div>', unsafe_allow_html=True)

    input_source_mode = st.radio(
        "Nguồn dữ liệu:",
        ["📁 Tải Lên File từ Máy (Video / Audio)", "🔗 Dán Link Trực Tiếp (Bilibili / YouTube / TikTok)", "🎬 Chọn Video Đã Tải Gần Đây"],
        horizontal=True,
        key="vocal_sep_source_mode"
    )

    selected_media_path = None
    media_display_title = ""

    if input_source_mode.startswith("📁"):
        uploaded_media = st.file_uploader(
            "Tải lên video hoặc audio cần xử lý:",
            type=["mp4", "mkv", "mov", "avi", "webm", "mp3", "wav", "m4a", "aac", "flac"],
            key="vocal_sep_file_uploader",
            help="Hỗ trợ file video hoặc audio dài nhiều tiếng."
        )
        if uploaded_media:
            temp_in_dir = Path("output_clips") / "temp_vocal_inputs"
            temp_in_dir.mkdir(parents=True, exist_ok=True)
            saved_in_file = temp_in_dir / uploaded_media.name
            if not saved_in_file.exists() or saved_in_file.stat().st_size != uploaded_media.size:
                with open(saved_in_file, "wb") as f:
                    f.write(uploaded_media.read())
            selected_media_path = saved_in_file
            media_display_title = uploaded_media.name
            st.info(f"✅ Đã tải file: **{uploaded_media.name}** ({round(uploaded_media.size / (1024*1024), 2)} MB)")

    elif input_source_mode.startswith("🔗"):
        url_input = st.text_input(
            "Dán link video:",
            placeholder="https://www.bilibili.com/video/BV... hoặc https://youtu.be/...",
            key="vocal_sep_url_input"
        )
        if url_input.strip():
            if st.button("📥 Tải Nhanh Video Từ Link Để Tách", key="btn_fetch_for_sep"):
                fetch_dir = Path("output_clips") / f"vocal_fetch_{int(time.time())}"
                fetch_dir.mkdir(parents=True, exist_ok=True)
                fetch_res = download_video_from_url(url_input.strip(), fetch_dir, st.empty())
                if fetch_res["success"]:
                    st.session_state["vocal_sep_fetched_path"] = fetch_res["path"]
                    st.session_state["vocal_sep_fetched_title"] = fetch_res["title"]
                    st.success(f"✅ Đã tải xong video: **{fetch_res['title']}**")
                else:
                    st.error(f"❌ Tải thất bại: {fetch_res.get('error', 'Lỗi không xác định')}")
        if "vocal_sep_fetched_path" in st.session_state and os.path.exists(st.session_state["vocal_sep_fetched_path"]):
            selected_media_path = Path(st.session_state["vocal_sep_fetched_path"])
            media_display_title = st.session_state.get("vocal_sep_fetched_title", selected_media_path.name)
            st.info(f"🎯 Đang chọn video: **{media_display_title}**")

    else:
        recent_clips_dir = Path("output_clips")
        recent_videos = []
        if recent_clips_dir.exists():
            for p in recent_clips_dir.glob("**/*"):
                if p.is_file() and p.suffix.lower() in [".mp4", ".mkv", ".mov", ".mp3", ".m4a"] and not p.name.endswith("_bgm.mp3") and not p.name.endswith("_vocals_only.mp3") and not p.name.endswith("_ai.mp3") and not p.name.endswith("_dsp.mp3"):
                    recent_videos.append(p)
        recent_videos.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        if recent_videos:
            opts = [str(p.relative_to(recent_clips_dir)) for p in recent_videos[:20]]
            chosen_rel = st.selectbox("Chọn video trong danh mục gần đây:", opts, key="vocal_sep_recent_select")
            selected_media_path = recent_clips_dir / chosen_rel
            media_display_title = selected_media_path.name
            st.info(f"🎯 Đang chọn file: **{media_display_title}** ({round(selected_media_path.stat().st_size / (1024*1024), 2)} MB)")
        else:
            st.warning("Chưa có video nào trong thư mục gần đây. Bạn có thể tải lên file từ máy hoặc dán link!")

    st.markdown("</div>", unsafe_allow_html=True)

    # 2. Cấu hình chế độ & Động cơ tách
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">⚙️ 2. Chọn Mục Tiêu Xử Lý & Động Cơ Bóc Tách</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        sep_mode_choice = st.radio(
            "🎯 Mục tiêu xử lý âm thanh:",
            [
                "💥 1. Chỉ Trích Xuất Tiếng Động SFX (Loại bỏ SẠCH 100% Nhạc Nền & Giọng Thoại / Lời Hát) — [Khuyên dùng cho Lồng Tiếng / Recap]",
                "🛡️ 2. Giữ Giọng Đọc / Thuyết Minh (Loại bỏ SẠCH 100% Bài Hát & BGM Bản Quyền) — [Khuyên dùng cho YouTube Recap/Kinh Dị]",
                "🎵 3. Tách Nhạc Nền BGM / Beat (Loại bỏ Giọng Hát Ca Sĩ & Lời Bài Hát) — [Khuyên dùng lấy nhạc nền / Karaoke]",
                "🎛️ 4. Tách Toàn Diện Tất Cả Track Riêng Biệt (Thoại | Tiếng Động SFX | Nhạc Nền)"
            ],
            index=0,
            key="vocal_sep_mode_radio"
        )
        if "1. Chỉ Trích Xuất Tiếng Động SFX" in sep_mode_choice:
            mode_val = "extract_sfx_only"
        elif "2. Giữ Giọng Đọc" in sep_mode_choice:
            mode_val = "isolate_vocals"
        elif "3. Tách Nhạc Nền" in sep_mode_choice:
            mode_val = "remove_vocals"
        else:
            mode_val = "both"

    with col2:
        engine_choice = st.radio(
            "⚡ Động cơ xử lý:",
            [
                "⚡ Động Cơ DSP Studio Instant — Siêu Tốc <30s (Khuyên dùng cho video dài 1–6 tiếng)",
                "🧠 Động Cơ AI Studio (UVR MDX-Net + Spectral HPSS) — Chuẩn Phòng Thu CapCut Pro (Clip / Bài Hát ngắn)"
            ],
            index=0,
            key="vocal_sep_engine_radio"
        )
        is_ai_engine = "AI Studio" in engine_choice

    chosen_overlap = 0.08
    chosen_threads = 8

    if is_ai_engine:
        st.markdown("<hr style='border-color: rgba(255,255,255,0.08); margin: 15px 0;'>", unsafe_allow_html=True)
        st.markdown('<div class="card-title" style="font-size: 14px;">⚡ Tùy Chỉnh Tăng Tốc Đa Luồng (AI Engine)</div>', unsafe_allow_html=True)
        c_ai1, c_ai2 = st.columns(2)
        with c_ai1:
            speed_mode = st.selectbox(
                "🚀 Chế độ Tối ưu & Tốc độ ghép nối (Overlap):",
                [
                    "⚡ Siêu Tốc (Overlap 8% — Tăng tốc gấp đôi, khuyên dùng cho video dài)",
                    "🎯 Tiêu Chuẩn (Overlap 18% — Cân bằng tốc độ & độ mượt)",
                    "💎 Phòng Thu Cao Cấp (Overlap 35% — Dành cho bài hát / audio ngắn)"
                ],
                index=0,
                key="vocal_sep_speed_mode"
            )
            if "Siêu Tốc" in speed_mode:
                chosen_overlap = 0.08
            elif "Tiêu Chuẩn" in speed_mode:
                chosen_overlap = 0.18
            else:
                chosen_overlap = 0.35

        with c_ai2:
            import os
            max_cores = os.cpu_count() or 8
            thread_opts = [f"🚀 Tối đa {max_cores} Luồng CPU (Max Speed)"]
            if max_cores >= 4:
                thread_opts.append("⚡ 4 Luồng CPU")
            thread_opts.append("🌱 2 Luồng CPU (Tiết kiệm CPU)")
            
            chosen_t_label = st.selectbox("🧵 Số Luồng Xử Lý CPU:", thread_opts, index=0, key="vocal_sep_threads")
            if "Tối đa" in chosen_t_label:
                chosen_threads = max_cores
            elif "4 Luồng" in chosen_t_label:
                chosen_threads = 4
            else:
                chosen_threads = 2
    else:
        st.info("💡 **Mẹo:** Động cơ **DSP Studio Instant** có tốc độ cực nhanh (xử lý file dài 5–6 tiếng chỉ trong **20–35 giây**), tự động triệt tiêu các bài hát stereo đa kênh lồng ngầm và giữ lại âm thanh sạch sẽ.")

    st.markdown("</div>", unsafe_allow_html=True)

    # 3. Nút hành động bắt đầu tách
    if st.button("🚀 BẮT ĐẦU BÓC TÁCH & LÀM SẠCH ÂM THANH NGAY", use_container_width=True, type="primary", key="btn_start_vocal_sep"):
        if not selected_media_path or not selected_media_path.exists():
            st.error("Vui lòng chọn hoặc tải lên một file video/âm thanh trước!")
        else:
            progress_bar = st.progress(0)
            status_box = st.empty()

            def update_progress(pct, msg):
                progress_bar.progress(min(100, max(0, pct)))
                status_box.info(msg)

            out_sep_dir = Path("output_clips") / f"separated_{int(time.time())}"
            out_sep_dir.mkdir(parents=True, exist_ok=True)

            if is_ai_engine:
                res = separate_audio_ai(
                    input_file=selected_media_path,
                    output_dir=out_sep_dir,
                    mode=mode_val,
                    overlap_ratio=chosen_overlap,
                    num_threads=chosen_threads,
                    progress_callback=update_progress
                )
            else:
                res = separate_audio_dsp(
                    input_file=selected_media_path,
                    output_dir=out_sep_dir,
                    mode=mode_val,
                    progress_callback=update_progress
                )

            status_box.empty()
            progress_bar.empty()

            if res["success"]:
                res["input_media_path"] = str(selected_media_path)
                res["media_display_title"] = media_display_title
                st.session_state["vocal_sep_result"] = res
                st.success(f"🎉 Đã xử lý âm thanh thành công bằng **{res.get('engine', 'DSP/AI')}**: **{res['filename']}**!")
            else:
                st.error(f"❌ Xử lý thất bại: {res.get('error', 'Lỗi không xác định')}")

    # 4. Hiển thị kết quả & Tích hợp CapCut
    if "vocal_sep_result" in st.session_state and st.session_state["vocal_sep_result"]:
        res = st.session_state["vocal_sep_result"]
        out_audio_file = Path(res["output_path"]) if res.get("output_path") else None
        sfx_audio_file = Path(res.get("sfx_path", "")) if res.get("sfx_path") and os.path.exists(res.get("sfx_path")) else (out_audio_file if (out_audio_file and "sfx" in out_audio_file.name.lower()) else None)
        voc_audio_file = Path(res.get("vocals_path", "")) if res.get("vocals_path") and os.path.exists(res.get("vocals_path")) else (out_audio_file if (out_audio_file and "vocal" in out_audio_file.name.lower()) else None)
        bgm_audio_file = Path(res.get("instrumental_path", "")) if res.get("instrumental_path") and os.path.exists(res.get("instrumental_path")) else (out_audio_file if (out_audio_file and "instrumental" in out_audio_file.name.lower()) else None)
        orig_media_file = Path(res["input_media_path"]) if res.get("input_media_path") and os.path.exists(res.get("input_media_path")) else None

        st.markdown("<hr style='border-color: rgba(255,255,255,0.1); margin: 25px 0;'>", unsafe_allow_html=True)
        st.markdown(f'<div class="card-title">📊 Kết Quả Xử Lý: {res["filename"]} ({res.get("engine", "Studio")})</div>', unsafe_allow_html=True)

        cols_display = []
        if sfx_audio_file and sfx_audio_file.exists():
            cols_display.append(("sfx", sfx_audio_file))
        if voc_audio_file and voc_audio_file.exists():
            cols_display.append(("voc", voc_audio_file))
        if bgm_audio_file and bgm_audio_file.exists():
            cols_display.append(("bgm", bgm_audio_file))

        if len(cols_display) == 1:
            ui_cols = [st.container()]
        elif len(cols_display) == 2:
            ui_cols = st.columns(2)
        else:
            ui_cols = st.columns(3)

        for idx, (t_type, a_path) in enumerate(cols_display):
            target_col = ui_cols[idx] if idx < len(ui_cols) else st.container()
            with target_col:
                if t_type == "sfx":
                    st.markdown("#### 💥 1. Tiếng Động SFX Sạch (Khử Hết Nhạc & Lời):")
                    st.caption("Chỉ chứa tiếng bước chân, súng, cửa, va chạm... Sạch 100% bản quyền.")
                    with open(a_path, "rb") as af:
                        st.audio(af.read(), format="audio/mp3")
                    with open(a_path, "rb") as af:
                        st.download_button(
                            label=f"📥 Tải SFX Sạch ({round(a_path.stat().st_size/(1024*1024), 2)} MB)",
                            data=af.read(),
                            file_name=a_path.name,
                            mime="audio/mp3",
                            use_container_width=True,
                            key="dl_btn_sfx_clean"
                        )
                elif t_type == "voc":
                    st.markdown("#### 🎤 2. Giọng Đọc Thoại Sạch (Khử Hết BGM/Bài Hát):")
                    st.caption("Track âm thanh chỉ chứa giọng nói thuyết minh, sạch 100% bản quyền.")
                    with open(a_path, "rb") as af:
                        st.audio(af.read(), format="audio/mp3")
                    with open(a_path, "rb") as af:
                        st.download_button(
                            label=f"📥 Tải Giọng Thoại ({round(a_path.stat().st_size/(1024*1024), 2)} MB)",
                            data=af.read(),
                            file_name=a_path.name,
                            mime="audio/mp3",
                            use_container_width=True,
                            key="dl_btn_voc_clean"
                        )
                    if st.button("🧬 Dùng Làm Giọng Mẫu OmniVoice (Clone)", use_container_width=True, key="btn_voc_to_omnivoice"):
                        st.session_state["omni_preselected_ref"] = str(a_path)
                        st.toast("✅ Đã nạp giọng thoại sạch vào OmniVoice!", icon="🧬")
                        st.success("✅ Đã chọn làm giọng mẫu trong tab Tạo Giọng Đọc -> OmniVoice!")
                elif t_type == "bgm":
                    st.markdown("#### 🎵 3. Nhạc Nền / Beat Đã Bóc (Đã Bỏ Lời Hát):")
                    st.caption("Track âm thanh chỉ chứa nhạc nền và tiếng động, đã tách bỏ lời ca sĩ.")
                    with open(a_path, "rb") as af:
                        st.audio(af.read(), format="audio/mp3")
                    with open(a_path, "rb") as af:
                        st.download_button(
                            label=f"📥 Tải Nhạc Nền Beat ({round(a_path.stat().st_size/(1024*1024), 2)} MB)",
                            data=af.read(),
                            file_name=a_path.name,
                            mime="audio/mp3",
                            use_container_width=True,
                            key="dl_btn_bgm_clean"
                        )

        # 5. Ghép Trực Tiếp Vào Video Gốc
        if orig_media_file and orig_media_file.exists() and orig_media_file.suffix.lower() in [".mp4", ".mkv", ".mov"]:
            st.markdown('<div class="card" style="margin-top: 15px;">', unsafe_allow_html=True)
            st.markdown('<div class="card-title">🎬 Tự Động Ghép Track Âm Thanh Mới Vào Video Gốc (1-Click)</div>', unsafe_allow_html=True)
            st.write("Tạo ngay một file video mới đã thay thế track âm thanh cũ, không cần mở Premiere hay CapCut.")
            
            c_btns = []
            if sfx_audio_file and sfx_audio_file.exists():
                c_btns.append(("sfx", "💥 Ghép Tiếng Động SFX Sạch Vào Video", sfx_audio_file))
            if voc_audio_file and voc_audio_file.exists():
                c_btns.append(("voc", "🛡️ Ghép Giọng Thoại Sạch Vào Video", voc_audio_file))
            if bgm_audio_file and bgm_audio_file.exists():
                c_btns.append(("bgm", "🎵 Ghép Nhạc Nền Đã Bóc Vào Video", bgm_audio_file))

            cols_v = st.columns(len(c_btns)) if c_btns else [st.container()]
            for b_idx, (b_type, b_label, b_file) in enumerate(c_btns):
                with cols_v[b_idx]:
                    if st.button(b_label, use_container_width=True, type="primary" if b_type=="sfx" else "secondary", key=f"btn_merge_v_{b_type}"):
                        with st.spinner(f"⏳ Đang ghép track {b_type.upper()} vào video gốc..."):
                            v_merge_res = separate_video_with_audio_track(
                                video_file=orig_media_file,
                                separated_audio_file=b_file,
                                output_dir=b_file.parent
                            )
                            if v_merge_res["success"]:
                                st.session_state["vocal_sep_video_merged"] = v_merge_res["video_path"]
                                st.success(f"🎉 Đã tạo video ghép track {b_type.upper()} thành công: **{v_merge_res['filename']}**!")

            if "vocal_sep_video_merged" in st.session_state and os.path.exists(st.session_state["vocal_sep_video_merged"]):
                merged_v_path = Path(st.session_state["vocal_sep_video_merged"])
                st.markdown(f"**File video đã xuất:** `{merged_v_path.name}` ({round(merged_v_path.stat().st_size/(1024*1024), 2)} MB)")
                with open(merged_v_path, "rb") as vf:
                    st.download_button(
                        label=f"📥 TẢI FILE VIDEO ĐÃ XỬ LÝ (.MP4)",
                        data=vf.read(),
                        file_name=merged_v_path.name,
                        mime="video/mp4",
                        use_container_width=True,
                        key="dl_btn_merged_video"
                    )
            st.markdown('</div>', unsafe_allow_html=True)

        # 6. CapCut Draft 1-Click Injection
        st.markdown('<div class="card" style="margin-top: 15px;">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">🎬 Thêm Trực Tiếp Vào Dự Án CapCut Mac (1-Click)</div>', unsafe_allow_html=True)
        capcut_projects = get_mac_capcut_projects()
        if capcut_projects:
            proj_names = [f"{p.get('name', 'Dự án không tên')}" + (f" ({p['modified_str']})" if p.get('modified_str') else "") for p in capcut_projects]
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                selected_proj_idx = st.selectbox(
                    "Chọn dự án CapCut đang mở trên máy:",
                    range(len(proj_names)),
                    format_func=lambda i: proj_names[i],
                    key="vocal_sep_capcut_proj_select"
                )
                selected_proj = capcut_projects[selected_proj_idx]

            with col_d2:
                inject_opts = []
                if sfx_audio_file and sfx_audio_file.exists():
                    inject_opts.append("💥 Track Tiếng Động SFX Sạch (Khuyên dùng)")
                if voc_audio_file and voc_audio_file.exists():
                    inject_opts.append("🎤 Track Giọng Nói Sạch")
                if bgm_audio_file and bgm_audio_file.exists():
                    inject_opts.append("🎵 Track Nhạc Nền / Beat")

                if not inject_opts:
                    inject_opts = ["💥 Track Tiếng Động SFX Sạch (Khuyên dùng)", "🎤 Track Giọng Nói Sạch", "🎵 Track Nhạc Nền / Beat"]

                track_to_inject = st.radio(
                    "Chọn track để chèn vào CapCut:",
                    inject_opts,
                    horizontal=True,
                    key="vocal_sep_inject_track_choice"
                )

            mute_orig_video = st.checkbox("🔇 Tự động tắt tiếng (Mute track video gốc) trong CapCut", value=True)

            if st.button("🚀 Chèn Track Âm Thanh Vào CapCut Ngay", type="primary", use_container_width=True, key="btn_inject_capcut_audio"):
                if "SFX" in track_to_inject:
                    inject_file = sfx_audio_file if (sfx_audio_file and sfx_audio_file.exists()) else out_audio_file
                elif "Giọng Nói" in track_to_inject:
                    inject_file = voc_audio_file if (voc_audio_file and voc_audio_file.exists()) else out_audio_file
                else:
                    inject_file = bgm_audio_file if (bgm_audio_file and bgm_audio_file.exists()) else out_audio_file

                if not inject_file or not inject_file.exists():
                    st.error("Không tìm thấy file âm thanh để chèn.")
                else:
                    with st.spinner("⏳ Đang ghi track âm thanh vào bản nháp CapCut..."):
                        inj_res = add_separated_audio_to_draft(
                            project_path=selected_proj["path"],
                            audio_file_path=inject_file,
                            mute_original_video=mute_orig_video
                        )
                        if inj_res["success"]:
                            st.success(f"🎉 Đã chèn âm thanh thành công vào dự án **{selected_proj['name']}**! Hãy mở CapCut để kiểm tra.")
                        else:
                            st.error(f"❌ Chèn thất bại: {inj_res.get('error', 'Lỗi không xác định')}")
        else:
            st.info("💡 Không tìm thấy dự án CapCut nào gần đây trên máy Mac của bạn.")
        st.markdown("</div>", unsafe_allow_html=True)
