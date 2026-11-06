"""
Feature module: Auto-Cut & CapCut Timeline Integration
Dedicated tool for:
1. Converting entire SRT subtitles (or CapCut Text tracks) into synced Voiceover ('Cô Gái Hoạt Ngôn').
2. Directly hacking into CapCut Project Drafts and slicing long timeline videos into 14-minute segments.
3. Lossless 14-minute video splitting from local files/URLs.
4. Syncing image sequences into CapCut Desktop draft timelines based on SRT.
"""

import streamlit as st
import tempfile
import shutil
import subprocess
import zipfile
import math
import json
import os
import time
from pathlib import Path

import importlib
import utils.capcut_draft_editor as capcut_draft_editor
import utils.srt_tts_syncer as srt_tts_syncer
importlib.reload(capcut_draft_editor)
importlib.reload(srt_tts_syncer)

from features.common_ui import (
    YTDLP_AVAILABLE,
    download_video_from_url,
    human_size,
    safe_filename,
)
from utils.capcut_draft_editor import (
    get_mac_capcut_projects,
    split_capcut_project_into_chunks,
    inject_timeline_to_draft,
    sync_existing_segments_to_srt,
)
from utils.srt_tts_syncer import (
    generate_synchronized_voiceover,
    convert_srt_file_to_subtitles_list,
    extract_subtitles_from_capcut_draft,
    inject_audio_track_to_capcut_draft,
)
from utils.capcut_tts_wrapper import get_available_voices

def get_video_duration_seconds(video_path: Path) -> float:
    """Lấy tổng thời lượng video bằng ffprobe."""
    cmd_probe = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path)
    ]
    try:
        res = subprocess.run(cmd_probe, capture_output=True, text=True)
        return float(res.stdout.strip())
    except Exception:
        return 0.0


def split_video_lossless(
    input_video_path: Path,
    output_dir: Path,
    chunk_minutes: float = 14.0,
    progress_callback=None
) -> list:
    """
    Cắt video dài thành các đoạn cố định (mặc định 14 phút) bằng Stream Copy (-c copy).
    Cắt siêu tốc (chỉ mất 1-3 giây cho video 2 tiếng) và giữ nguyên 100% chất lượng gốc.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    total_duration = get_video_duration_seconds(input_video_path)

    if total_duration <= 0:
        raise Exception("Không thể đọc thời lượng của file video này.")

    chunk_seconds = int(chunk_minutes * 60)
    num_parts = int(math.ceil(total_duration / chunk_seconds))
    output_files = []

    stem = safe_filename(input_video_path.stem)
    ext = input_video_path.suffix.lower() if input_video_path.suffix else ".mp4"
    if ext not in [".mp4", ".mov", ".mkv", ".webm"]:
        ext = ".mp4"

    start_time_proc = time.time()

    for i in range(num_parts):
        start_sec = i * chunk_seconds
        part_num = i + 1

        st_m = int(start_sec // 60)
        st_s = int(start_sec % 60)
        end_total_sec = min(total_duration, (start_sec + chunk_seconds))
        end_m = int(end_total_sec // 60)
        end_s = int(end_total_sec % 60)

        out_filename = f"[{part_num:02d}]_{stem}_{st_m:02d}p{st_s:02d}s-{end_m:02d}p{end_s:02d}s{ext}"
        out_path = output_dir / out_filename

        if progress_callback:
            pct = int((i / num_parts) * 100)
            progress_callback(pct, f"⚡ Đang cắt phần {part_num}/{num_parts} ({st_m}p{st_s:02d}s -> {end_m}p{end_s:02d}s)...")

        cmd_cut = [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-i", str(input_video_path),
            "-t", str(chunk_seconds),
            "-c", "copy",
            "-map", "0",
            str(out_path)
        ]
        res = subprocess.run(cmd_cut, capture_output=True)

        if res.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
            cmd_cut_fallback = [
                "ffmpeg", "-y",
                "-ss", str(start_sec),
                "-i", str(input_video_path),
                "-t", str(chunk_seconds),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-c:a", "aac",
                str(out_path)
            ]
            subprocess.run(cmd_cut_fallback, capture_output=True)

        if out_path.exists() and out_path.stat().st_size > 0:
            output_files.append({
                "path": str(out_path),
                "filename": out_filename,
                "part": part_num,
                "time_range": f"{st_m:02d}:{st_s:02d} - {end_m:02d}:{end_s:02d}",
                "size": out_path.stat().st_size
            })

    if progress_callback:
        elapsed = time.time() - start_time_proc
        progress_callback(100, f"✅ Đã cắt xong {len(output_files)} đoạn chỉ trong {elapsed:.1f} giây!")

    return output_files


def create_zip_archive(files_list: list, zip_path: Path) -> Path:
    """Đóng gói tất cả file video đã cắt thành 1 file ZIP duy nhất."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for item in files_list:
            p = Path(item["path"])
            if p.exists():
                zipf.write(p, arcname=p.name)
    return zip_path


