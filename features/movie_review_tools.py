"""
Feature module: Movie Review / AI Video Summary
Dedicated file for AI video analysis, highlights extraction, and summary generation.
"""

import streamlit as st
import tempfile
import json
import time
import subprocess
import traceback
import concurrent.futures
from pathlib import Path

from features.common_ui import (
    SUPPORTED_FORMATS,
    YTDLP_AVAILABLE,
    download_video_from_url,
)

def ask_gemini_for_review_segments(api_key, video_file_path, target_ratio=0.3, model_name="gemini-1.5-pro-latest"):
    import google.generativeai as genai
    
    genai.configure(api_key=api_key)
    
    video_file = genai.upload_file(path=video_file_path)
    
    while video_file.state.name == "PROCESSING":
        time.sleep(20)
        video_file = genai.get_file(video_file.name)
        
    if video_file.state.name == "FAILED":
        raise Exception("Lỗi khi xử lý video trên hệ thống AI.")
        
    duration_info = ""
    try:
        if hasattr(video_file, "video_metadata") and video_file.video_metadata:
            total_sec = video_file.video_metadata.video_duration.seconds
            target_sec = int(total_sec * target_ratio)
            min_segments = int(target_sec / 10)
            max_segments = int(target_sec / 5)
            if target_sec > 0:
                duration_info = f"\n\nTHÔNG TIN ĐỊNH LƯỢNG BẮT BUỘC:\n- Video gốc dài: {total_sec} giây.\n- Mục tiêu tóm tắt: {target_sec} giây.\n- Bạn PHẢI trích xuất một mảng JSON rất dài gồm khoảng {min_segments} đến {max_segments} phân cảnh. Đừng dừng lại quá sớm, nếu không bản tóm tắt sẽ bị hụt thời lượng!"
    except Exception:
        pass
        
    prompt = f"""
    Bạn là một AI Agent chuyên gia biên tập video (Movie Reviewer).
    Nhiệm vụ của bạn là phân tích video gốc, lọc ra các phân cảnh quan trọng nhất để tạo thành một bản tóm tắt chiếm khoảng {target_ratio*100}% thời lượng gốc.{duration_info}
    
    YÊU CẦU QUAN TRỌNG: Để nhịp điệu video hấp dẫn như các clip review trên Tiktok/Shorts, mỗi phân cảnh (segment) được chọn chỉ nên có độ dài khoảng từ 5 đến 10 giây. Tuyệt đối không chọn một phân cảnh kéo dài liên tục quá lâu.
    
    Hãy trả về KẾT QUẢ DUY NHẤT LÀ MỘT MẢNG JSON, KHÔNG CÓ BẤT KỲ VĂN BẢN NÀO KHÁC (KỂ CẢ MARKDOWN).
    Cấu trúc JSON:
    [
        {{"start": 12.5, "end": 20.0}},
        {{"start": 120.0, "end": 128.5}}
    ]
    (start và end tính bằng GIÂY).
    """
    
    model = genai.GenerativeModel(model_name=model_name)
    response = model.generate_content([video_file, prompt], request_options={"timeout": 600})
    
    text = response.text
    if text.startswith("```json"):
        text = text.replace("```json\n", "").replace("\n```", "")
    elif text.startswith("```"):
        text = text.replace("```\n", "").replace("\n```", "")
        
    segments = json.loads(text)
    return segments

