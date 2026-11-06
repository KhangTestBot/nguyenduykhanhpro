"""
Feature module: Video Splitter (Cắt Video & Lách Bản Quyền)
Dedicated file for all video splitting, trimming, and anti-copyright filter controls.
"""

import streamlit as st
import os
import time
import shutil
import tempfile
import traceback
from pathlib import Path
from datetime import datetime

from features.common_ui import (
    OUTPUT_BASE,
    SUPPORTED_FORMATS,
    MAX_CLIP_DURATION,
    YTDLP_AVAILABLE,
    human_size,
    format_duration,
    get_video_info,
    safe_filename,
    cleanup_old_processes,
    download_video_from_url,
    render_clips,
)

def render_video_splitter_tab():
    """Renders the complete 'Cắt Video' feature tab."""

    # ── Hero Banner ──────────────────────────────────────────────────────
    st.markdown("""
    <div class="hero-banner">
    <div style="display:inline-flex; align-items:center; gap:8px; background:rgba(99,102,241,0.12); border:1px solid rgba(99,102,241,0.3); border-radius:999px; padding:4px 14px; margin-bottom:14px;">
      <span style="width:8px; height:8px; background:#22c55e; border-radius:50%; box-shadow:0 0 10px #22c55e; animation: pulse-dot 1.8s infinite;"></span>
      <span style="font-size:0.75rem; font-weight:700; color:#38bdf8; text-transform:uppercase; letter-spacing:0.08em;">Studio AI Engine Active</span>
    </div>
    <div class="hero-title">🎬 NgDuyKhanh Pro</div>
    <div class="hero-subtitle">Tự động cắt video thông minh & tối ưu lách bản quyền cho TikTok · Reels · Shorts</div>
    <div class="badge-row">
    <span class="badge">🔗 Auto Download</span>
    <span class="badge">🔪 Auto Split</span>
    <span class="badge">🛡️ Copyright Bypass</span>
    <span class="badge">📱 9:16 Format</span>
    <span class="badge">⚡ Blur Background</span>
    <span class="badge">🔄 Mirror Flip</span>
    <span class="badge">🎨 Color Filter</span>
    </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Khu vực chính: 2 cột trung tâm ──────────────────────────────────
    col_left, col_right = st.columns([1.1, 1], gap="large")

    with col_left:
        # 1. Card Nguồn Video
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(
            '<div class="card-title">📤 1. Nguồn Video</div>',
            unsafe_allow_html=True)

        tab_upload, tab_url = st.tabs(["📁 Upload File", "🔗 Tải từ Link"])

        with tab_upload:
            uploaded_file = st.file_uploader(
                "Kéo thả hoặc chọn file video",
                type=SUPPORTED_FORMATS,
                help=f"Định dạng hỗ trợ: {', '.join(f'.{f}' for f in SUPPORTED_FORMATS)}",
                label_visibility="collapsed",
            )

            if uploaded_file:
                tmp_dir = Path(tempfile.mkdtemp())
                tmp_path = tmp_dir / uploaded_file.name
                with open(tmp_path, "wb") as f:
                    f.write(uploaded_file.read())

                file_size = tmp_path.stat().st_size
                st.markdown(f"""
                <div style="display:flex; gap:0.5rem; flex-wrap:wrap; margin: 0.5rem 0;">
                  <span class="file-tag">📁 {uploaded_file.name}</span>
                  <span class="file-tag">💾 {human_size(file_size)}</span>
                  <span class="file-tag">🎞️ {uploaded_file.type}</span>
                </div>
                """, unsafe_allow_html=True)

                with st.spinner("Đang phân tích video..."):
                    info = get_video_info(str(tmp_path))

                if "error" in info:
                    st.markdown(
                        f'<div class="error-box">❌ Không đọc được video: {info["error"]}</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.session_state["tmp_path"] = str(tmp_path)
                    st.session_state["video_info"] = info

        with tab_url:
            if not YTDLP_AVAILABLE:
                st.markdown(
                    '<div class="warning-box">⚠️ Cần cài <code>yt-dlp</code>: '
                    '<code>pip install yt-dlp</code></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown("""
                <div style="font-size:0.82rem; color:#94a3b8; margin-bottom:0.6rem; line-height:1.6;">
                  Hỗ trợ: <b>YouTube</b> · <b>TikTok</b> · <b>Facebook</b> · <b>Instagram</b> · <b>1000+ trang khác</b>
                </div>
                """, unsafe_allow_html=True)

                video_url = st.text_input(
                    "🔗 Nhập link video",
                    placeholder="https://www.youtube.com/watch?v=... hoặc link TikTok, FB, IG...",
                    key="video_url_input",
                )

                with st.expander("🔑 Tùy chọn: Cookies (Nếu gặp lỗi xác minh độ tuổi / chặn IP Cloud)", expanded=False):
                    st.caption("Nếu video yêu cầu đăng nhập hoặc bị YouTube chặn IP của Google Colab, bạn có thể xuất file `cookies.txt` từ trình duyệt và tải lên đây:")
                    uploaded_cookie = st.file_uploader("Tải file cookies.txt:", type=["txt"], key="cookie_uploader_splitter")
                    if uploaded_cookie is not None:
                        with open("cookies.txt", "wb") as cf:
                            cf.write(uploaded_cookie.getvalue())
                        st.success("✅ Đã nạp cookies.txt thành công! yt-dlp sẽ tự động dùng cookies này.")

                dl_btn = st.button(
                    "📥  Tải Video",
                    use_container_width=True,
                    key="download_btn",
                    disabled=not video_url,
                )

                if dl_btn and video_url:
                    st.session_state["pending_download_url"] = video_url
                    st.session_state["download_status"] = "downloading"

                dl_status = st.empty()

                if st.session_state.get("download_status") == "downloading":
                    current_url = st.session_state.get("pending_download_url")
                    dl_dir = Path(tempfile.mkdtemp())
                    with st.spinner("Đang tải video... Vui lòng không bấm nút khác!"):
                        result = download_video_from_url(
                            url=current_url,
                            output_dir=dl_dir,
                            progress_placeholder=dl_status,
                        )

                    if result["success"]:
                        dl_path = result["path"]
                        dl_title = result["title"]
                        file_size = Path(dl_path).stat().st_size

                        dl_status.markdown(f"""
                        <div class="success-box">
                          ✅ Tải thành công: <b>{dl_title}</b><br>
                          <span style="font-size:0.82rem;">
                            💾 {human_size(file_size)} · 📄 {Path(dl_path).name}
                          </span>
                        </div>
                        """, unsafe_allow_html=True)

                        info = get_video_info(dl_path)
                        if "error" not in info:
                            st.session_state["tmp_path"] = dl_path
                            st.session_state["video_info"] = info
                            st.session_state["auto_title"] = dl_title
                        else:
                            st.markdown(
                                f'<div class="error-box">❌ Lỗi đọc video: {info["error"]}</div>',
                                unsafe_allow_html=True,
                            )
                    else:
                        dl_status.markdown(
                            f'<div class="error-box">❌ Tải thất bại: {result["error"]}</div>',
                            unsafe_allow_html=True,
                        )

                    st.session_state["download_status"] = "done"

                if "tmp_path" in st.session_state and not dl_btn:
                    current_path = st.session_state.get("tmp_path", "")
                    if current_path and os.path.exists(current_path):
                        file_size = Path(current_path).stat().st_size
                        st.markdown(f"""
                        <div style="display:flex; gap:0.5rem; flex-wrap:wrap; margin: 0.5rem 0;">
                          <span class="file-tag">📁 {Path(current_path).name}</span>
                          <span class="file-tag">💾 {human_size(file_size)}</span>
                        </div>
                        """, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

        # 2. Card Cấu hình Series & Đầu ra
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(
            '<div class="card-title">📋 2. Thông Tin Series & Định Dạng Đầu Ra</div>',
            unsafe_allow_html=True)

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            series_title = st.text_input(
                "Tiêu đề gốc",
                value="",
                help="Tên sẽ được đánh số thứ tự: 'Tiêu đề 1', '2'...",
                placeholder="Nhập tên series (ví dụ: Tập)...",
            )
            show_part_number = st.checkbox(
                "Hiển thị chữ 'Part 1, 2...'",
                value=True,
                help="Bật để hiển thị phần đánh số tập trên video",
            )
        with col_s2:
            output_aspect = st.selectbox(
                "Tỉ lệ khung hình",
                options=["9:16 (TikTok/Reels)", "1:1 (Vuông)", "16:9 (YouTube)"],
                index=0,
            )
            output_format = st.selectbox(
                "Định dạng file",
                options=["mp4", "mov"],
                index=0,
            )

        clip_duration = st.slider(
            "⏱️ Thời lượng mỗi clip (giây)",
            min_value=60, max_value=MAX_CLIP_DURATION, value=75, step=1,
            help=f"Thời lượng 60–{MAX_CLIP_DURATION} giây cho TikTok/Reels/Shorts/YouTube",
        )

        split_mode = st.radio(
            "⚡ Chế độ Xử Lý Video:",
            options=[
                "🚀 Render Lách Bản Quyền (GPU Turbo Engine)",
                "⚡ Cắt Siêu Tốc (Stream Copy - 0.2s/clip, giữ 100% gốc)",
            ],
            index=0,
            help="Cắt Siêu Tốc: Chia nhỏ video trong tích tắc mà không mã hóa lại. Render Lách Bản Quyền: Chạy bộ lọc biến dạng hình ảnh, âm thanh, lật khung hình và chống quét bản quyền.",
            key="split_mode_radio"
        )
        is_fast_mode = "Stream Copy" in split_mode

        col_opt1, col_opt2 = st.columns(2)
        with col_opt1:
            blur_bg = st.checkbox(
                "🌫️ Blur Background (16:9 → 9:16)",
                value=True,
                help="Thêm nền mờ khi video gốc là ngang (16:9)",
                disabled=is_fast_mode,
            )
        with col_opt2:
            from utils.hardware_accelerator import detect_best_video_encoder
            hw_enc_info = detect_best_video_encoder()
            use_gpu = st.checkbox(
                f"🚀 Tăng tốc Phần Cứng ({hw_enc_info['encoder']})",
                value=True,
                help=f"Tự động kích hoạt {hw_enc_info['label']} (h264_nvenc trên Colab GPU / h264_videotoolbox trên Mac).",
                disabled=is_fast_mode,
            )

        with st.expander("⚙️ Tùy Chỉnh Nâng Cao Tốc Độ Render", expanded=False):
            col_hw1, col_hw2 = st.columns(2)
            with col_hw1:
                max_workers = st.selectbox(
                    "Số tiến trình render đồng thời",
                    options=[1, 2, 3, 4],
                    index=1,
                    help="2 luồng là tối ưu nhất trên CPU Mac của bạn (tránh quá tải luồng và nghẽn nhiệt).",
                )
            with col_hw2:
                quality_preset = st.selectbox(
                    "Mức nén / Tốc độ GPU",
                    options=["Cực nhanh (Bitrate 4000k)", "Cân bằng (Bitrate 5000k)", "Chất lượng cao (Bitrate 7500k)"],
                    index=1,
                )
                bitrate_map = {
                    "Cực nhanh (Bitrate 4000k)": "4000k",
                    "Cân bằng (Bitrate 5000k)": "5000k",
                    "Chất lượng cao (Bitrate 7500k)": "7500k"
                }
                video_bitrate = bitrate_map.get(quality_preset, "5000k")

        st.markdown('</div>', unsafe_allow_html=True)

        # 3. Card Thông Tin Video Gốc
        if "video_info" in st.session_state and st.session_state["video_info"]:
            info = st.session_state["video_info"]
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown(
                '<div class="card-title">📊 Thông Tin Video Gốc</div>',
                unsafe_allow_html=True)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("⏱️ Thời lượng", format_duration(info["duration"]))
            c2.metric("🎞️ FPS", f"{info['fps']:.0f}")
            c3.metric("📐 Kích thước", f"{info['size'][0]}×{info['size'][1]}")
            c4.metric("✂️ Số clips", info["n_clips"])

            start_t_ui = 0.0
            chunks_ui = []
            speed_val = 1.0 if is_fast_mode else float(speed_factor if "speed_factor" in locals() else 1.1)
            while start_t_ui < info["duration"]:
                end_t_ui = min(start_t_ui + (clip_duration * speed_val), info["duration"])
                chunks_ui.append({"start": start_t_ui, "end": end_t_ui})
                start_t_ui = end_t_ui
                
            if len(chunks_ui) > 1:
                last_dur_ui = (chunks_ui[-1]["end"] - chunks_ui[-1]["start"]) / speed_val
                if last_dur_ui < 60.0:
                    chunks_ui.pop()
                    
            actual_n = len(chunks_ui)
            st.markdown(f"""
            <div class="info-box" style="margin-top:0.8rem;">
              📌 Với thời lượng <b>{clip_duration}s/clip</b>, video sẽ được chia thành
              <b>{actual_n} clip</b> → đặt tên: <i>"{series_title or 'Clip'} 1"</i> → <i>"{series_title or 'Clip'} {actual_n}"</i>
            </div>
            """, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

    with col_right:
        # Card Cấu hình Lách Bản Quyền (Bypass Engine)
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(
            '<div class="card-title">🛡️ 3. Cấu Hình Lách Bản Quyền (Bypass Engine)</div>',
            unsafe_allow_html=True)

        if is_fast_mode:
            st.info("⚡ Bạn đang chọn **Chế Độ Cắt Siêu Tốc (Stream Copy)**: Các bộ lọc lách bản quyền dưới đây sẽ được bỏ qua để xuất file tức thì (0.2s/clip) với 100% chất lượng gốc. Để áp dụng hiệu ứng lách bản quyền, hãy chọn chế độ *Render Lách Bản Quyền* ở mục 2.")

        with st.expander("🖼️ 1. Biến Dạng Hình Ảnh (Visual Filters)", expanded=True):
            zoom_pct = st.slider(
                "🔍 Phóng to (Zoom %)",
                min_value=0, max_value=100, value=10, step=1,
                help="Phóng to nhẹ để thay đổi hash khung hình. 0% = không phóng to",
            )
            col_v1, col_v2 = st.columns(2)
            with col_v1:
                flip_horizontal = st.checkbox(
                    "🔄 Lật ngang (Mirror Flip)",
                    value=True,
                    help="Lật ngược video theo chiều ngang – hiệu quả lách bản quyền cao",
                )
                noise_overlay = st.checkbox(
                    "🌫️ Nhiễu hạt tàng hình (Siêu tốc)",
                    value=True,
                    help="Biến đổi gamma/contrast vi mô liên tục bẻ gãy hash pixel.",
                )
            with col_v2:
                micro_rotation = st.checkbox(
                    "📐 Xoay nghiêng vi mô",
                    value=False,
                    help="Xoay video 0.5 độ. Bắt buộc AI phải quét lại toàn bộ khung hình.",
                )
                dynamic_shake = st.checkbox(
                    "🌊 Lắc lư động (Micro-shake)",
                    value=False,
                    help="Dịch chuyển khung hình vài pixel liên tục theo thời gian.",
                )

        with st.expander("⏳ 2. Biến Dạng Thời Gian (Temporal Speed)", expanded=True):
            speed_factor = st.slider(
                "⚡ Tốc độ (Speed)",
                min_value=1.0, max_value=10.0, value=1.1, step=0.1,
                format="%.1fx",
                help="Tăng tốc độ video. Ví dụ: 1.1x, 1.2x... lên tối đa 10x.",
            )
            dynamic_speed = st.checkbox(
                "📈 Biến thiên tốc độ động (Tối ưu)",
                value=True,
                help="Dao động tốc độ liên tục quanh mức Tốc độ đã chọn.",
            )
            dynamic_amplitude = 0.03
            if dynamic_speed:
                dynamic_amplitude = st.slider(
                    "   ↳ Độ dao động tốc độ",
                    min_value=0.01, max_value=0.10, value=0.03, step=0.01, format="%.2f",
                )

            micro_cut = st.checkbox(
                "✂️ Cắt phân đoạn vi mô (Micro-cuts)",
                value=False,
                help="Tự động cắt bỏ một khoảng thời gian cực ngắn (0.1s - 0.3s) mỗi 10s.",
            )
            micro_cut_duration = 0.15
            if micro_cut:
                micro_cut_duration = st.slider(
                    "   ↳ Thời lượng cắt (giây)",
                    min_value=0.10, max_value=0.30, value=0.15, step=0.05, format="%.2fs",
                )

            frame_drop = st.checkbox(
                "🎬 Bỏ túi khung hình (Stutter)",
                value=False,
                help="Tạo hiện tượng giật vi mô ngẫu nhiên để phá thuật toán nhận diện nhịp độ.",
            )

        with st.expander("🎵 3. Âm Thanh & 🎨 Bộ Lọc Màu", expanded=True):
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                add_noise = st.checkbox(
                    "📻 Thêm tạp âm ẩn",
                    value=False,
                    help="Chèn một lớp âm thanh nhiễu siêu nhỏ.",
                )
                audio_reverb = st.checkbox(
                    "🎵 Tiếng vang vi mô (Reverb)",
                    value=True,
                    help="Thêm một lớp tiếng vang cực nhỏ bẻ gãy vân tay âm thanh.",
                )
                pitch_shift = st.slider(
                    "🎶 Tone giọng (Pitch Shift)",
                    min_value=-2, max_value=2, value=0, step=1,
                    help="0 = bình thường, -1 = trầm nhẹ, +1 = thanh.",
                )
            with col_a2:
                brightness = st.slider(
                    "☀️ Độ sáng (Brightness)",
                    min_value=-0.30, max_value=0.30, value=0.02, step=0.01,
                )
                contrast = st.slider(
                    "🎭 Tương phản (Contrast)",
                    min_value=0.80, max_value=1.30, value=1.05, step=0.01,
                )

        # Tính điểm Bypass
        bypass_score = 0
        if zoom_pct > 0: bypass_score += 1
        if flip_horizontal: bypass_score += 2
        if noise_overlay: bypass_score += 2
        if micro_rotation: bypass_score += 2
        if speed_factor > 1.01: bypass_score += 1
        if frame_drop: bypass_score += 3
        if add_noise: bypass_score += 2
        if pitch_shift != 0: bypass_score += 2
        if abs(brightness) > 0.01: bypass_score += 1
        if abs(contrast - 1.0) > 0.01: bypass_score += 1
        if dynamic_speed: bypass_score += 3
        if micro_cut: bypass_score += 2

        bypass_label = "🟢 Thấp" if bypass_score <= 4 else ("🟡 Trung bình" if bypass_score <= 9 else "🔴 Rất Cao")
        bypass_bar_pct = min(bypass_score * (100 / 22), 100)

        st.markdown(f"""
        <div style="margin-top:1.25rem; padding-top:1rem; border-top:1px solid rgba(255,255,255,0.08);">
          <div style="display:flex; justify-content:space-between; font-size:0.85rem; color:#94a3b8; margin-bottom:0.4rem;">
            <span>🎯 Mức độ bypass thuật toán:</span>
            <b style="color:#ffffff;">{bypass_label} ({bypass_score}/22)</b>
          </div>
          <div style="background:rgba(255,255,255,0.08); border-radius:999px; height:8px; overflow:hidden;">
            <div style="background:linear-gradient(90deg,#22c55e,#eab308,#ef4444);
              width:{bypass_bar_pct}%; height:100%; border-radius:999px;
              transition:width 0.5s ease;"></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

    # ── Nút bắt đầu ──────────────────────────────────────────────────────
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="card-title">🚀 Bắt Đầu Xử Lý</div>',
        unsafe_allow_html=True)

    has_video = "tmp_path" in st.session_state and os.path.exists(
        st.session_state.get("tmp_path", "")
    )

    if not has_video:
        st.markdown(
            '<div class="warning-box">⬅️ Vui lòng upload video trước</div>',
            unsafe_allow_html=True,
        )

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        start_btn = st.button(
            "🚀  Bắt Đầu Cắt & Xử Lý Video",
            disabled=not has_video,
            use_container_width=True,
            key="start_btn",
            type="primary",
        )
    with col_btn2:
        clear_btn = st.button(
            "🗑️  Xóa Kết Quả Cũ",
            use_container_width=True,
            key="clear_btn",
        )

    if clear_btn:
        if OUTPUT_BASE.exists():
            shutil.rmtree(OUTPUT_BASE)
            OUTPUT_BASE.mkdir(exist_ok=True)

        for f in Path(".").glob("*TEMP_MPY_wvf_snd*"):
            try:
                f.unlink()
            except BaseException:
                pass
        for f in Path(".").glob("dummy*.mp4"):
            try:
                f.unlink()
            except BaseException:
                pass

        st.session_state.pop("results", None)
        st.markdown(
            '<div class="success-box">✅ Đã xóa toàn bộ kết quả cũ và dọn dẹp file rác</div>',
            unsafe_allow_html=True,
        )

    st.markdown('</div>', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════════
    #  XỬ LÝ KHI NHẤN NÚT
    # ════════════════════════════════════════════════════════════════════════
    if start_btn and has_video:
        cleanup_old_processes()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = OUTPUT_BASE / f"run_{timestamp}"
        run_dir.mkdir(parents=True, exist_ok=True)

        st.markdown("---")
        st.markdown("### ⚙️ Đang Xử Lý...")

        progress_bar = st.progress(0)
        status_text = st.empty()
        time_info = st.empty()

        start_time = time.time()

        try:
            results = render_clips(
                input_path=st.session_state["tmp_path"],
                output_dir=run_dir,
                title=series_title.strip(),
                show_part_number=show_part_number,
                clip_duration=clip_duration,
                zoom_pct=float(zoom_pct),
                flip_horizontal=flip_horizontal,
                noise_overlay=noise_overlay,
                micro_rotation=micro_rotation,
                frame_drop=frame_drop,
                add_noise=add_noise,
                pitch_shift=int(pitch_shift),
                speed_factor=float(speed_factor),
                dynamic_speed=dynamic_speed,
                dynamic_amplitude=float(dynamic_amplitude),
                micro_cut=micro_cut,
                micro_cut_duration=float(micro_cut_duration),
                brightness=float(brightness),
                contrast=float(contrast),
                dynamic_shake=dynamic_shake,
                audio_reverb=audio_reverb,
                output_format=output_format,
                use_gpu=use_gpu,
                blur_bg=blur_bg,
                output_aspect=output_aspect,
                is_fast_mode=is_fast_mode,
                max_workers=max_workers,
                video_bitrate=video_bitrate,
                progress_bar=progress_bar,
                status_text=status_text,
            )
            st.session_state["results"] = results
            st.session_state["run_dir"] = str(run_dir)
        except Exception as fatal_err:
            st.markdown(
                f'<div class="error-box">💥 Lỗi nghiêm trọng: {fatal_err}<br><pre>{traceback.format_exc()}</pre></div>',
                unsafe_allow_html=True,
            )
            results = []

        elapsed = time.time() - start_time
        time_info.markdown(
            f'<div class="info-box">⏱️ Tổng thời gian xử lý: <b>{elapsed:.1f} giây</b></div>',
            unsafe_allow_html=True,
        )

    # ════════════════════════════════════════════════════════════════════════
    #  HIỂN THỊ KẾT QUẢ VÀ NÚT TẢI (Luôn hiển thị ngay cả khi rerun trang)
    # ════════════════════════════════════════════════════════════════════════
    if "results" in st.session_state and st.session_state["results"]:
        results = st.session_state["results"]
        run_dir = st.session_state.get("run_dir", "")

        st.markdown("---")
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(
            '<div class="card-title">📦 Kết Quả Xuất Ra</div>',
            unsafe_allow_html=True)

        success_list = [r for r in results if r["success"]]
        fail_list = [r for r in results if not r["success"]]

        m1, m2, m3, m4 = st.columns(4)
        total_size = sum(r["size"] for r in success_list)
        total_dur = sum(r["duration"] for r in success_list)
        m1.metric("✅ Clip thành công", len(success_list))
        m2.metric("❌ Clip lỗi", len(fail_list))
        m3.metric("💾 Tổng dung lượng", human_size(total_size))
        m4.metric("⏱️ Tổng thời lượng", format_duration(total_dur))

        if run_dir:
            col_dir1, col_dir2 = st.columns([3, 1])
            with col_dir1:
                st.markdown(f"""
                <div class="info-box">
                  📁 Thư mục output: <code>{run_dir}</code>
                </div>
                """, unsafe_allow_html=True)
            with col_dir2:
                if st.button("📂 Mở Thư Mục Finder", key="open_finder_btn", use_container_width=True):
                    import subprocess
                    try:
                        subprocess.run(["open", str(run_dir)])
                        st.toast("📂 Đã mở thư mục output trên Mac!")
                    except Exception as e:
                        st.error(f"Không thể mở thư mục: {e}")

        if success_list:
            for r in success_list:
                st.markdown(f"""
                <div class="clip-item">
                  <div class="clip-number">{r['part']}</div>
                  <div style="flex:1; min-width:0;">
                    <div style="font-weight:600; color:#e2e8f0; font-size:0.9rem;">{r['name']}</div>
                    <div style="font-size:0.78rem; color:#64748b; margin-top:0.1rem;">
                      ⏱️ {format_duration(r['duration'])} &nbsp;·&nbsp;
                      💾 {human_size(r['size'])}
                    </div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

            if len(success_list) > 1:
                zip_path = Path(run_dir) / "all_clips.zip"
                if not zip_path.exists():
                    import zipfile
                    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for r in success_list:
                            if r["file"] and os.path.exists(r["file"]):
                                zipf.write(r["file"], arcname=Path(r["file"]).name)

                if zip_path.exists():
                    col_zip1, col_zip2 = st.columns([1, 1])
                    with col_zip1:
                        with open(zip_path, "rb") as f:
                            st.download_button(
                                label="📦 TẢI TẤT CẢ (ZIP)",
                                data=f,
                                file_name=f"{safe_filename(series_title) if series_title else 'Video_Splitter'}.zip",
                                mime="application/zip",
                                key="dl_all_zip",
                                use_container_width=True,
                                type="primary")
                    with col_zip2:
                        if st.button("📂 Lấy File Zip Trong Finder", key="open_zip_finder", use_container_width=True):
                            import subprocess
                            subprocess.run(["open", "-R", str(zip_path)])
                            st.toast("📂 Đã mở file Zip trong Finder!")

            st.markdown(
                '<div style="margin: 0.8rem 0 0.4rem;"><b>📥 Tải từng clip:</b></div>',
                unsafe_allow_html=True)

            for r in success_list:
                if r["file"] and os.path.exists(r["file"]):
                    dl_col1, dl_col2 = st.columns([3, 1])
                    with dl_col1:
                        st.markdown(
                            f'<div style="padding:0.4rem 0; font-size:0.85rem; color:#cbd5e1;">'
                            f'{r["name"]} — {human_size(r["size"])}</div>',
                            unsafe_allow_html=True)
                    with dl_col2:
                        with open(r["file"], "rb") as f:
                            st.download_button(
                                label="⬇️ Tải",
                                data=f,
                                file_name=Path(r["file"]).name,
                                mime=f"video/{output_format}",
                                key=f"dl_{r['part']}",
                                use_container_width=True)

        if fail_list:
            st.markdown("#### ❌ Clip Bị Lỗi")
            for r in fail_list:
                st.markdown(
                    f'<div class="error-box">❌ <b>{r["name"]}</b>: {r.get("error", "Lỗi không xác định")}</div>',
                    unsafe_allow_html=True)

        if success_list:
            st.markdown(f"""
            <div class="success-box" style="margin-top:1rem; text-align:center;">
              🎉 <b>Hoàn tất!</b> Đã tạo thành công <b>{len(success_list)}</b> clip sẵn sàng đăng TikTok / Reels / Shorts!
            </div>
            """, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)
