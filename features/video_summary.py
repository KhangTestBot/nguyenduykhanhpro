"""
Feature module: AI Video Summary (Light)
Pipeline: Upload video → Gemini phan tich → cat ghep segments → phu de
"""

import streamlit as st
import tempfile
import json
import time
import subprocess
import shutil
from pathlib import Path
from datetime import timedelta

from features.common_ui import (
    SUPPORTED_FORMATS,
    YTDLP_AVAILABLE,
    download_video_from_url,
)


def ask_gemini_for_segments(api_key, video_path, target_ratio, narration_style, target_lang, model_name):
    """Gui video cho Gemini, nhan ve segments + narration"""
    import google.generativeai as genai
    genai.configure(api_key=api_key)

    status = st.empty()
    status.info("📤 Đang tải video lên Gemini (có thể mất 1-2 phút với video dài)...")

    video_file = genai.upload_file(path=video_path)
    while video_file.state.name == "PROCESSING":
        time.sleep(10)
        video_file = genai.get_file(video_file.name)

    if video_file.state.name == "FAILED":
        return False, "Video upload failed on Gemini server"

    duration_info = ""
    try:
        if hasattr(video_file, "video_metadata") and video_file.video_metadata:
            total_sec = video_file.video_metadata.video_duration.seconds
            target_sec = int(total_sec * target_ratio)
            duration_info = (
                f"\nVideo gốc: {total_sec}s, mục tiêu tóm tắt ~{target_sec}s."
                f"\nChọn khoảng {max(3, target_sec//10)} đến {max(5, target_sec//5)} segments."
            )
    except Exception:
        pass

    style_guide = {
        "kể chuyện": "Giong van ke chuyen loi cuon, gianh cam xuc, dan dat nguoi xem.",
        "khách quan": "Giong van trung lap, khach quan, tap trung vao su kien.",
        "hài hước": "Giong van hai huoc, vui nhon, co the chem binh luan di dom.",
    }
    style_inst = style_guide.get(narration_style, style_guide["kể chuyện"])

    prompt = f"""Bạn là chuyên gia biên tập video. Hãy xem video này và:
1. Chọn ra các phân đoạn QUAN TRỌNG NHẤT ({target_ratio*100:.0f}% thời lượng gốc).
2. Bỏ qua: chào hỏi, quảng cáo, lặp ý, khoảng lặng.
3. Với mỗi đoạn, viết lời bình ({target_lang}) ngắn gọn (2-3 câu) tóm tắt nội dung.
4. {style_inst}
{duration_info}

Trả về JSON NGHIÊM NGẶT, không markdown, không text thừa:
{{"summary": "Tóm tắt 1 câu", "segments": [{{"start": 12.5, "end": 25.0, "narration": "..."}}]}}"""

    fallback_models = [
        model_name,
        "models/gemini-2.0-flash",
        "models/gemini-2.0-flash-lite",
        "models/gemini-1.5-flash",
        "models/gemini-1.5-pro",
    ]

    last_err = ""
    for attempt in fallback_models:
        try:
            status.info(f"🧠 Gemini ({attempt.split('/')[-1]}) đang phân tích video...")
            model = genai.GenerativeModel(attempt)
            resp = model.generate_content([video_file, prompt], request_options={"timeout": 300})
            text = resp.text.strip()
            break
        except Exception as e:
            last_err = str(e)
            continue
    else:
        return False, f"Tat ca models deu loi: {last_err}"

    if text.startswith("```json"):
        text = text.replace("```json\n", "").replace("\n```", "")
    elif text.startswith("```"):
        text = text.replace("```\n", "").replace("\n```", "")

    try:
        data = json.loads(text)
        if "segments" not in data or not data["segments"]:
            return False, "Gemini khong tra ve segments hop le"
        return True, data
    except json.JSONDecodeError as e:
        return False, f"Loi parse JSON: {e}\nRaw: {text[:500]}"