def cut_and_concat_video(video_path, segments, output_path, status_placeholder):
    tmp_dir = tempfile.mkdtemp()
    cut_files = [None] * len(segments)
    
    status_placeholder.info(f"✂️ Đang cắt {len(segments)} phân cảnh (Sử dụng đa luồng siêu tốc)...")
    
    def process_segment(args):
        i, seg = args
        out_file = Path(tmp_dir) / f"part_{i}.mp4"
        start = seg['start']
        end = seg['end']
        duration = end - start
        
        cmd = [
            "ffmpeg", "-y",
            "-accurate_seek",
            "-ss", str(start),
            "-t", str(duration),
            "-i", video_path,
            "-vf", "fps=30,setpts=PTS-STARTPTS",
            "-af", "asetpts=PTS-STARTPTS,aresample=48000:async=1000:first_pts=0",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
            "-c:a", "aac", "-b:a", "192k",
            str(out_file)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if out_file.exists():
            return i, str(out_file)
        return i, None

    with concurrent.futures.ThreadPoolExecutor() as executor:
        tasks = [(i, seg) for i, seg in enumerate(segments)]
        for i, out_file in executor.map(process_segment, tasks):
            cut_files[i] = out_file
            
    cut_files = [cf for cf in cut_files if cf is not None]
            
    if not cut_files:
        raise Exception("Không thể cắt được phân cảnh nào!")
        
    status_placeholder.info("🔗 Đang ghép nối các đoạn video...")
    list_file = Path(tmp_dir) / "list.txt"
    with open(list_file, "w") as f:
        for cf in cut_files:
            f.write(f"file '{cf}'\n")
            
    concat_cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file), "-c", "copy", output_path
    ]
    subprocess.run(concat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def generate_review_srt(segments):
    import datetime
    def format_time(seconds):
        td = datetime.timedelta(seconds=seconds)
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        millis = int((seconds - total_seconds) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    lines = []
    current_offset = 0.0
    for i, seg in enumerate(segments):
        start = seg.get('start', 0)
        end = seg.get('end', 0)
        narration = seg.get('narration', '')
        duration = end - start
        
        if narration:
            lines.append(str(i + 1))
            lines.append(f"{format_time(current_offset)} --> {format_time(current_offset + duration)}")
            lines.append(narration)
            lines.append("")
            
        current_offset += duration
        
    return "\n".join(lines)

def render_movie_review_tools():
    """Renders the AI Movie Review feature tab."""
    st.markdown("""
    <div class="hero-banner">
    <div class="hero-title">🤖 AI Tóm Tắt Phim</div>
    <div class="hero-subtitle">Tự động xem, chọn lọc cảnh hay và tóm tắt thành video 15 phút kèm Subtitle</div>
    <div class="badge-row">
    <span class="badge">🧠 Gemini 1.5 Pro</span>
    <span class="badge">🎬 Smart Cut</span>
    <span class="badge">📝 Auto Sync SRT</span>
    </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">🔑 Cấu Hình Tóm Tắt</div>', unsafe_allow_html=True)
    
    api_key = st.text_input("Gemini API Key (Tóm tắt Phim)", type="password", value=os.environ.get("GEMINI_API_KEY", ""), placeholder="Nhập API Key vào đây...")
    
    force_recheck_movie = False
    if "api_key_valid_movie" not in st.session_state or st.session_state.get("current_api_key_movie") != api_key:
        force_recheck_movie = True
    elif not st.session_state.get("api_key_valid_movie") and not st.session_state.get("api_error_movie"):
        force_recheck_movie = True
        
    if force_recheck_movie:
        st.session_state["api_key_valid_movie"] = False
        st.session_state["valid_model_movie"] = None
        st.session_state["available_models_movie"] = []
        st.session_state["current_api_key_movie"] = api_key
        st.session_state["api_error_movie"] = ""
        
        if api_key:
            with st.spinner("Đang kiểm tra API Key..."):
                available_models = []
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=api_key)
                    for m in genai.list_models():
                        if 'generateContent' in m.supported_generation_methods:
                            if 'flash' in m.name.lower() or 'pro' in m.name.lower() or 'gemini' in m.name.lower():
                                available_models.append(m.name)
                except Exception:
                    pass
                    
                if not available_models:
                    available_models = ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'models/gemini-2.0-flash-exp', 'models/gemini-2.0-pro-exp-02-05']
                
                valid = False
                for m_name in available_models:
                    try:
                        test_model = genai.GenerativeModel(m_name)
                        test_model.generate_content("hello")
                        valid = True
                        break
                    except Exception:
                        continue
                
                if valid:
                    st.session_state["api_key_valid_movie"] = True
                    st.session_state["available_models_movie"] = available_models
                    st.session_state["valid_model_movie"] = available_models[-1] if available_models else None
                else:
                    st.session_state["api_error_movie"] = "Không thể kết nối với API (Sai API Key hoặc hết quota)."

    if api_key:
        if st.session_state.get("api_key_valid_movie"):
            st.success("✅ Kết nối API Gemini thành công!")
            models_list = st.session_state.get("available_models_movie", [])
            if models_list:
                default_idx = 0
                if st.session_state.get("valid_model_movie") in models_list:
                    default_idx = models_list.index(st.session_state["valid_model_movie"])
                selected = st.selectbox("🤖 Chọn Phiên bản Gemini", models_list, index=default_idx, key="movie_model_select")
                st.session_state["valid_model_movie"] = selected
        elif st.session_state.get("api_error_movie"):
            st.error(f"❌ API Key không hợp lệ hoặc lỗi kết nối: {st.session_state['api_error_movie']}")
    
    input_method = st.radio("Nguồn Video", ["Tải lên từ máy", "Tải từ Link (YouTube, TikTok...)"], horizontal=True)
    
    vid_file = None
    vid_url = ""
    if input_method == "Tải lên từ máy":
        vid_file = st.file_uploader("📂 Tải lên Video gốc (MP4, MKV...)", type=SUPPORTED_FORMATS)
    else:
        if not YTDLP_AVAILABLE:
            st.error("⚠️ Cần cài `yt-dlp` để tải video từ link")
        vid_url = st.text_input("🔗 Dán Link Video", placeholder="https://www.youtube.com/...")
        
    target_ratio = st.slider("Tỷ lệ thời lượng mong muốn so với gốc", 10, 50, 30, format="%d%%") / 100.0
    
    if st.button("🚀 Bắt Đầu Phân Tích & Tóm Tắt", use_container_width=True):
        if not api_key:
            st.error("Vui lòng nhập Gemini API Key!")
            return
        if input_method == "Tải lên từ máy" and not vid_file:
            st.error("Vui lòng tải lên video!")
            return
        if input_method == "Tải từ Link (YouTube, TikTok...)" and not vid_url:
            st.error("Vui lòng nhập Link Video!")
            return
            
        status = st.empty()
        
        try:
            tmp_dir = Path(tempfile.mkdtemp())
            vid_path = ""
            
            if input_method == "Tải lên từ máy":
                status.info("📥 Đang lưu file gốc...")
                vid_path = str(tmp_dir / vid_file.name)
                with open(vid_path, "wb") as f:
                    f.write(vid_file.read())
            else:
                status.info("⏳ Đang tải video từ Link (Vui lòng đợi)...")
                dl_result = download_video_from_url(vid_url, tmp_dir, status)
                if not dl_result["success"]:
                    status.error(f"❌ Lỗi tải video: {dl_result.get('error', 'Lỗi không xác định')}")
                    return
                vid_path = dl_result["path"]
                
            vid_filename = Path(vid_path).name
                
            status.info("🧠 AI đang xem và phân tích video (Có thể mất 1-3 phút)...")
            valid_model = st.session_state.get("valid_model_movie", "models/gemini-1.5-pro")
            segments = ask_gemini_for_review_segments(api_key, vid_path, target_ratio, model_name=valid_model)
            
            with st.expander("📊 Xem các phân cảnh AI đã chọn"):
                st.json(segments)
            
            status.info("✂️ Đang cắt ghép video tóm tắt...")
            out_vid_path = str(tmp_dir / ("review_" + vid_filename))
            cut_and_concat_video(vid_path, segments, out_vid_path, status)
            
            status.info("📝 Đang tạo kịch bản thuyết minh (SRT)...")
            final_srt_content = generate_review_srt(segments)
            
            status.success("✅ Hoàn tất tóm tắt!")
            
            st.markdown("### 📥 Kết quả Tóm Tắt")
            
            with open(out_vid_path, "rb") as f:
                v_bytes = f.read()
            st.download_button(
                "🎬 Tải Video Tóm Tắt (MP4)",
                data=v_bytes,
                file_name="review_" + vid_filename,
                mime="video/mp4",
                type="primary",
                use_container_width=True
            )
            
            if final_srt_content:
                st.download_button(
                    "📝 Tải Kịch Bản Thuyết Minh (.srt)",
                    data=final_srt_content.encode('utf-8'),
                    file_name="review_script_" + Path(vid_filename).stem + ".srt",
                    mime="text/plain",
                    use_container_width=True
                )
                st.text_area("Xem trước Phụ đề Thuyết Minh", value=final_srt_content, height=200)
                
        except Exception as e:
            status.error(f"❌ Lỗi: {str(e)}")
            st.code(traceback.format_exc())
            
    st.markdown('</div>', unsafe_allow_html=True)
