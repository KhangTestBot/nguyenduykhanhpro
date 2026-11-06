"""
Feature module: TTS Tools (Tạo Giọng Đọc AI & Sao Chép Giọng Mẫu OmniVoice)
Supports:
1. CapCut Text-To-Speech generation with curated voice favorites.
2. k2-fsa/OmniVoice Zero-Shot Voice Cloning from short audio samples (Colab GPU & local).
"""

import streamlit as st
import time
from pathlib import Path

def render_tts_tools():
    """Renders the 'Tạo Giọng Đọc' feature tab with CapCut TTS & OmniVoice Cloning."""
    from utils.capcut_tts_wrapper import (
        get_available_voices,
        generate_tts,
        toggle_favorite_voice,
        get_or_create_voice_preview,
        add_custom_voice,
    )
    from utils.omnivoice_wrapper import (
        is_omnivoice_available,
        get_device_info,
        generate_cloned_voice,
    )

    st.markdown("""
    <div class="hero-banner">
    <div class="hero-title">🎙️ Studio Giọng Đọc AI & Sao Chép Giọng Mẫu</div>
    <div class="hero-subtitle">Tạo giọng đọc từ văn bản với CapCut TTS hoặc nhân bản bất kỳ giọng nói nào với k2-fsa/OmniVoice</div>
    <div class="badge-row">
    <span class="badge">🔥 Tốc độ cao</span>
    <span class="badge">🧬 Zero-Shot Voice Cloning</span>
    <span class="badge">🇻🇳 Hỗ trợ Tiếng Việt & Đa Ngôn Ngữ</span>
    <span class="badge">🚀 Tăng tốc GPU Colab</span>
    </div>
    </div>
    """, unsafe_allow_html=True)

    tab_capcut, tab_omnivoice = st.tabs([
        "🎙️ Kho Giọng Đọc Sẵn Có (CapCut TTS)",
        "🧬 Sao Chép Giọng Mẫu (OmniVoice Zero-Shot Cloning)"
    ])

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 1: CAPCUT TTS
    # ─────────────────────────────────────────────────────────────────────────
    with tab_capcut:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">📝 Cấu Hình Giọng Đọc Sẵn Có</div>', unsafe_allow_html=True)

        txt_file = st.file_uploader("📂 Tải Lên File Văn Bản (.txt)", type=["txt"], key="capcut_txt_uploader")
        default_text = ""
        if txt_file is not None:
            try:
                default_text = txt_file.getvalue().decode("utf-8")
            except Exception as e:
                st.error(f"Không thể đọc file: {e}")

        text_input = st.text_area(
            "Nhập nội dung cần đọc:",
            value=default_text,
            height=130,
            placeholder="Xin chào các bạn, hôm nay mình sẽ hướng dẫn...",
            key="capcut_text_input"
        )

        lang_choice = st.selectbox(
            "🌐 Chọn Ngôn Ngữ Giọng Đọc:",
            options=[
                "🇻🇳 Tiếng Việt (24 giọng)",
                "🇬🇧 Tiếng Anh (39 giọng)",
                "🇨🇳 Tiếng Trung (16 giọng)",
                "🇯🇵 Tiếng Nhật (19 giọng)",
                "🇪🇸 Tiếng Tây Ban Nha (9 giọng)",
                "🇮🇩 Tiếng Indonesia (5 giọng)",
                "🇹🇭 Tiếng Thái (5 giọng)",
                "🌍 Ngôn ngữ khác (Pháp, Đức, Bồ Đào Nha... - 10 giọng)",
                "🌐 Tất Cả Ngôn Ngữ (127 giọng)"
            ],
            index=0,
            key="capcut_lang_choice"
        )

        lang_map = {
            "🇻🇳 Tiếng Việt (24 giọng)": "vi",
            "🇬🇧 Tiếng Anh (39 giọng)": "en",
            "🇨🇳 Tiếng Trung (16 giọng)": "zh",
            "🇯🇵 Tiếng Nhật (19 giọng)": "ja",
            "🇪🇸 Tiếng Tây Ban Nha (9 giọng)": "es",
            "🇮🇩 Tiếng Indonesia (5 giọng)": "id",
            "🇹🇭 Tiếng Thái (5 giọng)": "th",
            "🌍 Ngôn ngữ khác (Pháp, Đức, Bồ Đào Nha... - 10 giọng)": "other",
            "🌐 Tất Cả Ngôn Ngữ (127 giọng)": "all"
        }
        selected_lang_code = lang_map[lang_choice]

        voices = get_available_voices(lang_filter=selected_lang_code)
        if not voices:
            st.error("Không tìm thấy danh sách giọng đọc. Vui lòng kiểm tra file Voice.json")
        else:
            voice_options = {v['name']: v for v in voices}
            voice_names = list(voice_options.keys())
            default_v_idx = 0
            for idx, vn in enumerate(voice_names):
                if "Cô Gái Hoạt Ngôn" in vn or "hoat ngon" in vn.lower():
                    default_v_idx = idx
                    break

            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                selected_voice_name = st.selectbox("🗣️ Chọn Giọng Đọc", voice_names, index=default_v_idx, key="capcut_voice_sel")

            v_data = voice_options[selected_voice_name]
            v_id = v_data['id']
            is_fav = v_data['is_fav']

            with col2:
                st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
                if st.button("🔊 Nghe Thử", use_container_width=True, key="capcut_preview_btn"):
                    with st.spinner("Đang lấy giọng mẫu..."):
                        ok, p_res = get_or_create_voice_preview(v_data)
                        if ok:
                            st.session_state["preview_audio_info"] = {
                                "path": p_res,
                                "name": selected_voice_name
                            }
                        else:
                            st.error(f"Không thể nghe thử: {p_res}")

            with col3:
                st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
                if st.button("❌ Bỏ ⭐" if is_fav else "⭐ Yêu Thích", use_container_width=True, key="capcut_fav_btn"):
                    toggle_favorite_voice(v_id)
                    st.rerun()

            # Hiển thị audio nghe thử nếu có
            if "preview_audio_info" in st.session_state:
                p_info = st.session_state["preview_audio_info"]
                st.markdown(f"**🔊 Đang nghe thử giọng:** `{p_info['name']}`")
                st.audio(p_info["path"], format="audio/mp3")

            st.markdown("<br>", unsafe_allow_html=True)

            if st.button("🚀 Chuyển Đổi Text Thành Audio (CapCut)", use_container_width=True, key="btn_convert_tts"):
                if not text_input.strip():
                    st.warning("Vui lòng nhập nội dung cần đọc!")
                else:
                    out_dir = Path("output_clips")
                    out_dir.mkdir(exist_ok=True)
                    out_file = out_dir / f"tts_{int(time.time())}.mp3"

                    with st.spinner("Đang kết nối với CapCut server để tạo giọng đọc..."):
                        success, result_or_err = generate_tts(
                            text=text_input.strip(),
                            voice_type=v_data['id'],
                            resource_id=v_data['resource_id'],
                            output_path=str(out_file)
                        )

                    if success:
                        st.session_state["tts_result_file"] = str(result_or_err)
                        st.session_state["tts_result_name"] = out_file.name
                        st.success("Tạo audio thành công!")
                    else:
                        st.error(f"Thất bại: {result_or_err}")

            if st.session_state.get("tts_result_file"):
                t_path = Path(st.session_state["tts_result_file"])
                if t_path.exists():
                    st.markdown("### 🔊 Kết Quả Giọng Đọc Đã Tạo")
                    st.audio(str(t_path), format="audio/mp3")
                    with open(t_path, "rb") as f:
                        st.download_button(
                            "💾 Tải File MP3",
                            data=f.read(),
                            file_name=st.session_state.get("tts_result_name", t_path.name),
                            mime="audio/mp3",
                            key="dl_btn_tts_persist"
                        )

            st.markdown("<br>", unsafe_allow_html=True)
            with st.expander("➕ Thêm Giọng Đọc Mới Tùy Chỉnh (CapCut)"):
                st.markdown("<small>Nhập thông tin Voice Type ID và Resource ID từ CapCut để bổ sung giọng đọc mới vào hệ thống:</small>", unsafe_allow_html=True)
                col_a, col_b = st.columns(2)
                with col_a:
                    new_disp = st.text_input("Tên Hiển Thị (ví dụ: English Ghostface)", key="add_new_disp")
                    new_vtype = st.text_input("Voice Type ID (ví dụ: en_us_ghostface)", key="add_new_vtype")
                with col_b:
                    new_resid = st.text_input("Resource ID (ví dụ: 7114563482518819329)", key="add_new_resid")
                    new_lang_choice = st.selectbox(
                        "Ngôn Ngữ",
                        options=["en (Tiếng Anh)", "vi (Tiếng Việt)", "zh (Tiếng Trung)", "ja (Tiếng Nhật)", "es (Tiếng Tây Ban Nha)", "th (Tiếng Thái)", "id (Tiếng Indonesia)"],
                        key="add_new_lang"
                    )

                if st.button("💾 Lưu Giọng Đọc Mới", key="btn_save_custom_voice"):
                    if not new_disp.strip() or not new_vtype.strip() or not new_resid.strip():
                        st.warning("Vui lòng điền đầy đủ Tên hiển thị, Voice Type ID và Resource ID!")
                    else:
                        lan_code = new_lang_choice.split()[0]
                        ok_add, msg_add = add_custom_voice(
                            display_name=new_disp.strip(),
                            voice_type=new_vtype.strip(),
                            resource_id=new_resid.strip(),
                            lan=lan_code,
                            lang="en-US" if lan_code == "en" else f"{lan_code}-{lan_code.upper()}"
                        )
                        if ok_add:
                            st.success(msg_add)
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(msg_add)

        st.markdown('</div>', unsafe_allow_html=True)

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 2: OMNIVOICE ZERO-SHOT CLONING
    # ─────────────────────────────────────────────────────────────────────────
    with tab_omnivoice:
        dev_info = get_device_info()
        is_avail = is_omnivoice_available()

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(f"""
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <div class="card-title" style="margin:0;">🧬 Nhân Bản & Sao Chép Giọng Đọc (k2-fsa/OmniVoice)</div>
            <span class="badge" style="background:#1e293b; border:1px solid #38bdf8; color:#38bdf8;">{dev_info['badge']}</span>
        </div>
        <p style="color:#94a3b8; font-size:0.9rem;">
            Chỉ cần cung cấp 1 đoạn âm thanh mẫu (3 đến 10 giây) của bất kỳ ai, OmniVoice sẽ tự động học âm sắc và đọc văn bản của bạn với chính chất giọng đó.
        </p>
        """, unsafe_allow_html=True)

        if not is_avail:
            st.warning("""
            ⚠️ **Gói `omnivoice` chưa được cài đặt trong môi trường hiện tại.**
            - Để sử dụng tính năng này mượt mà nhất với **GPU T4**, bạn có thể chạy app trên **Google Colab** (file `run_on_colab.ipynb` đã cấu hình sẵn).
            - Hoặc cài đặt thủ công: `pip install omnivoice torch torchaudio soundfile`
            """)

        # 1. Chọn file giọng mẫu (Reference Audio)
        st.markdown("#### 1️⃣ Chọn Đoạn Âm Thanh / Video Giọng Mẫu (3 - 10 giây)")
        preselected_ref = st.session_state.get("omni_preselected_ref")
        default_ref_idx = 1 if (preselected_ref and Path(preselected_ref).exists()) else 0

        ref_mode = st.radio(
            "Nguồn file giọng mẫu:",
            ["📁 Tải Lên File Âm Thanh / Video (.wav / .mp3 / .m4a / .mp4)", "📂 Chọn Từ Các File Đã Tách Giọng / Âm Thanh Trước Đó"],
            index=default_ref_idx,
            horizontal=True,
            key="omni_ref_mode"
        )

        ref_audio_path = None
        if ref_mode.startswith("📁"):
            uploaded_ref = st.file_uploader(
                "Tải lên file giọng mẫu (khuyên dùng đoạn nói rõ ràng, không nhạc nền):",
                type=["wav", "mp3", "m4a", "ogg", "flac", "mp4", "mov", "mkv"],
                key="omni_ref_file"
            )
            if uploaded_ref is not None:
                tmp_dir = Path("output_voiceovers") / "temp_ref"
                tmp_dir.mkdir(parents=True, exist_ok=True)
                save_ref_path = tmp_dir / uploaded_ref.name
                with open(save_ref_path, "wb") as f:
                    f.write(uploaded_ref.getvalue())
                ref_audio_path = str(save_ref_path)
                st.audio(ref_audio_path)
                st.caption(f"✅ Đã nhận file mẫu: `{uploaded_ref.name}`")
        else:
            # Tìm các file wav/mp3 có sẵn trong output_vocal_separation hoặc output_voiceovers
            candidate_files = []
            if preselected_ref and Path(preselected_ref).exists():
                candidate_files.append(Path(preselected_ref))
            for search_dir in ["output_vocal_separation", "output_voiceovers", "output_clips"]:
                p = Path(search_dir)
                if p.exists():
                    for ext in ("*.wav", "*.mp3", "*.m4a"):
                        for found in p.rglob(ext):
                            if found not in candidate_files:
                                candidate_files.append(found)

            if candidate_files:
                file_map = {f"{f.parent.name}/{f.name}": str(f) for f in candidate_files[:40]}
                chosen_label = st.selectbox("Chọn file có sẵn:", list(file_map.keys()), key="omni_existing_audio")
                ref_audio_path = file_map[chosen_label]
                st.audio(ref_audio_path)
            else:
                st.info("Chưa có file âm thanh nào trong hệ thống, vui lòng tải file lên ở chế độ Tải Lên.")

        st.markdown("<hr style='border-color:#334155; margin:1.5rem 0;'>", unsafe_allow_html=True)

        # 2. Nội dung cần đọc
        st.markdown("#### 2️⃣ Nhập Văn Bản Kịch Bản Cần Đọc")
        omni_txt_file = st.file_uploader("Hoặc tải lên file .txt:", type=["txt"], key="omni_txt_uploader")
        omni_default_text = ""
        if omni_txt_file is not None:
            try:
                omni_default_text = omni_txt_file.getvalue().decode("utf-8")
            except Exception as e:
                st.error(f"Lỗi đọc file: {e}")

        omni_text_input = st.text_area(
            "Văn bản muốn nhân bản giọng đọc:",
            value=omni_default_text,
            height=140,
            placeholder="Chào mừng các bạn đã quay trở lại với kênh! Hôm nay mình sẽ chia sẻ...",
            key="omni_target_text"
        )

        with st.expander("⚙️ Tùy Chọn Nâng Cao (Cắt đoạn mẫu & Transcript)"):
            col_r1, col_r2 = st.columns(2)
            with col_r1:
                ref_start_sec = st.number_input("⏱️ Giây bắt đầu lấy mẫu (s):", min_value=0.0, max_value=3600.0, value=0.0, step=1.0, key="omni_ref_start")
            with col_r2:
                ref_duration_sec = st.slider("⏳ Độ dài đoạn mẫu tối ưu (giây):", min_value=3.0, max_value=15.0, value=8.0, step=0.5, key="omni_ref_dur")
            ref_transcript = st.text_input(
                "Nội dung văn bản của đoạn audio mẫu (Reference Text):",
                placeholder="Để trống nếu muốn OmniVoice tự nhận diện bằng Whisper ASR...",
                key="omni_ref_transcript"
            )
            st.caption("💡 Hệ thống tự động trích xuất đoạn giọng mẫu sạch 24kHz và lọc nhiễu nền trước khi đưa vào OmniVoice.")

        st.markdown("<br>", unsafe_allow_html=True)

        # 3. Nút bấm nhân bản giọng
        if st.button("🧬 Nhân Bản & Tạo Giọng Nói (OmniVoice)", use_container_width=True, key="btn_run_omnivoice"):
            if not is_avail:
                st.error("Thư viện `omnivoice` chưa được cài đặt. Vui lòng chuyển sang Google Colab để tận dụng GPU T4 hoặc cài đặt thư viện.")
            elif not ref_audio_path:
                st.warning("Vui lòng tải lên hoặc chọn một đoạn âm thanh mẫu (3 - 10s) trước!")
            elif not omni_text_input.strip():
                st.warning("Vui lòng nhập nội dung văn bản cần đọc!")
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()

                def update_progress(percent, msg):
                    progress_bar.progress(percent)
                    status_text.info(f"⏳ {msg}")

                out_cloned_dir = Path("output_voiceovers") / "omnivoice"
                out_cloned_dir.mkdir(parents=True, exist_ok=True)
                dest_file = out_cloned_dir / f"cloned_{int(time.time())}.wav"

                ok_clone, res_clone = generate_cloned_voice(
                    text=omni_text_input.strip(),
                    ref_audio_path=ref_audio_path,
                    output_path=str(dest_file),
                    ref_text=ref_transcript.strip() if ref_transcript else None,
                    ref_start_sec=ref_start_sec,
                    ref_duration_sec=ref_duration_sec,
                    progress_callback=update_progress
                )

                if ok_clone:
                    st.session_state["omni_cloned_file"] = res_clone
                    progress_bar.progress(100)
                    status_text.success("🎉 Nhân bản giọng nói thành công!")
                else:
                    progress_bar.empty()
                    status_text.error(f"❌ {res_clone}")

        # Hiển thị kết quả nhân bản
        if st.session_state.get("omni_cloned_file"):
            cloned_p = Path(st.session_state["omni_cloned_file"])
            if cloned_p.exists():
                st.markdown("### 🔊 Kết Quả Giọng Nói Nhân Bản (OmniVoice)")
                st.audio(str(cloned_p), format="audio/wav")
                with open(cloned_p, "rb") as f:
                    st.download_button(
                        "💾 Tải File Âm Thanh (.wav)",
                        data=f.read(),
                        file_name=cloned_p.name,
                        mime="audio/wav",
                        key="btn_dl_omni_cloned"
                    )

        st.markdown('</div>', unsafe_allow_html=True)