def cut_and_concat_video(input_path, segments, output_path, status):
    """Cat segments bang FFmpeg (stream copy cho toc do), ghep noi"""
    tmp = Path(tempfile.mkdtemp())
    seg_files = []

    try:
        for i, seg in enumerate(segments):
            start = seg["start"]
            duration = seg["end"] - start
            out = tmp / f"seg_{i:04d}.mp4"
            status.info(f"✂️ Đang cắt segment {i+1}/{len(segments)} ({duration:.0f}s)...")

            subprocess.run([
                "ffmpeg", "-y",
                "-accurate_seek",
                "-ss", str(start),
                "-t", str(duration),
                "-i", input_path,
                "-vf", "fps=30,setpts=PTS-STARTPTS",
                "-af", "asetpts=PTS-STARTPTS,aresample=48000:async=1000:first_pts=0",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
                "-c:a", "aac", "-b:a", "192k",
                str(out)
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            if out.exists():
                seg_files.append(out)

        if not seg_files:
            return False, "Khong cat duoc segment nao"

        status.info("🔗 Đang ghép nối video...")
        list_file = tmp / "list.txt"
        with open(list_file, "w") as f:
            for sf in seg_files:
                f.write(f"file '{sf.name}'\n")

        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_file), "-c", "copy", output_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        return (True, output_path) if Path(output_path).exists() else (False, "Loi ghep video")

    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)


def burn_subtitles(video_path, srt_path, output_path):
    """Dot phu de vao video"""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"subtitles='{srt_path}':force_style='FontSize=15,PrimaryColour=&H00FFFFFF,OutlineColour=&H00424242,BackColour=&H80000000,BorderStyle=3,Outline=2,MarginV=36'",
        "-c:a", "copy",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24",
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return Path(output_path).exists()