def render_autocut_tools():
    """Renders the 'Auto-Cut' feature tab."""
    st.markdown("""
    <div class="hero-banner">
    <div class="hero-title">✂️ Auto-Cut & Tích Hợp Dự Án CapCut</div>
    <div class="hero-subtitle">Biến đổi toàn bộ SRT thành Giọng Nói Cô Gái Hoạt Ngôn & Tự động Cắt Timeline CapCut 14 phút</div>
    <div class="badge-row">
    <span class="badge">🎙️ SRT -> Giọng 'Cô Gái Hoạt Ngôn'</span>
    <span class="badge">🎯 Cắt Trực Tiếp Timeline CapCut 14p</span>
    <span class="badge">⚡ Khớp 100% Thời Gian Phụ Đề</span>
    <span class="badge">🛡️ Bơm Trực Tiếp Vào Dự Án CapCut</span>
    </div>
    </div>
    """, unsafe_allow_html=True)

    tab_srt_tts, tab_draft_cut, tab_timeline_srt = st.tabs([
        "🎙️ Chuyển SRT Thành Giọng 'Cô Gái Hoạt Ngôn'",
        "🎯 Can Thiệp Dự Án CapCut (Cắt Timeline 14 Phút)",
        "🖼️ Đồng Bộ Ảnh & SRT Vào CapCut"
    ])

    # ─── TAB 1: CHUYỂN SRT THÀNH GIỌNG "CÔ GÁI HOẠT NGÔN" ────────────────────
    with tab_srt_tts:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">📄 Nguồn Phụ Đề (SRT hoặc Từ Dự Án CapCut)</div>', unsafe_allow_html=True)

        srt_source_type = st.radio(
            "Chọn nguồn phụ đề:",
            ["📂 Tải File Phụ Đề (.srt) Lên", "📁 Lấy Phụ Đề Đang Có Sẵn Trong Dự Án CapCut"],
            horizontal=True,
            key="srt_tts_source_type"
        )

        subtitles_to_process = []
        uploaded_srt_file = None
        selected_project_for_sub = None
        drafts = get_mac_capcut_projects()

        if srt_source_type.startswith("📂"):
            uploaded_srt_file = st.file_uploader(
                "Kéo thả file Phụ đề SRT vào đây:",
                type=["srt"],
                key="srt_tts_file_uploader"
            )
        else:
            if not drafts:
                st.warning("⚠️ Không tìm thấy Dự Án CapCut nào trên máy.")
            else:
                draft_options = [f"📁 {d['name']} — ({Path(d['path']).parent.name})" for d in drafts]
                sel_idx = st.selectbox(
                    "Chọn Dự án CapCut có chứa phụ đề:",
                    range(len(draft_options)),
                    format_func=lambda x: draft_options[x],
                    key="srt_tts_draft_select"
                )
                selected_project_for_sub = drafts[sel_idx]

        st.markdown('<br><div class="card-title">🎭 Chọn Giọng Đọc AI (Có sẵn: Wealthy Daddy, Cô Gái Hoạt Ngôn,...)</div>', unsafe_allow_html=True)
        
        col_lang, col_v1, col_v2 = st.columns([2, 3, 3])

        with col_lang:
            lang_options = [
                "🇻🇳 Tiếng Việt (Vietnamese)",
                "🇺🇸 Tiếng Anh (English)",
                "🌐 Tất Cả Ngôn Ngữ",
                "🇨🇳 Tiếng Trung",
                "🇯🇵 Tiếng Nhật"
            ]
            chosen_lang_label = st.selectbox(
                "🌐 Ngôn Ngữ:",
                lang_options,
                index=0,
                key="srt_tts_lang_filter"
            )
            lang_code_map = {
                "🇻🇳 Tiếng Việt (Vietnamese)": "vi",
                "🇺🇸 Tiếng Anh (English)": "en",
                "🌐 Tất Cả Ngôn Ngữ": "all",
                "🇨🇳 Tiếng Trung": "zh",
                "🇯🇵 Tiếng Nhật": "ja"
            }
            sel_lang = lang_code_map.get(chosen_lang_label, "vi")

        # Danh sách giọng đọc theo ngôn ngữ đã chọn
        all_voices = get_available_voices(lang_filter=sel_lang)
        if not all_voices:
            all_voices = get_available_voices(lang_filter="all")

        # Tìm index mặc định (Cô Gái Hoạt Ngôn nếu chọn Tiếng Việt, hoặc Wealthy Daddy nếu chọn tiếng Anh)
        default_voice_idx = 0
        for idx, v in enumerate(all_voices):
            v_name = v.get("name", "")
            v_id = v.get("id", "")
            if sel_lang == "vi" and ("Cô Gái Hoạt Ngôn" in v_name or v_id == "BV074_streaming" or "hoat ngon" in v_name.lower()):
                default_voice_idx = idx
                break
            elif sel_lang == "en" and ("Wealthy Daddy" in v_name or "philosopher" in v_id or "adam" in v_id):
                default_voice_idx = idx
                break

        with col_v1:
            voice_names = [v["name"] for v in all_voices]
            chosen_voice_idx = st.selectbox(
                "Chọn Giọng Đọc CapCut:",
                range(len(voice_names)),
                index=default_voice_idx,
                format_func=lambda x: voice_names[x],
                key="srt_tts_voice_choice"
            )
            chosen_voice = all_voices[chosen_voice_idx]

        with col_v2:
            auto_inject_to_capcut = st.checkbox(
                "🎬 Bơm trực tiếp Track Giọng Đọc vào Project CapCut",
                value=True,
                help="Tự động thêm luồng âm thanh đã tạo thành 1 Track Audio mới trên Timeline CapCut của bạn!"
            )

        if auto_inject_to_capcut and drafts:
            draft_inject_options = [f"📁 {d['name']}" for d in drafts]
            chosen_inject_idx = st.selectbox(
                "Chọn Dự án CapCut để bơm Track Giọng Đọc vào:",
                range(len(draft_inject_options)),
                format_func=lambda x: draft_inject_options[x],
                key="srt_tts_inject_draft_target"
            )
            target_inject_draft_path = drafts[chosen_inject_idx]["path"]
        else:
            target_inject_draft_path = None

        if st.button("🚀 Bắt Đầu Chuyển Toàn Bộ SRT Thành Giọng Đọc Ngay", use_container_width=True, type="primary", key="btn_run_srt_to_tts"):
            # 1. Trích xuất phụ đề
            subs_list = []
            stem_name = "Voiceover"

            if srt_source_type.startswith("📂"):
                if not uploaded_srt_file:
                    st.warning("Vui lòng tải lên file SRT trước!")
                else:
                    temp_srt_path = Path(tempfile.gettempdir()) / f"input_{int(time.time())}.srt"
                    with open(temp_srt_path, "wb") as f:
                        f.write(uploaded_srt_file.getbuffer())
                    subs_list = convert_srt_file_to_subtitles_list(temp_srt_path)
                    stem_name = safe_filename(uploaded_srt_file.name.replace(".srt", ""))
            else:
                if not selected_project_for_sub:
                    st.warning("Vui lòng chọn Dự án CapCut!")
                else:
                    subs_list = extract_subtitles_from_capcut_draft(selected_project_for_sub["path"])
                    stem_name = safe_filename(selected_project_for_sub["name"])

            if not subs_list:
                st.error("❌ Không tìm thấy phụ đề nào để xử lý. Vui lòng kiểm tra lại file SRT hoặc Track Text trong CapCut!")
            else:
                progress_bar = st.progress(0)
                status_box = st.empty()

                def update_tts_progress(pct, msg):
                    progress_bar.progress(min(100, max(0, pct)))
                    status_box.info(msg)

                out_audio_dir = Path("output_voiceovers") / f"voice_{int(time.time())}"
                out_audio_dir.mkdir(parents=True, exist_ok=True)
                out_mp3_path = out_audio_dir / f"{stem_name}_Voice_CoGaiHoatNgon.mp3"

                success, res_path_or_err = generate_synchronized_voiceover(
                    subtitles_list=subs_list,
                    output_mp3_path=out_mp3_path,
                    voice_type=chosen_voice["id"],
                    resource_id=chosen_voice.get("resource_id", "7102355709945188865"),
                    progress_callback=update_tts_progress
                )

                status_box.empty()
                progress_bar.empty()

                if success:
                    st.session_state["srt_tts_result_path"] = res_path_or_err
                    st.session_state["srt_tts_total_cues"] = len(subs_list)
                    st.session_state["srt_tts_title"] = stem_name

                    # Nếu người dùng chọn bơm vào CapCut
                    if auto_inject_to_capcut and target_inject_draft_path:
                        inj_ok, inj_msg = inject_audio_track_to_capcut_draft(
                            draft_json_path=target_inject_draft_path,
                            audio_file_path=res_path_or_err,
                            track_name=f"Voice_{chosen_voice['name'][:15]}"
                        )
                        if inj_ok:
                            st.session_state["srt_tts_inject_msg"] = inj_msg
                        else:
                            st.session_state["srt_tts_inject_msg"] = f"⚠️ Không thể bơm vào CapCut: {inj_msg}"

                    st.success(f"🎉 Đã chuyển đổi thành công **{len(subs_list)} câu phụ đề** thành Giọng đọc `{chosen_voice['name']}`!")
                    st.balloons()
                else:
                    st.error(f"❌ Thất bại: {res_path_or_err}")

        # Hiển thị kết quả TTS
        if st.session_state.get("srt_tts_result_path"):
            res_audio = st.session_state["srt_tts_result_path"]
            tot_cues = st.session_state.get("srt_tts_total_cues", 0)
            tit_str = st.session_state.get("srt_tts_title", "Voiceover")
            inj_msg = st.session_state.get("srt_tts_inject_msg")

            st.markdown("<hr style='border-color: rgba(255,255,255,0.1); margin: 25px 0;'>", unsafe_allow_html=True)
            st.markdown(f'<div class="card-title">🎧 Kết Quả Giọng Đọc Đồng Bộ: {tit_str} ({tot_cues} câu)</div>', unsafe_allow_html=True)

            if inj_msg:
                st.info(f"🎬 **Tích hợp CapCut:** {inj_msg}")

            if Path(res_audio).exists():
                st.audio(res_audio)
                a_size = Path(res_audio).stat().st_size
                with open(res_audio, "rb") as af:
                    st.download_button(
                        label=f"📥 TẢI FILE ÂM THANH LỒNG TIẾNG MP3 ({human_size(a_size)})",
                        data=af.read(),
                        file_name=Path(res_audio).name,
                        mime="audio/mp3",
                        use_container_width=True,
                        type="primary"
                    )

        st.markdown('</div>', unsafe_allow_html=True)

    # ─── TAB 2: CAN THIỆP TRỰC TIẾP DỰ ÁN CAPCUT ──────────────────────────────
    with tab_draft_cut:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">📂 Chọn Dự Án CapCut Trên Máy</div>', unsafe_allow_html=True)

        if not drafts:
            st.warning("⚠️ Không tìm thấy Dự Án CapCut nào trên máy. Vui lòng mở CapCut và tạo 1 Project trước.")
        else:
            draft_options = [f"📁 {d['name']} — ({Path(d['path']).parent.name})" for d in drafts]
            selected_draft_idx = st.selectbox(
                "Chọn Dự án CapCut muốn cắt video:",
                range(len(draft_options)),
                format_func=lambda x: draft_options[x],
                key="capcut_split_draft_select"
            )
            selected_draft = drafts[selected_draft_idx]
            selected_draft_path = selected_draft["path"]

            try:
                with open(selected_draft_path, "r", encoding="utf-8") as f:
                    draft_data = json.load(f)

                v_tracks = [t for t in draft_data.get("tracks", []) if t.get("type") == "video"]
                total_segs = sum(len(t.get("segments", [])) for t in v_tracks)
                max_dur_sec = draft_data.get("duration", 0) / 1000000.0

                dur_h = int(max_dur_sec // 3600)
                dur_m = int((max_dur_sec % 3600) // 60)
                dur_s = int(max_dur_sec % 60)
                dur_str = f"{dur_h} giờ {dur_m} phút {dur_s} giây" if dur_h > 0 else f"{dur_m} phút {dur_s} giây"

                st.info(f"📊 **Thông tin Timeline Dự án:** Tổng thời lượng: `{dur_str}` | Số phân đoạn hiện tại: `{total_segs}` đoạn.")
            except Exception:
                pass

            st.markdown('<br><div class="card-title">⚙️ Cấu Hình Cắt Phân Đoạn Timeline</div>', unsafe_allow_html=True)
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                target_chunk_mins = st.number_input(
                    "Thời lượng tối đa mỗi phân đoạn (Phút):",
                    min_value=1.0,
                    max_value=30.0,
                    value=14.0,
                    step=0.5,
                    key="capcut_split_chunk_mins",
                    help="Mặc định là 14 phút. Bất kỳ đoạn video nào trên Timeline CapCut dài hơn 14 phút sẽ được tự động chia nhỏ thành các đoạn liền kề <= 14 phút."
                )
            with col_d2:
                split_audio_tracks = st.checkbox(
                    "Cắt đồng thời cả Track Âm thanh (Audio Tracks)",
                    value=True,
                    key="capcut_split_audio_tracks"
                )

            st.markdown("""
            > [!TIP]
            > **Hướng dẫn thực hiện:**
            > 1. Hãy lưu hoặc **tắt phần mềm CapCut** trước khi bấm nút bên dưới để tránh CapCut ghi đè lại file cũ.
            > 2. Bấm nút **🚀 Cắt Timeline CapCut Thành Các Đoạn 14 Phút**.
            > 3. Mở lại CapCut -> Vào dự án -> Bạn sẽ thấy toàn bộ video dài 2–3 tiếng đã được cắt thành từng đoạn 14 phút gọn gàng!
            > 4. Click chuột phải vào từng đoạn 14 phút -> Chọn **Tách giọng nói** (Bỏ lời / Giữ lời) hoàn toàn không bị giới hạn!
            """)

            if st.button("🚀 Cắt Timeline CapCut Thành Các Đoạn 14 Phút Ngay", use_container_width=True, type="primary", key="btn_split_capcut_timeline"):
                with st.spinner("Đang can thiệp và cắt phân đoạn trên Timeline CapCut..."):
                    success, msg = split_capcut_project_into_chunks(
                        draft_json_path=selected_draft_path,
                        chunk_minutes=target_chunk_mins,
                        split_all_tracks=split_audio_tracks
                    )

                    if success:
                        st.success(msg)
                        st.balloons()
                        st.markdown("""
                        ### 🎬 Các bước tiếp theo trong CapCut:
                        1. Mở phần mềm **CapCut Desktop** lên.
                        2. Nhấp vào Dự án bạn vừa xử lý.
                        3. Nhìn xuống thanh Timeline: Video đã được chia thành từng đoạn **14 phút** hoàn hảo.
                        4. **Chuột phải** vào từng đoạn -> Chọn **Tách giọng nói** -> Chọn **Bỏ lời** hoặc **Giữ lời**! 🚀
                        """)
                    else:
                        st.error(msg)

        st.markdown('</div>', unsafe_allow_html=True)
    # ─── TAB 3: ĐỒNG BỘ ẢNH & SRT VÀO CAPCUT ─────────────────────────────────
    with tab_timeline_srt:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">✂️ Đồng Bộ Ảnh & SRT Vào Project CapCut</div>', unsafe_allow_html=True)
        st.markdown('<div style="margin-bottom: 16px; color: #a1a1aa; font-size: 13px; background: rgba(255,255,255,0.03); padding: 8px 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.08);">✨ <b>Hiệu ứng Ken Burns tự động:</b> Mỗi bức ảnh khi đồng bộ sẽ tự động <b>zoom từ từ 5% – 10%</b> kết hợp <b>Pan trôi ngẫu nhiên (Trái / Phải / Trên / Dưới)</b> mượt mà bằng hệ thống Keyframe của CapCut.</div>', unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown('<div class="card-title">📄 Tải Lên Phụ Đề (.srt)</div>', unsafe_allow_html=True)
            srt_file = st.file_uploader("Kéo thả file SRT", type=["srt"], key="capcut_srt_uploader")

        with col2:
            st.markdown('<div class="card-title">🎵 Tải Lên Âm Thanh (Tùy chọn)</div>', unsafe_allow_html=True)
            audio_file = st.file_uploader("Kéo thả file Audio (.mp3, .wav) - Khuyên dùng để ghép thủ công", type=["mp3", "wav", "m4a"], key="capcut_audio_uploader")

        st.markdown('<br><div class="card-title">🖼️ Nguồn Hình Ảnh</div>', unsafe_allow_html=True)
        img_source = st.radio(
            "Chọn hành động cho hình ảnh:",
            ["Đồng bộ hình ảnh đã có sẵn trên Timeline CapCut (Khuyên dùng)", "Chèn thêm ảnh từ thư mục google_flow_output", "Tải lên danh sách ảnh mới"],
            key="capcut_img_source"
        )

        uploaded_images = []
        if img_source == "Tải lên danh sách ảnh mới":
            uploaded_images = st.file_uploader("Tải lên danh sách ảnh (Chọn nhiều file)", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True, key="capcut_images_uploader")

        st.markdown('<br><div class="card-title">✂️ Đích đến CapCut</div>', unsafe_allow_html=True)

        if not drafts:
            st.warning("⚠️ Không tìm thấy Project CapCut nào trên máy. Vui lòng mở CapCut và tạo 1 Project mới trước.")
            st.info("Lưu ý: CapCut bản Desktop trên máy Mac thường lưu Project ở ~/Movies/CapCut/User Data/Projects")
        else:
            draft_options = [f"{d['name']} ({d['path']})" for d in drafts]
            selected_draft_idx = st.selectbox("Chọn Project CapCut để bơm dữ liệu:", range(len(draft_options)), format_func=lambda x: draft_options[x], key="capcut_draft_select")
            selected_draft_path = drafts[selected_draft_idx]["path"]

            insert_mode = "main_track"
            if img_source != "Đồng bộ hình ảnh đã có sẵn trên Timeline CapCut (Khuyên dùng)":
                insert_mode_ui = st.radio("Vị trí chèn Timeline:", ["Tạo Track Video mới ở trên cùng (Khuyên dùng)", "Nối tiếp vào Track Video chính"], key="capcut_insert_mode")
                insert_mode = "new_track" if "Tạo Track" in insert_mode_ui else "main_track"

            if st.button("🚀 Bơm Dữ Liệu Vào CapCut", use_container_width=True, key="capcut_inject_btn"):
                if not srt_file:
                    st.error("Vui lòng tải lên file phụ đề SRT!")
                elif img_source == "Tải lên danh sách ảnh mới" and not uploaded_images:
                    st.error("Vui lòng tải lên ít nhất 1 hình ảnh!")
                else:
                    with st.spinner("Đang hack vào tim CapCut... (Vui lòng tắt phần mềm CapCut trước khi ấn)"):
                        temp_dir = Path(tempfile.mkdtemp())
                        try:
                            srt_path = temp_dir / "input.srt"
                            with open(srt_path, "wb") as f:
                                f.write(srt_file.getbuffer())

                            if img_source == "Đồng bộ hình ảnh đã có sẵn trên Timeline CapCut (Khuyên dùng)":
                                success, result = sync_existing_segments_to_srt(
                                    draft_json_path=selected_draft_path,
                                    srt_path=str(srt_path)
                                )
                            else:
                                images_dir = str(temp_dir / "images")
                                os.makedirs(images_dir, exist_ok=True)

                                image_paths = []
                                if img_source == "Chèn thêm ảnh từ thư mục google_flow_output":
                                    import glob
                                    src_images = glob.glob("google_flow_output/*.*")
                                    for src in src_images:
                                        if src.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                                            dest = os.path.join(images_dir, os.path.basename(src))
                                            shutil.copy(src, dest)
                                            image_paths.append(os.path.abspath(dest))
                                else:
                                    for idx, img_file in enumerate(uploaded_images):
                                        img_path = os.path.join(images_dir, f"{idx:04d}_{img_file.name}")
                                        with open(img_path, "wb") as f:
                                            f.write(img_file.getbuffer())
                                        image_paths.append(os.path.abspath(img_path))

                                image_paths.sort()

                                success, result = inject_timeline_to_draft(
                                    draft_json_path=selected_draft_path,
                                    srt_path=str(srt_path),
                                    images=image_paths,
                                    insert_mode=insert_mode
                                )

                            if success:
                                st.success(result)
                                st.balloons()
                                st.info("✅ Xong! Bây giờ bạn hãy mở phần mềm CapCut lên, vào Project đó và tận hưởng thành quả nhé!")
                            else:
                                st.error(f"Thất bại: {result}")

                        finally:
                            shutil.rmtree(temp_dir, ignore_errors=True)

        st.markdown('</div>', unsafe_allow_html=True)