def generate_summary_srt(segments):
    """Tao SRT cho video tom tat"""
    lines = []
    offset = 0.0
    for i, seg in enumerate(segments):
        narration = seg.get("narration", "").strip()
        if not narration:
            continue
        dur = seg["end"] - seg["start"]

        def fmt(s):
            td = timedelta(seconds=s)
            ms = int(td.total_seconds() * 1000)
            h, rem = divmod(ms, 3600000)
            m, rem = divmod(rem, 60000)
            s, ms = divmod(rem, 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        lines.append(str(i + 1))
        lines.append(f"{fmt(offset)} --> {fmt(offset + dur)}")
        lines.append(narration)
        lines.append("")
        offset += dur
    return "\n".join(lines)


RATIO_PRESETS = {
    "1 phút (với video < 10p)": 0,
    "10% thời lượng gốc": 10,
    "20% thời lượng gốc": 20,
    "30% thời lượng gốc": 30,
    "50% thời lượng gốc": 50,
}


def render_video_summary_tools():
    st.markdown("""
    <div class="hero-banner">
    <div class="hero-title">🎬 AI Tóm Tắt Video</div>
    <div class="hero-subtitle">Gemini xem video → chọn cảnh hay → cắt ghép → phụ đề</div>
    <div class="badge-row">
    <span class="badge">🧠 Gemini</span>
    <span class="badge">✂️ Smart Cut</span>
    <span class="badge">📝 Phụ đề</span>
    <span class="badge">⚡ Nhẹ, nhanh</span>
    </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">🔑 Cấu Hình</div>', unsafe_allow_html=True)

    api_key = st.text_input(
        "Gemini API Key",
        type="password",
        value=os.environ.get("GEMINI_API_KEY", ""),
        placeholder="Nhap Gemini API Key..."
    )

    if "vs_api_valid" not in st.session_state:
        st.session_state.vs_api_valid = False
        st.session_state.vs_models = []
        st.session_state.vs_selected_model = None

    def check_models(api_key):
        if not api_key:
            return
        with st.spinner("Đang kiểm tra API Key..."):
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                KNOWN = [
                    "models/gemini-2.0-flash",
                    "models/gemini-2.0-flash-lite",
                    "models/gemini-1.5-flash",
                    "models/gemini-1.5-pro",
                ]
                models = []
                try:
                    for m in genai.list_models():
                        if 'generateContent' in m.supported_generation_methods:
                            if any(x in m.name.lower() for x in ['flash', 'pro']):
                                models.append(m.name)
                except Exception:
                    pass
                if not models:
                    models = KNOWN
                valid = []
                for m_name in models:
                    try:
                        genai.GenerativeModel(m_name).generate_content("hi", generation_config={"max_output_tokens": 1})
                        valid.append(m_name)
                    except Exception:
                        continue
                if valid:
                    st.session_state.vs_models = valid
                    st.session_state.vs_selected_model = valid[0]
                    st.session_state.vs_api_valid = True
                    st.success(f"✅ OK! {len(valid)} models kha dung.")
                else:
                    st.session_state.vs_api_valid = False
                    st.error("❌ Khong co model nao hoat dong.")
            except Exception as e:
                st.session_state.vs_api_valid = False
                st.error(f"❌ Loi: {e}")

    if api_key:
        c1, c2 = st.columns([3, 1])
        with c1:
            if st.button("✅ Kiem tra API Key", use_container_width=True):
                check_models(api_key)
        with c2:
            if st.session_state.vs_api_valid:
                st.success("✅ San sang")

        if st.session_state.vs_api_valid and st.session_state.vs_models:
            idx = 0
            if st.session_state.vs_selected_model in st.session_state.vs_models:
                idx = st.session_state.vs_models.index(st.session_state.vs_selected_model)
            sel = st.selectbox("🧠 Model Gemini", st.session_state.vs_models, index=idx, key="vs_model")
            st.session_state.vs_selected_model = sel

    st.markdown("---")
    input_method = st.radio("Nguồn Video", ["📂 Tai len tu may", "🔗 Link YouTube..."], horizontal=True)
    vid_file = None
    vid_url = ""
    if "📂" in input_method:
        vid_file = st.file_uploader("Chọn video", type=SUPPORTED_FORMATS)
    else:
        if not YTDLP_AVAILABLE:
            st.warning("⚠️ Can cai `pip install yt-dlp`")
        vid_url = st.text_input("Link Video", placeholder="https://www.youtube.com/watch?v=...")

    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        ratio_display = st.selectbox(
            "📏 Độ dài tóm tắt",
            list(RATIO_PRESETS.keys()),
            index=3
        )
        ratio_val = RATIO_PRESETS[ratio_display]
        target_ratio = ratio_val / 100.0 if ratio_val > 0 else 0.1

        narration_style = st.selectbox(
            "🎭 Phong cách lời bình",
            ["kể chuyện", "khách quan", "hài hước"],
            index=0
        )

    with col2:
        target_lang = st.selectbox("🌐 Ngôn ngữ lời bình", ["Tiếng Việt", "English"], index=0)
        target_lang_code = "vi" if target_lang == "Tiếng Việt" else "en"

        render_subs = st.checkbox("📝 Đốt phụ đề vào video", value=True, help="Theo SRT vao video (cham hon mot chut)")
        stream_copy = st.checkbox("⚡ Cat nhanh (stream copy)", value=False, help="Nhanh hon nhung cat khong chinh xac tuyet doi")

    st.markdown("""
    <div class="warning-box">
    ⚠️ <strong>Ban quyen:</strong> Chi dung voi video ban co quyen xu ly.
    </div>
    """, unsafe_allow_html=True)

    process = st.button(
        "🚀 Bat Dau Phan Tich & Tao Video Tom Tat",
        use_container_width=True, type="primary",
        disabled=not (api_key and st.session_state.get("vs_api_valid"))
    )

    if process:
        if not api_key or not st.session_state.get("vs_api_valid"):
            st.error("Vui long nhap va kiem tra API Key!")
            return
        if "📂" in input_method and not vid_file:
            st.error("Vui long tai video len!")
            return
        if "🔗" in input_method and not vid_url:
            st.error("Vui long nhap link!")
            return

        status = st.empty()
        prog = st.progress(0, text="Khoi tao...")

        try:
            work_dir = Path(tempfile.mkdtemp())
            vid_path = ""

            if "📂" in input_method:
                status.info("📥 Đang doc video...")
                vid_path = str(work_dir / vid_file.name)
                with open(vid_path, "wb") as f:
                    f.write(vid_file.read())
            else:
                status.info("⏳ Đang tai video tu link...")
                prog.progress(5, text="Đang tai video...")
                dl = download_video_from_url(vid_url, work_dir, status)
                if not dl["success"]:
                    status.error(f"❌ Loi tai: {dl.get('error', '')}")
                    return
                vid_path = dl["path"]
            prog.progress(10, text="Da tai xong video")

            model_name = st.session_state.get("vs_selected_model", "models/gemini-1.5-flash")
            ok, result = ask_gemini_for_segments(
                api_key, vid_path, target_ratio, narration_style, target_lang_code, model_name
            )
            if not ok:
                status.error(f"❌ {result}")
                return
            prog.progress(50, text="Gemini da phan tich xong")

            segments = result["segments"]
            summary = result.get("summary", "")

            with st.expander("📊 Ket qua phan tich tu Gemini"):
                st.markdown(f"**Tom tat:** {summary}")
                st.json(segments)

            if not segments:
                status.error("❌ Khong tim thay segment nao!")
                return

            srt_content = generate_summary_srt(segments)
            srt_path = str(work_dir / "summary.srt")
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt_content)

            prog.progress(60, text="Đang cat ghep video...")
            cut_ok, cut_result = cut_and_concat_video(vid_path, segments, str(work_dir / "concat.mp4"), status)
            if not cut_ok:
                status.error(f"❌ {cut_result}")
                return
            prog.progress(80, text="Da cat ghep xong")

            final_video = str(work_dir / "final.mp4")
            if render_subs:
                status.info("📝 Đang dot phu de...")
                burn_subtitles(str(work_dir / "concat.mp4"), srt_path, final_video)
            else:
                shutil.copy(str(work_dir / "concat.mp4"), final_video)

            if not Path(final_video).exists():
                status.error("❌ Loi tao video cuoi cung")
                return
            prog.progress(100, text="✅ Hoan tat!")

            status.success("🎉 Video tom tat da san sang!")

            with st.container():
                st.markdown("### 📥 Ket Qua")
                with open(final_video, "rb") as f:
                    st.download_button(
                        "🎬 Tai Video Tom Tat (MP4)",
                        data=f.read(),
                        file_name=f"summary_{Path(vid_path).stem}.mp4",
                        mime="video/mp4",
                        type="primary",
                        use_container_width=True
                    )
                c1, c2 = st.columns(2)
                with c1:
                    st.download_button(
                        "📝 Tai Phu De (.srt)", data=srt_content.encode(),
                        file_name=f"summary_{Path(vid_path).stem}.srt",
                        mime="text/plain", use_container_width=True
                    )
                with c2:
                    script = f"TOM TAT: {summary}\n\n" + "\n\n".join(
                        f"=== Đoan {i+1} ({seg['start']:.1f}s - {seg['end']:.1f}s) ===\n{seg['narration']}"
                        for i, seg in enumerate(segments)
                    )
                    st.download_button(
                        "📄 Tai Kich Ban (.txt)", data=script.encode(),
                        file_name=f"script_{Path(vid_path).stem}.txt",
                        mime="text/plain", use_container_width=True
                    )

        except Exception as e:
            status.error(f"❌ Loi: {str(e)}")
            import traceback
            st.code(traceback.format_exc())
        finally:
            shutil.rmtree(str(work_dir), ignore_errors=True)

    st.markdown('</div>', unsafe_allow_html=True)
