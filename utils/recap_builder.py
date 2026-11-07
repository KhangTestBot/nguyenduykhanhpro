"""
Core Engine: AI Video Recap & Highlight Storyteller Studio.
Analyzes input video/link, extracts key climax/turning point scenes with strict visual grounding,
writes an engaging storytelling voiceover script, cuts clips in parallel with frame-accurate sync,
and synthesizes complete recap videos with AI voiceover and CapCut Draft support.
"""

import os
import re
import json
import time
import math
import shutil
import tempfile
import subprocess
import concurrent.futures
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Tuple
import google.generativeai as genai

from utils.capcut_stt_wrapper import transcribe_audio_to_srt
from utils.capcut_tts_wrapper import generate_tts


def get_ffmpeg_cmd() -> str:
    """Trả về đường dẫn thực thi FFmpeg ưu tiên bản có đầy đủ libfreetype, drawtext và libass."""
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass
    return shutil.which("ffmpeg") or "ffmpeg"


ffmpeg_exe = get_ffmpeg_cmd()


def get_system_font(font_type: str = "bold") -> str:
    """Trả về đường dẫn font chữ hệ thống hỗ trợ đầy đủ tiếng Việt cho FFmpeg drawtext."""
    if font_type == "condensed":
        candidates = [
            "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/Library/Fonts/Arial Unicode.ttf"
        ]
    elif font_type == "black":
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial Black.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/Library/Fonts/Arial Unicode.ttf"
        ]
    else:
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/Library/Fonts/Arial Unicode.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf"
        ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return ""


def get_video_duration(video_path: Path) -> float:
    """Lấy thời lượng chính xác của video bằng ffprobe."""
    ffprobe_exe = shutil.which("ffprobe") or "ffprobe"
    cmd = [
        ffprobe_exe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path)
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        return float(res.stdout.strip())
    except Exception:
        return 0.0


def parse_time_to_seconds(val, default: float = 0.0) -> float:
    """Chuyển đổi linh hoạt chuỗi mm:ss, hh:mm:ss hoặc số giây sang float."""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip()
    if not val_str:
        return default
    if ":" in val_str:
        parts = val_str.split(":")
        try:
            if len(parts) == 2:
                return float(parts[0]) * 60.0 + float(parts[1])
            elif len(parts) == 3:
                return float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
        except ValueError:
            pass
    try:
        return float(val_str)
    except ValueError:
        return default


def format_seconds_to_mmss(seconds: float) -> str:
    """Định dạng giây sang MM:SS hoặc HH:MM:SS."""
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def create_lightweight_ai_proxy(video_path: Path, output_proxy_path: Path) -> Path:
    """
    Tạo nhanh bản video proxy siêu nhẹ giữ nguyên 100% timeline gốc (mốc giây chính xác tuyệt đối)
    để gửi lên Gemini File API với tốc độ cực nhanh, tối ưu đặc biệt cho phim dài 1.5 - 3 tiếng.
    (Khi xuất video Master ở Bước 2, hệ thống vẫn cắt từ file gốc 1080p 30fps sắc nét).
    """
    ffmpeg_exe = get_ffmpeg_cmd()
    dur = get_video_duration(video_path)
    # Gemini xử lý chuẩn ở 1-2 FPS; giảm FPS trên bản Proxy cho phim dài giúp nén phim 2 tiếng chỉ mất ~30 giây!
    if dur > 1800:  # Phim dài > 30 phút (ví dụ 1.5 - 3 tiếng)
        vf_str = "fps=2,scale='min(426,iw)':-2:flags=fast_bilinear,pad=ceil(iw/2)*2:ceil(ih/2)*2"
        audio_br = "32k"
    elif dur > 600:
        vf_str = "fps=4,scale='min(480,iw)':-2:flags=fast_bilinear,pad=ceil(iw/2)*2:ceil(ih/2)*2"
        audio_br = "40k"
    else:
        vf_str = "scale='min(480,iw)':-2:flags=fast_bilinear,pad=ceil(iw/2)*2:ceil(ih/2)*2"
        audio_br = "48k"

    cmd = [
        ffmpeg_exe, "-y",
        "-i", str(video_path),
        "-vf", vf_str,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "33",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", audio_br,
        "-ac", "1",
        "-ar", "16000",
        "-movflags", "+faststart",
        "-threads", "0",
        str(output_proxy_path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if output_proxy_path.exists() and output_proxy_path.stat().st_size > 1000:
            return output_proxy_path
    except Exception:
        pass
    return video_path


def pick_active_api_key(api_key_input: str) -> str:
    """Tự động phân tách và xoay vòng nếu người dùng nhập nhiều API Key (cách nhau bởi dấu phẩy)."""
    if not api_key_input:
        return ""
    keys = [k.strip() for k in re.split(r'[,;\n]+', api_key_input) if k.strip()]
    import random
    return random.choice(keys) if keys else api_key_input.strip()


def generate_segment_thumbnails(video_path: Path, segments: list, output_dir: Path) -> list:
    """
    Trích xuất song song ảnh thumbnail khung hình đại diện cho từng phân cảnh highlight
    tại thời điểm start_sec để người dùng xem trước và kiểm tra độ khớp với lời kịch bản.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = get_ffmpeg_cmd()

    def extract_one_thumb(idx_seg):
        i, seg = idx_seg
        st_sec = float(seg.get("start_sec", 0.0))
        # Lấy khung hình tại start_sec + 0.3s (tránh khung hình đen chuyển cảnh)
        sample_time = max(0.0, st_sec + 0.3)
        thumb_file = output_dir / f"thumb_seg_{i:03d}.jpg"
        if not thumb_file.exists() or thumb_file.stat().st_size == 0:
            cmd = [
                ffmpeg_exe, "-y", "-nostdin",
                "-ss", str(sample_time),
                "-accurate_seek",
                "-i", str(video_path),
                "-frames:v", "1",
                "-update", "1",
                "-q:v", "3",
                "-vf", "scale='min(400,iw)':-2",
                str(thumb_file)
            ]
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=15)
            except Exception:
                pass

        if thumb_file.exists() and thumb_file.stat().st_size > 0:
            seg["thumb_path"] = str(thumb_file)
        else:
            seg["thumb_path"] = ""
        return i, seg

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as ex:
        results = list(ex.map(extract_one_thumb, enumerate(segments)))

    return [r[1] for r in sorted(results, key=lambda x: x[0])]


def create_circular_logo_badge(logo_input_path: Path, output_png_path: Path, size: int = 116) -> Optional[Path]:
    """
    Chuyển đổi ảnh Logo/Avatar kênh bất kỳ thành huy hiệu tròn (Circular Badge) có viền đôi sắc nét
    chuẩn phong cách góc trái-trên của kênh 'Não Động Review' để đính lên video.
    """
    try:
        from PIL import Image, ImageDraw, ImageOps
        img = Image.open(logo_input_path).convert("RGBA")
        # Crop vuông ở tâm và resize mượt
        img = ImageOps.fit(img, (size, size), method=Image.Resampling.LANCZOS)

        # Tạo mask tròn khử răng cưa (supersampling 4x)
        scale = 4
        big_sz = size * scale
        mask = Image.new("L", (big_sz, big_sz), 0)
        draw_m = ImageDraw.Draw(mask)
        draw_m.ellipse((8 * scale, 8 * scale, big_sz - 8 * scale, big_sz - 8 * scale), fill=255)
        mask = mask.resize((size, size), Image.Resampling.LANCZOS)

        # Tạo nền huy hiệu tròn có viền cam đào / vàng hồng + viền trắng chuẩn Não Động Review
        badge = Image.new("RGBA", (big_sz, big_sz), (0, 0, 0, 0))
        draw_b = ImageDraw.Draw(badge)
        # Vòng ngoài màu cam san hô ấm (Coral/Salmon border)
        draw_b.ellipse((2, 2, big_sz - 2, big_sz - 2), fill=(242, 139, 130, 245))
        # Vòng nhẫn trắng tinh tế bên trong
        draw_b.ellipse((5 * scale, 5 * scale, big_sz - 5 * scale, big_sz - 5 * scale), fill=(255, 248, 231, 255))
        badge = badge.resize((size, size), Image.Resampling.LANCZOS)

        badge.paste(img, (0, 0), mask)
        output_png_path.parent.mkdir(parents=True, exist_ok=True)
        badge.save(output_png_path, format="PNG")
        if output_png_path.exists() and output_png_path.stat().st_size > 100:
            return output_png_path
    except Exception:
        pass
    return None


def parse_srt_entries(srt_text: str) -> List[Dict[str, Any]]:
    """Phân tích nội dung file phụ đề .SRT hoặc .VTT thành danh sách các câu thoại có mốc giây."""
    if not srt_text or not srt_text.strip():
        return []
    entries = []
    blocks = re.split(r'\n\s*\n', srt_text.strip())
    time_pat = re.compile(r'(\d{1,2}:\d{2}:\d{2}[.,]\d+|\d{1,2}:\d{2}[.,]\d+)\s*-->\s*(\d{1,2}:\d{2}:\d{2}[.,]\d+|\d{1,2}:\d{2}[.,]\d+)')
    for b in blocks:
        lines = [ln.strip() for ln in b.splitlines() if ln.strip()]
        if not lines:
            continue
        m = None
        time_line_idx = -1
        for i, ln in enumerate(lines):
            m = time_pat.search(ln)
            if m:
                time_line_idx = i
                break
        if m and time_line_idx != -1:
            st_raw = m.group(1).replace(",", ".")
            en_raw = m.group(2).replace(",", ".")
            st_s = parse_time_to_seconds(st_raw, 0.0)
            en_s = parse_time_to_seconds(en_raw, st_s + 2.0)
            txt_lines = lines[time_line_idx + 1:]
            clean_txt = re.sub(r'<[^>]+>', '', " ".join(txt_lines)).strip()
            if clean_txt:
                entries.append({"start": st_s, "end": en_s, "text": clean_txt})
    return entries


def get_srt_snippet_for_window(srt_entries: List[Dict[str, Any]], start_s: float, end_s: float, max_chars: int = 3500) -> str:
    """Lấy phần phụ đề gốc nằm trong khoảng [start_s, end_s] để giúp AI nắm chuẩn 100% tên nhân vật & cốt truyện."""
    if not srt_entries:
        return ""
    matched = []
    cur_len = 0
    for e in srt_entries:
        if e["end"] >= start_s and e["start"] <= end_s:
            line = f"[{format_seconds_to_mmss(e['start'])}] {e['text']}"
            if cur_len + len(line) > max_chars:
                break
            matched.append(line)
            cur_len += len(line) + 1
    return "\n".join(matched)


def format_srt_timestamp(seconds: float) -> str:
    """Định dạng số giây sang chuẩn SRT HH:MM:SS,mmm."""
    seconds = max(0.0, float(seconds))
    total_sec = int(seconds)
    millis = int(round((seconds - total_sec) * 1000))
    if millis >= 1000:
        total_sec += 1
        millis -= 1000
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    return f"{h:02d}:{m:02d}:{s:02d},{millis:03d}"


def export_synced_srt_file(segments: list, scene_durations: Dict[int, float], output_srt_path: Path) -> Optional[Path]:
    """Tạo file phụ đề .SRT khớp chính xác 100% với thời lượng thực tế của từng phân cảnh sau khi render."""
    try:
        lines = []
        cur_time = 0.0
        sub_idx = 1
        for i, seg in enumerate(segments):
            dur = scene_durations.get(i, float(seg.get("duration", 5.0)))
            script_txt = seg.get("script", "").strip()
            if script_txt:
                # Chia câu dài thành các câu nhỏ vừa mắt người đọc phụ đề YouTube
                sentences = [s.strip() for s in re.split(r'(?<=[.!?।])\s+', script_txt) if s.strip()]
                if not sentences:
                    sentences = [script_txt]
                total_words = sum(max(1, len(s.split())) for s in sentences)
                seg_cur = cur_time
                for s_i, sent in enumerate(sentences):
                    w_cnt = max(1, len(sent.split()))
                    part_dur = dur * (w_cnt / total_words) if s_i < len(sentences) - 1 else (cur_time + dur - seg_cur)
                    part_dur = max(0.8, part_dur)
                    st_str = format_srt_timestamp(seg_cur)
                    en_str = format_srt_timestamp(min(cur_time + dur, seg_cur + part_dur))
                    lines.append(f"{sub_idx}\n{st_str} --> {en_str}\n{sent}\n")
                    sub_idx += 1
                    seg_cur += part_dur
            cur_time += dur
        output_srt_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return output_srt_path
    except Exception:
        return None


def analyze_and_generate_recap(
    video_path: Path,
    target_duration_sec: Optional[float] = None,
    target_ratio: float = 0.30,
    target_lang_name: str = "Tiếng Việt",
    style: str = "🔥 Review Phim Chuyên Sâu (Chuẩn Kênh Não Động Review)",
    movie_title: str = "",
    character_hints: str = "",
    model_name: str = "models/gemini-flash-latest",
    api_key: Optional[str] = None,
    custom_num_segments: Optional[int] = None,
    recap_mode: str = "movie_recap",
    votri_style: str = "max_absurd",
    custom_catchphrases: str = "",
    srt_text: str = "",
    include_cold_open_hook: bool = True,
    include_deep_moral_outro: bool = True,
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> Dict[str, Any]:
    """
    Sử dụng Gemini Model phân tích video với thuật toán Neo Hình Ảnh Thực Tế (Visual Grounding),
    tự động bóc tách các đoạn highlight và viết kịch bản thuyết minh khớp 100% với từng khung hình.
    Hỗ trợ chuyên sâu:
    - Phong cách 'Não Động Review': Kể chuyện liền mạch đa hồi (15-25 phút), phân tích tâm lý/cơ chế ngầm,
      mở đầu Cold Open giật gân và kết thúc bằng Thông điệp Nhân sinh / Cảnh giác sâu sắc.
    - movie_recap: Review phim / Tóm tắt cốt truyện điện ảnh kịch tính theo Hồi (Acts).
    - votritv_comedy: Tuyển tập Clip Hài Hước / Vô Tri TV theo chuẩn phong cách kênh @78votritv.
    """
    active_key = pick_active_api_key(api_key or "")
    if not active_key:
        return {"success": False, "error": "Vui lòng cung cấp Gemini API Key."}

    total_dur = get_video_duration(video_path)
    if total_dur <= 0:
        return {"success": False, "error": "Không thể đọc thời lượng của video gốc."}

    if recap_mode == "votritv_comedy":
        target_duration_sec = total_dur
        target_ratio = 1.0
    elif target_duration_sec is None or target_duration_sec <= 0:
        target_duration_sec = total_dur * target_ratio
    else:
        target_ratio = min(1.0, target_duration_sec / total_dur)

    total_dur_str = format_seconds_to_mmss(total_dur)
    target_dur_str = format_seconds_to_mmss(target_duration_sec)
    srt_entries = parse_srt_entries(srt_text) if srt_text else []

    proxy_temp_dir = Path(tempfile.mkdtemp())
    try:
        genai.configure(api_key=active_key)

        if progress_callback:
            progress_callback(5, "⚡ Đang nén Proxy siêu nhẹ giữ nguyên mốc thời gian...")

        proxy_video_path = proxy_temp_dir / f"proxy_{video_path.name}"
        upload_target = create_lightweight_ai_proxy(video_path, proxy_video_path)

        file_sz_mb = upload_target.stat().st_size / (1024 * 1024) if upload_target.exists() else 0
        if progress_callback:
            progress_callback(12, f"📤 Đang gửi video tới Gemini AI ({file_sz_mb:.1f}MB)...")

        # Upload video proxy lên Gemini File API với cơ chế tự động thử lại chống đứt kết nối mạng
        video_file = None
        last_upload_err = None
        for up_attempt in range(3):
            try:
                if progress_callback and up_attempt > 0:
                    progress_callback(12, f"🔄 Đang kết nối lại và gửi video tới Gemini AI (lần {up_attempt+1})...")
                video_file = genai.upload_file(path=str(upload_target))
                if video_file:
                    break
            except Exception as up_e:
                last_upload_err = up_e
                time.sleep(2)

        if not video_file:
            try:
                video_file = genai.upload_file(path=str(video_path))
            except Exception as final_e:
                return {"success": False, "error": f"Lỗi kết nối gửi video lên AI: {str(final_e or last_upload_err)}"}

        max_wait = 360
        waited = 0
        while video_file.state.name == "PROCESSING" and waited < max_wait:
            time.sleep(2)
            waited += 2
            video_file = genai.get_file(video_file.name)
            if progress_callback:
                progress_callback(15 + int((waited / max_wait) * 20), f"🤖 AI đang giải mã bối cảnh và diễn biến bộ phim ({waited}s)...")

        # Tính số lượng phân cảnh và độ dài từng cảnh theo đúng mục tiêu thời lượng
        if recap_mode == "votritv_comedy":
            # Chế độ Tuyển tập Clip Hài Vô Tri TV: Giữ trọn vẹn 100% video gốc không cắt bỏ
            if custom_num_segments and int(custom_num_segments) > 0:
                num_segments = max(2, min(150, int(custom_num_segments)))
            else:
                num_segments = max(3, min(80, int(total_dur / 5.0)))

            avg_seg_dur = max(2.5, round(total_dur / num_segments, 1))
            min_seg_dur = 2.0
            max_seg_dur = max(4.0, round(avg_seg_dur * 1.5, 1))
            target_words = max(8, min(24, int(avg_seg_dur * 3.1)))
            min_words = max(6, int(target_words * 0.7))
            max_words = int(target_words * 1.35)
        else:
            # Chế độ Review Phim / Chuẩn Kênh Não Động Review
            if custom_num_segments and int(custom_num_segments) > 0:
                num_segments = max(4, min(180, int(custom_num_segments)))
            else:
                if target_duration_sec <= 180:
                    num_segments = max(8, min(22, int(target_duration_sec / 8.0)))
                elif target_duration_sec <= 480:
                    num_segments = max(20, min(42, int(target_duration_sec / 10.5)))
                elif target_duration_sec <= 900:
                    num_segments = max(40, min(75, int(target_duration_sec / 12.0)))
                else:
                    # Phim dài Review Chuyên Sâu 15 - 25 phút chuẩn Não Động Review (80 - 150 phân cảnh)
                    num_segments = max(65, min(150, int(target_duration_sec / 12.5)))

            avg_seg_dur = max(5.0, min(22.0, round(target_duration_sec / num_segments, 1)))
            min_seg_dur = max(4.0, round(avg_seg_dur * 0.75, 1))
            max_seg_dur = round(avg_seg_dur * 1.35, 1)
            # Tốc độ nói chuẩn của giọng Review Phim (Não Động Review): ~3.15 từ / giây
            target_words = max(18, min(75, int(avg_seg_dur * 3.15)))
            min_words = max(14, int(target_words * 0.82))
            max_words = int(target_words * 1.22)

        movie_context_prompt = ""
        if movie_title.strip() or character_hints.strip():
            movie_context_prompt = f"""
THÔNG TIN TÁC PHẨM & NHÂN VẬT:
- Tên Phim / Video: {movie_title.strip() if movie_title.strip() else 'Theo cốt truyện video'}
- Danh Sách Nhân Vật & Tên Gọi: {character_hints.strip() if character_hints.strip() else 'Tự động tra cứu theo phim'}
- QUY TẮC BẮT BUỘC: Bạn PHẢI nhận diện chính xác từng nhân vật xuất hiện trên màn hình và GỌI ĐÚNG TÊN NHÂN VẬT trong toàn bộ kịch bản thuyết minh. Tuyệt đối KHÔNG gọi chung chung là 'chàng trai', 'cô gái', 'người đàn ông' khi đã biết tên nhân vật!
"""

        # Phân chia theo Hồi (Timeline Acts) hỗ trợ tới 8 Hồi cho Review Phim Chuyên Sâu 15-25 phút
        acts_plan = []
        if num_segments <= 24:
            acts_plan = [(0.0, total_dur, num_segments, 1, 1)]
        else:
            num_acts = min(8, max(2, math.ceil(num_segments / 22.0)))
            act_dur = total_dur / num_acts
            base_segs = num_segments // num_acts
            rem_segs = num_segments % num_acts
            cur_st = 0.0
            for a_i in range(num_acts):
                cur_et = total_dur if a_i == num_acts - 1 else cur_st + act_dur
                segs_in_act = base_segs + (1 if a_i < rem_segs else 0)
                acts_plan.append((round(cur_st, 1), round(cur_et, 1), segs_in_act, a_i + 1, num_acts))
                cur_st = cur_et

        deprecated_models = {"models/gemini-2.5-flash", "models/gemini-2.5-pro", "models/gemini-2.5-flash-lite"}
        candidate_models = []
        if model_name and model_name not in deprecated_models:
            candidate_models.append(model_name)
        for m in [
            "models/gemini-flash-latest",
            "models/gemini-flash-lite-latest",
            "models/gemini-3.5-flash-lite",
            "models/gemini-3.6-flash",
            "models/gemini-3.7-flash",
        ]:
            if m not in candidate_models and m not in deprecated_models:
                candidate_models.append(m)

        raw_all_segments = []
        total_acts_count = len(acts_plan)
        is_naodong_style = ("não động" in style.lower()) or ("chuyên sâu" in style.lower()) or (recap_mode == "naodong_review")

        for act_st, act_et, act_segs, act_num, total_acts in acts_plan:
            act_st_str = format_seconds_to_mmss(act_st)
            act_et_str = format_seconds_to_mmss(act_et)

            active_disp_model = (candidate_models[0] if candidate_models else "AI").replace("models/", "")
            if progress_callback:
                if total_acts > 1:
                    pct_val = 35 + int((act_num - 1) / total_acts * 45)
                    progress_callback(pct_val, f"✍️ AI ({active_disp_model}) đang biên kịch Hồi {act_num}/{total_acts} ({act_st_str} ➔ {act_et_str}) gồm {act_segs} phân cảnh...")
                else:
                    progress_callback(40, f"✍️ AI ({active_disp_model}) đang lên kịch bản thuyết minh và chọn lọc {act_segs} phân cảnh Highlight...")

            # Ngữ cảnh nối tiếp từ Hồi trước để câu chuyện liền mạch 100% không đứt quãng
            prev_continuity_note = ""
            if raw_all_segments:
                last_two = raw_all_segments[-2:]
                prev_scripts = " | ".join([s.get("script", "") for s in last_two if s.get("script")])
                if prev_scripts:
                    prev_continuity_note = f"""
MẠCH TRUYỆN LIỀN TRƯỚC (HỒI {act_num - 1}):
"{prev_scripts}"
➔ YÊU CẦU LIỀN MẠCH TUYỆT ĐỐI: Phân cảnh đầu tiên của Hồi {act_num} PHẢI nối tiếp tự nhiên mạch chuyện trên (dùng các từ chuyển đoạn như 'Lúc này...', 'Thế nhưng...', 'Ngay sau đó...', 'Trong khi đó...', 'Hóa ra...'). TUYỆT ĐỐI KHÔNG mở bài lại từ đầu!
"""

            # Trích xuất phụ đề gốc (nếu có) trong khung giờ của Hồi hiện tại
            srt_window_context = ""
            if srt_entries:
                sub_snippet = get_srt_snippet_for_window(srt_entries, act_st, act_et, max_chars=3500)
                if sub_snippet:
                    srt_window_context = f"""
PHỤ ĐỀ / LỜI THOẠI GỐC TRONG ĐOẠN [{act_st_str} - {act_et_str}] (Dùng để lấy chính xác tên nhân vật, địa danh, tình tiết):
{sub_snippet}
"""

            if recap_mode == "votritv_comedy":
                # Tùy biến phân cấp phong cách Vô Tri theo chuẩn kênh @78votritv
                if votri_style == "fake_serious":
                    substyle_guide = """
- TRỌNG TÂM: NÓI LÁI ĐI QUA LĂNG KÍNH KHOA HỌC & ĐỊNH LUẬT VẬT LÝ DỞ HƠI.
- Tuyệt đối né tránh việc miêu tả cú ngã hay tai nạn. Hãy giải thích tình huống dưới góc nhìn định luật vạn vật hấp dẫn Newton, quán tính, gia tốc rơi tự do, ma sát học, sinh học tế bào hoặc phong thủy nhưng với kết luận hoàn toàn nhảm nhí, cùn và tỉnh bơ.
- Giọng văn trang nghiêm, trịnh trọng như một giáo sư hay bản tin khoa học đời sống.
"""
                elif votri_style == "brotherhood":
                    substyle_guide = """
- TRỌNG TÂM: NÓI LÁI ĐI QUA TÌNH ANH EM CẢM LẠNH & NGHĨA KHÍ VÔ TRI.
- Dù trên hình là cảnh bạn bè chơi khăm, rút ghế, xô ngã, hãm hại, gài bẫy đau đớn đến mấy ➔ BẮT BUỘC PHẢI NÓI LÁI THÀNH: sự giúp đỡ hết mình, nghĩa cử cao đẹp, tình anh em chí cốt, sự trợ giúp kịp thời để bạn rèn luyện xương khớp hoặc hoàn thành sớm công việc.
"""
                elif votri_style == "genz_bua":
                    substyle_guide = """
- TRỌNG TÂM: NÓI LÁI ĐI KẾT HỢP HÀI BỰA GEN Z & CÀ KHỊA TIKTOK.
- Nói lái sang hướng châm biếm, sử dụng linh hoạt các thuật ngữ thịnh hành: 'kiếp nạn thứ 82', 'pha xử lý đi thẳng vào lòng đất', '10 điểm tự tin nhưng âm vô cùng điểm thực tế', 'quay xe khét lẹt', 'hết cứu', 'tình anh em cảm lạnh', 'hảo hán', 'đúng là không còn gì để nói'...
"""
                else: # max_absurd (Mặc định - Chuẩn 100% Kênh @78votritv Triệu View)
                    substyle_guide = """
- TRỌNG TÂM: SIÊU CẤP VÔ TRI - NÓI LÁI ĐI & BẺ LÁI LOGIC 180 ĐỘ (CHUẨN 100% KÊNH @78votritv).
- CÔNG THỨC VÀNG TỐI THƯỢNG: TUYỆT ĐỐI KHÔNG NÓI VÀO TRỌNG TÂM CÂU CHUYỆN!
  * Khán giả có mắt và họ đang nhìn thấy rõ hành động chính (ngã sấp mặt, lật xe, đập đầu, rơi vỡ). Nếu bạn tả lại điều đó, bạn là một người kể chuyện tồi tệ và nhạt nhẽo!
  * BẮT BUỘC PHẢI LỜ ĐI TAI NẠN CHÍNH, NÓI LÁI SANG MỘT CHI TIẾT HOÀN TOÀN PHỤ, LẠC QUẺ VÀ BỊA RA ĐỘNG CƠ CAO ĐẸP HOẶC QUY TRÌNH THỬ NGHIỆM TỈNH BƠ.
"""

                catchphrase_guide = ""
                if custom_catchphrases.strip():
                    catchphrase_guide = f"""
══════════════════════════════════════════════════════════════════════
GỢI Ý TỪ KHÓA & PHONG CÁCH PUNCHLINE THAM KHẢO TỪ KÊNH @78votritv:
{custom_catchphrases.strip()}
⚠️ NGUYÊN TẮC BẮT BUỘC:
- Danh sách trên là GỢI Ý PHONG CÁCH. Bạn CHỈ ĐƯỢC PHÉP CHỌN CÂU NÀO THỰC SỰ KHỚP VỚI HÌNH ẢNH CLIP.
- TUYỆT ĐỐI CẤM dùng bừa bãi những từ/vật thể không xuất hiện trong clip!
- Nếu không có cảnh tương ứng, bạn BẮT BUỘC PHẢI TỰ NGHĨ RA PUNCHLINE NÓI LÁI MỚI phù hợp với hình ảnh clip.
══════════════════════════════════════════════════════════════════════
"""

                act_prompt = f"""
Bạn là Bậc Thầy Biên Kịch & "Thánh Bịa Chuyện Vô Tri" số 1 TikTok (kênh @78votritv triệu view).
Video đầu vào là một video tổng hợp gồm RẤT NHIỀU CLIP NGẮN HÀI HƯỚC, TÌNH HUỐNG BẤT NGỜ, CÁC PHA XỬ LÝ CỒNG KỀNH NỐI TIẾP NHAU LIÊN TỤC TRONG KHOẢNG [{act_st_str} - {act_et_str}].

══════════════════════════════════════════════════════════════════════
YÊU CẦU 1: BẢO TOÀN 100% VIDEO GỐC - KHÔNG BỎ BẤT KỲ GIÂY NÀO (ZERO CUTS)
══════════════════════════════════════════════════════════════════════
- Nhiệm vụ tối thượng: Phân chia toàn bộ dòng thời gian từ {act_st_str} đến {act_et_str} thành các clip tình huống nối tiếp nhau liên tục:
  * Cảnh 1: start_time = "{act_st_str}", end_time = t1
  * Cảnh 2: start_time = t1, end_time = t2
  * ...
  * Cảnh cuối: start_time = t_{{n-1}}, end_time = "{act_et_str}"
- QUY TẮC BẮT BUỘC: end_time của cảnh trước PHẢI LÀ start_time của cảnh sau. KHÔNG ĐƯỢC CÓ KHOẢNG TRỐNG (GAP), KHÔNG ĐƯỢC BỎ SÓT BẤT CỨ ĐOẠN NÀO!
- Mỗi tình huống ngắn từ {min_seg_dur:.1f}s đến {max_seg_dur:.1f}s (tối đa 30s). Bắt trọn khoảnh khắc diễn biến của từng clip ngắn.

══════════════════════════════════════════════════════════════════════
YÊU CẦU 2: TUYỆT KỸ "NÓI LÁI ĐI - CẤM TUYỆT ĐỐI NÓI VÀO TRỌNG TÂM" CHUẨN @78votritv
══════════════════════════════════════════════════════════════════════
- ❌ CẤM NÓI THẲNG VÀO TRỌNG TÂM SỰ THẬT: Khán giả có mắt và họ đang nhìn thấy màn hình! Tuyệt đối không mô tả sự thật hiển nhiên như:
  * ❌ "Một người đàn ông đang lái xe rồi bị ngã sấp mặt." (Cực kỳ nhạt nhẽo!)
  * ❌ "Chàng trai nhảy xuống nước nhưng va đập vào bờ."
  * ❌ "Cô gái nấu ăn bất cẩn làm đổ tung tóe đồ đạc."
  * ❌ "Hai người bạn đang đùa thì một người bị đẩy ngã."

- ✅ BẮT BUỘC PHẢI "NÓI LÁI ĐI" SANG CHI TIẾT PHỤ HOẶC BỊA RA ĐỘNG CƠ CAO CẢ / THỬ NGHIỆM KHOA HỌC TỈNH BƠ:
  Xem kỹ 8 bộ ví dụ đối chiếu kinh điển của kênh @78votritv dưới đây:

  1. 🏃 Khi thấy ai ngã sấp mặt / trượt té / tiếp đất đau đớn:
     - ❌ Đừng nói: Ngã đau, trượt chân.
     - ✅ Nói lái đi: "Nhận thấy mặt đường lâu ngày chưa ai đo đạc lại kích thước, người đàn ông lập tức dùng gò má để kiểm tra độ phẳng của bê tông, kết quả cho thấy mặt đường rất chuẩn, chỉ có chiếc răng cửa là lung lay." hoặc "Để chứng minh định luật vạn vật hấp dẫn của Newton vẫn hoạt động bình thường, chàng trai quyết định dùng phần thịt mềm nhất trên cơ thể để tiếp đất, một màn hạ cánh không thể nào êm ái hơn."

  2. 💦 Khi thấy ai rơi xuống ao hồ, lao xe xuống mương, nhảy vũng bùn:
     - ❌ Đừng nói: Lao xe xuống mương, rơi xuống ao bèo.
     - ✅ Nói lái đi: "Nhận thấy làn da sau một ngày làm việc cần được cấp ẩm chuyên sâu, anh ấy quyết định hòa mình vào lớp bùn khoáng hữu cơ, phương pháp làm đẹp từ thiên nhiên này quả nhiên vô cùng tốn xà phòng." hoặc "Với mong muốn giảm tải áp lực cho giao thông đường bộ, vị tài xế đã chủ động chuyển hướng sang đường thủy kết hợp bơi lội, đúng là một con người luôn có lối đi riêng."

  3. 🤝 Khi thấy bạn bè chơi khăm, rút ghế, xô ngã, đẩy bạn:
     - ❌ Đừng nói: Bạn bè chơi đểu đẩy ngã.
     - ✅ Nói lái đi: "Nhận thấy người bạn ngồi nghỉ quá lâu có thể làm chậm tiến độ làm việc, người anh em chí cốt liền nhiệt tình hỗ trợ một cú hích dứt khoát, nhờ sự giúp đỡ hết mình của người anh em tốt, chàng trai nhanh chóng hoàn thành toàn bộ quy trình, tình bạn thời nay quả nhiên cảm động đến rơi nước mắt."

  4. 💥 Khi thấy làm vỡ bát đĩa, đổ nồi niêu, hỏng đồ đạc:
     - ❌ Đừng nói: Bê đồ trượt tay làm đổ vỡ.
     - ✅ Nói lái đi: "Nhận thấy việc rửa bát sau khi ăn quá mất thời gian, cô gái đã chủ động giải phóng sức lao động bằng cách đập vỡ toàn bộ, nếu đang nấu canh mà làm đổ muối xuống đất, thì không còn nghi ngờ gì nữa, nồi canh này chắc chắn phải nấu lại."

  5. 🏋️ Khi thấy khoe mẽ, bốc đầu xe, làm xiếc thất bại:
     - ❌ Đừng nói: Bốc đầu xe thể hiện rồi bị ngã.
     - ✅ Nói lái đi: "Nhận thấy bánh trước hoạt động quá nhiều dễ bị mòn lốp, chàng trai tốt bụng đã nâng bổng bánh xe lên để nó được nghỉ ngơi, 10 điểm ý thức nhưng âm vô cùng điểm thực tế, đúng là đàn ông đích thực chưa bao giờ chừa cho mình đường lui."

  6. 🚪 Khi thấy va đập vào cửa kính, đâm vào cột điện, vật cản:
     - ❌ Đừng nói: Đi không chú ý đâm vào cửa kính.
     - ✅ Nói lái đi: "Để kiểm tra độ trong suốt của cửa kính sau khi nhân viên vệ sinh lau dọn, vị khách đã dùng trán để nghiệm thu chất lượng, kết quả cho thấy cửa kính quá sạch, sạch đến mức không còn nhận ra nó đang đóng."

  7. 🐶 Khi thấy thú cưng phản chủ, quậy phá, động vật vô tri:
     - ❌ Đừng nói: Con chó kéo ngã chủ, con mèo cào đồ.
     - ✅ Nói lái đi: "Nhận thấy chủ nhân ngồi văn phòng quá nhiều thiếu vận động, chú cún đã tạo điều kiện cho anh một pha tiếp đất rèn luyện phản xạ, con sen hết lòng phục vụ nhưng hoàng thượng thì chỉ muốn tiễn bạn lên đường."

  8. 🥊 Khi thấy nghịch dại trêu người lạ bị ăn đòn / phản đòn:
     - ❌ Đừng nói: Nghịch dại trêu người bị đánh.
     - ✅ Nói lái đi: "Nhằm mục đích kiểm tra phản xạ tự vệ và mức độ kiên nhẫn của người qua đường, chàng trai đã dũng cảm làm đối tượng thử nghiệm, quả nhiên không phải ai cũng thích đùa."

{substyle_guide}
{catchphrase_guide}

══════════════════════════════════════════════════════════════════════
YÊU CẦU 3: KHO PUNCHLINE & NGHỆ THUẬT CHỐT HẠ BẺ LÁI ĐỈNH CAO @78votritv
══════════════════════════════════════════════════════════════════════
Mỗi câu thoại PHẢI kết thúc bằng một punchline đúc kết tỉnh bơ, lạnh lùng, hài hước:
- '...tội nghiệp quá, chiếc xe chắc chắn phải đem đi bảo dưỡng lại lòng tin.'
- '...đúng là một phương pháp làm đẹp từ thiên nhiên vô cùng tốn xà phòng.'
- '...kỹ năng thì có hạn nhưng độ tự tin thì có thừa.'
- '...10 điểm tự tin nhưng âm vô cùng điểm thực tế.'
- '...đúng là đàn ông đích thực chưa bao giờ chừa cho mình đường lui.'
- '...nhanh đến mức mặt đất còn chưa kịp chuẩn bị tâm lý đón nhận.'
- '...hóa ra đây là cách người tích cực nhìn thế giới.'
- '...tình bạn thời nay quả nhiên cảm động đến rơi nước mắt.'
- '...đúng lúc đó một người hùng xuất hiện nhưng hóa ra là người hùng thầm lặng đi ngang qua.'
- '...đúng là quá nghĩa khí.'
- '...nếu đang nấu canh mà làm đổ muối xuống đất, thì không còn nghi ngờ gì nữa, nồi canh này chắc chắn phải nấu lại.'
- '...quả nhiên không phải ai cũng thích đùa.'
- '...đi được nửa đường mới phát hiện hóa ra đây đúng là xe đạp địa hình.'
- '...sống đủ lâu mới thấy trên đời này chuyện quái gì cũng có thể xảy ra.'
- '...hóa ra người làm bạn tổn thương nhất chưa bao giờ là đối thủ ngoài xã hội.'
- '...đúng là một pha xử lý đi thẳng vào lòng đất theo cả nghĩa đen lẫn nghĩa bóng.'

⚠️ QUY TẮC CỐT LÕI:
- TONE GIỌNG: Lạnh lùng, điềm đạm, nghiêm túc giả tạo (Deadpan Humor). TUYỆT ĐỐI KHÔNG dùng từ cảm thán như 'haha', 'hihi', 'trời ơi', 'buồn cười quá'.
- TUYỆT ĐỐI CẤM nhắc đến đồ vật/con vật/hành động KHÔNG HỀ XUẤT HIỆN trong clip!
- Không dùng dấu ngoặc kép " bên trong script (dùng dấu nháy đơn ' hoặc không dùng) để đảm bảo JSON hợp lệ 100%.

══════════════════════════════════════════════════════════════════════
CẤU TRÚC MỖI CÂU SCRIPT (TỪ {min_words} ĐẾN {max_words} TỪ):
══════════════════════════════════════════════════════════════════════
- Mở đầu nghiêm trang: 'Nhận thấy...' / 'Để chứng minh...' / 'Với tinh thần...' / 'Một người đàn ông sau khi...' / 'Nhờ sự giúp đỡ hết mình của người anh em...' / 'Nếu đang...'
- Thân câu: Nói lái đi hoàn toàn sang chi tiết phụ (độ cứng mặt đường, cấp ẩm bùn khoáng, rèn luyện xương khớp, bảo vệ môi trường...).
- Câu chốt hạ: Punchline chuẩn kênh @78votritv tỉnh bơ, lạnh lùng khớp hoàn toàn với bối cảnh clip.

Ngôn ngữ kịch bản bắt buộc: {target_lang_name}.
OUTPUT FORMAT:
Bạn PHẢI trả về duy nhất một JSON Array hợp lệ gồm các phân cảnh bao phủ trọn vẹn từ "{act_st_str}" đến "{act_et_str}":
[
  {{
    "index": 1,
    "start_time": "{act_st_str}",
    "end_time": "...",
    "visual_action": "Bối cảnh clip ngắn",
    "title": "Tên tình huống nói lái",
    "script": "Lời bình bịa đặt vô tri nói lái đi chuẩn phong cách @78votritv..."
  }}
]
"""
            else:
                act_role_instruction = ""
                if act_num == 1 and include_cold_open_hook:
                    act_role_instruction = """
🔥 YÊU CẦU ĐẶC BIỆT CHO HỒI MỞ ĐẦU (COLD OPEN HOOK CHUẨN KÊNH 'NÃO ĐỘNG REVIEW'):
- Phân cảnh #1 và #2 PHẢI mở màn trực diện vào bầu không khí căng thẳng, bí ẩn hoặc xung đột đắt giá nhất (Ví dụ mẫu chuẩn Não Động Review: 'Nơi này nằm ở một khu vực vô cùng hoang vắng, gần như tách biệt hoàn toàn với thế giới bên ngoài, nhưng lại được quản lý và canh gác cực kỳ nghiêm ngặt... Tuy nhiên, ngay sau đó, một tiếng súng vang lên khiến tất cả mọi người có mặt lập tức im bặt...').
- Tuyệt đối KHÔNG mở đầu nhạt nhẽo kiểu 'Xin chào các bạn, hôm nay chúng ta cùng xem phim...'. Hãy cuốn người xem vào thẳng thế giới của bộ phim ngay từ giây đầu tiên, sau đó dẫn dắt mượt mà vào nhân vật chính và nguyên nhân khởi nguồn câu chuyện!
"""
                elif act_num == total_acts and include_deep_moral_outro:
                    act_role_instruction = """
🌟 YÊU CẦU ĐẶC BIỆT CHO HỒI KẾT (CAO TRÀO & THÔNG ĐIỆP CHIỀU SÂU CHUẨN 'NÃO ĐỘNG REVIEW'):
- Các phân cảnh đầu và giữa Hồi này: Đẩy kịch tính lên đỉnh điểm để giải quyết nút thắt cuối cùng của bộ phim.
- RIÊNG 1-2 PHÂN CẢNH CUỐI CÙNG CỦA HỒI NÀY: Sau khi khép lại số phận các nhân vật, BẮT BUỘC phải lồng ghép phần đúc kết THÔNG ĐIỆP NHÂN SINH / BÀI HỌC CẢNH GIÁC SÂU SẮC chuẩn phong cách kênh 'Não Động Review' (Ví dụ mẫu chuẩn: 'Thông điệp cuối cùng mà nội dung muốn nhấn mạnh là thay vì chỉ trông chờ vào may mắn sau khi hậu quả đã xảy ra, mỗi người trước hết cần tự nâng cao cảnh giác... Nhiều chiếc bẫy không khiến nạn nhân mất tất cả ngay từ bước đầu, chúng thường cố tình cho người ta một chút lợi ích, một chút hy vọng để khiến người đó tin rằng mình đang kiểm soát tình hình...').
"""
                else:
                    act_role_instruction = f"""
🎬 YÊU CẦU ĐẶC BIỆT CHO HỒI {act_num}/{total_acts} (PHÁT TRIỂN XUNG ĐỘT & BÓC TÁCH CHIỀU SÂU):
- Tiếp nối liền mạch 100% từ Hồi trước, đẩy cao mâu thuẫn, bóc tách rõ tâm lý nhân vật, các bước ngoặt (plot twists) và cơ chế hoạt động ngầm đằng sau các sự kiện trong phim.
"""

                naodong_master_guide = ""
                if is_naodong_style:
                    naodong_master_guide = """
══════════════════════════════════════════════════════════════════════
BÍ QUYẾT BIÊN KỊCH TRIỆU VIEW CHUẨN KÊNH "NÃO ĐỘNG REVIEW" (BẮT BUỘC TUÂN THỦ):
══════════════════════════════════════════════════════════════════════
1. **GIỌNG VĂN KỂ CHUYỆN TOÀN TRI, SẮC SẢO & LIỀN MẠCH NHƯ TIỂU THUYẾT**:
   - Sử dụng ngôi thứ ba toàn tri điềm đạm, khách quan, giàu tính phân tích tâm lý và xã hội.
   - TUYỆT ĐỐI KHÔNG viết rời rạc từng câu cụt ngủn. Toàn bộ các phân cảnh phải nối kết với nhau thành MỘT DÒNG CHẢY KỂ CHUYỆN LIÊN TỤC bằng các từ nối tự nhiên ('Tuy nhiên, ngay sau đó...', 'Sau khi...', 'Ở cấp độ cao hơn...', 'Lúc này...', 'Dĩ nhiên...', 'Không ai ngờ rằng...', 'Thế nhưng...').
2. **VỪA KHỚP HÌNH ẢNH 100%, VỪA GIẢI THÍCH BẢN CHẤT & ĐỘNG CƠ NGẦM**:
   - Không chỉ tả bề mặt ('anh ta ngồi trước máy tính'), mà phải giải thích Ý NGHĨA CỦA HÀNH ĐỘNG ĐÓ TRONG CỐT TRUYỆN ('Trong căn phòng tối tăm và ngột ngạt, hàng loạt người đàn ông chen chúc trước máy tính. Công việc của họ là sử dụng hàng chục tài khoản ảo để tiếp cận con mồi và phát tán đường link lừa đảo...').
"""

                act_prompt = f"""
Bạn là Tổng Biên Tập & Biên Kịch Trưởng của kênh YouTube Review Phim triệu view "Não Động Review".
Nhiệm vụ: Trích xuất các phân cảnh đắt giá nhất và viết kịch bản thuyết minh Review Phim chuyên sâu, cuốn hút, ĐỒNG BỘ CHUẨN XÁC 100% VỚI HÌNH ẢNH VIDEO.
Phong cách biên kịch: {style}.
Ngôn ngữ kịch bản bắt buộc: {target_lang_name}.
Thời lượng video gốc: {total_dur_str} ({total_dur:.1f} giây).
HỒI HIỆN TẠI (PHÂN ĐOẠN {act_num}/{total_acts}): Khung thời gian từ {act_st_str} ({act_st:.1f}s) đến {act_et_str} ({act_et:.1f}s).
YÊU CẦU: CHỌN LỌC VÀ VIẾT ĐÚNG {act_segs} PHÂN CẢNH NẰM TRONG KHOẢNG [{act_st_str} - {act_et_str}].
{movie_context_prompt}
{prev_continuity_note}
{srt_window_context}
{act_role_instruction}
{naodong_master_guide}

══════════════════════════════════════════════════════════════════════
QUY TẮC BẮT BUỘC VỀ ĐỒNG BỘ HÌNH ẢNH & LỜI THOẠI (VISUAL-TO-SCRIPT GROUNDING):
══════════════════════════════════════════════════════════════════════
1. **NEO HÌNH ẢNH THỰC TẾ TRỰC QUAN (`visual_action`)**:
   - Bạn PHẢI quan sát trực tiếp khung hình video tại `start_time` và ghi rõ hành động, bối cảnh, nhân vật đang xuất hiện.

2. **LỜI THUYẾT MINH PHẢI NÓI TRỰC TIẾP VỀ HÌNH ẢNH ĐANG CHIẾU (`script`)**:
   - Lời thoại BẮT BUỘC PHẢI THUYẾT MINH CHÍNH XÁC VỀ HÀNH ĐỘNG/SỰ KIỆN đang diễn ra trên màn hình tại mốc thời gian đó kết hợp dẫn dắt cốt truyện sâu sắc.
   - Khi video chiếu cảnh nhân vật cầm tờ tiền viết số điện thoại cầu cứu, lời thoại phải nói đúng về hành động viết số điện thoại lên tờ tiền đó.

3. **CÂN CHỈNH ĐỘ DÀI LỜI THOẠI KHỚP THỜI LƯỢNG (WORD COUNT CALIBRATION)**:
   - Tốc độ đọc chuẩn Review Phim là khoảng 3.15 từ/giây.
   - Vì mỗi phân cảnh dài khoảng {avg_seg_dur:.1f} giây, mỗi đoạn `script` BẮT BUỘC PHẢI DÀI TỪ {min_words} ĐẾN {max_words} TỪ.
   - Không được viết quá ngắn (dưới {min_words} từ) gây trống vắng, cũng không viết quá dài (trên {max_words} từ) làm giọng đọc bị trôi cảnh!
   - Không dùng dấu ngoặc kép " bên trong script (dùng dấu nháy đơn ' hoặc không dùng) để đảm bảo JSON hợp lệ 100%.

4. **MỐC THỜI GIAN TUẦN TỰ (CHRONOLOGICAL TIMESTAMPS)**:
   - Mốc thời gian `start_time` và `end_time` BẮT BUỘC nằm trong khoảng [{act_st_str} - {act_et_str}].
   - Các phân cảnh sắp xếp theo thứ tự tăng dần.
   - Thời lượng mỗi cảnh (`end_time` - `start_time`) từ {min_seg_dur:.0f}s đến {max_seg_dur:.0f}s.

OUTPUT FORMAT:
Bạn PHẢI trả về duy nhất một JSON Array hợp lệ gồm đúng {act_segs} phân cảnh:
[
  {{
    "index": 1,
    "start_time": "{act_st_str}",
    "end_time": "{format_seconds_to_mmss(act_st + avg_seg_dur)}",
    "visual_action": "Mô tả hình ảnh cụ thể đang chiếu trên màn hình tại mốc thời gian này",
    "title": "Tiêu đề phân cảnh",
    "script": "Lời thuyết minh chuẩn phong cách Não Động Review, liền mạch, sâu sắc và khớp 100% khung hình..."
  }}
]
"""

            act_resp_txt = ""
            for model_idx, cur_model in enumerate(candidate_models):
                cur_model_clean = cur_model.replace("models/", "")
                if progress_callback:
                    if total_acts > 1:
                        pct_val = 35 + int((act_num - 1) / total_acts * 45)
                        progress_callback(pct_val, f"✍️ AI ({cur_model_clean}) đang phân tích kịch bản Hồi {act_num}/{total_acts} ({act_st_str} ➔ {act_et_str}) gồm {act_segs} phân cảnh...")
                    else:
                        progress_callback(40, f"✍️ AI ({cur_model_clean}) đang lên kịch bản thuyết minh và chọn lọc {act_segs} phân cảnh Highlight...")

                try:
                    model_inst = genai.GenerativeModel(
                        model_name=cur_model,
                        generation_config={
                            "response_mime_type": "application/json",
                            "temperature": 0.30,
                        }
                    )
                    # Giới hạn timeout 150s hỗ trợ phân tích phim dài 2-3 tiếng
                    resp = model_inst.generate_content([video_file, act_prompt], request_options={"timeout": 150})
                    if resp and resp.text:
                        act_resp_txt = resp.text.strip()
                        break
                except Exception as e_gen:
                    if progress_callback and model_idx + 1 < len(candidate_models):
                        next_m = candidate_models[model_idx + 1].replace("models/", "")
                        progress_callback(pct_val, f"⚡ Model {cur_model_clean} bận, tự động chuyển sang ({next_m}) để tiếp tục...")
                    time.sleep(1)
                    continue

            if act_resp_txt:
                act_segs_parsed = extract_recap_segments_robustly(act_resp_txt)
                if act_segs_parsed:
                    raw_all_segments.extend(act_segs_parsed)

        if not raw_all_segments:
            return {"success": False, "error": "AI không thể trích xuất phân cảnh nào từ video."}

        # Chuẩn hóa lại thời gian các segment theo thứ tự và giây thực tế
        validated_segments = []
        cur_default_st = 0.0
        for idx, seg in enumerate(raw_all_segments):
            raw_st = seg.get("start_time") or seg.get("start_sec") or cur_default_st
            raw_en = seg.get("end_time") or seg.get("end_sec") or None

            st_val = max(0.0, min(total_dur, parse_time_to_seconds(raw_st, default=cur_default_st)))
            if raw_en is not None:
                parsed_en = parse_time_to_seconds(raw_en, default=st_val + avg_seg_dur)
                # Giới hạn mỗi phân cảnh tối đa 35s để tránh AI trả về cả Hồi 5 phút
                max_allowed_dur = 35.0 if recap_mode == "votritv_comedy" else 45.0
                en_val = max(st_val + 2.0, min(st_val + max_allowed_dur, min(total_dur, parsed_en)))
            else:
                en_val = min(total_dur, st_val + avg_seg_dur)

            cur_default_st = en_val

            validated_segments.append({
                "index": idx + 1,
                "start_sec": round(st_val, 2),
                "end_sec": round(en_val, 2),
                "start_time": format_seconds_to_mmss(st_val),
                "end_time": format_seconds_to_mmss(en_val),
                "duration": round(en_val - st_val, 2),
                "title": seg.get("title", f"Phân cảnh {idx+1}"),
                "visual_action": seg.get("visual_action", "").strip(),
                "script": seg.get("script", "").strip()
            })

        # ĐẢM BẢO 100% TIMELINE KHÔNG ĐỨT ĐOẠN CHO VÔ TRI TV (GIỮ 100% VIDEO GỐC)
        if recap_mode == "votritv_comedy" and validated_segments:
            validated_segments[0]["start_sec"] = 0.0
            validated_segments[0]["start_time"] = "00:00"
            if validated_segments[0]["end_sec"] <= 0.0 or validated_segments[0]["end_sec"] > 35.0:
                validated_segments[0]["end_sec"] = min(total_dur, avg_seg_dur)
            validated_segments[0]["end_time"] = format_seconds_to_mmss(validated_segments[0]["end_sec"])
            validated_segments[0]["duration"] = round(validated_segments[0]["end_sec"], 2)

            for s_i in range(1, len(validated_segments)):
                prev_en = validated_segments[s_i-1]["end_sec"]
                validated_segments[s_i]["start_sec"] = prev_en
                validated_segments[s_i]["start_time"] = format_seconds_to_mmss(prev_en)

                cur_en = validated_segments[s_i]["end_sec"]
                if cur_en <= prev_en or (cur_en - prev_en) > 35.0:
                    cur_en = min(total_dur, prev_en + avg_seg_dur)
                validated_segments[s_i]["end_sec"] = round(cur_en, 2)
                validated_segments[s_i]["end_time"] = format_seconds_to_mmss(cur_en)
                validated_segments[s_i]["duration"] = round(cur_en - prev_en, 2)

            # Cảnh cuối cùng nối đến đúng cuối video gốc
            validated_segments[-1]["end_sec"] = round(total_dur, 2)
            validated_segments[-1]["end_time"] = format_seconds_to_mmss(total_dur)
            validated_segments[-1]["duration"] = round(max(1.0, total_dur - validated_segments[-1]["start_sec"]), 2)

        # Trích xuất hình ảnh Thumbnail đại diện cho từng phân cảnh để người dùng kiểm tra trực quan
        if progress_callback:
            progress_callback(88, "📸 Đang trích xuất ảnh xem trước trực quan cho từng phân cảnh...")

        thumb_dir = Path("output_clips") / f"thumbs_{int(time.time())}"
        validated_segments = generate_segment_thumbnails(video_path, validated_segments, thumb_dir)

        return {
            "success": True,
            "total_video_dur": total_dur,
            "target_recap_dur": target_duration_sec,
            "segments": validated_segments,
            "thumb_dir": str(thumb_dir)
        }

    except Exception as e:
        return {"success": False, "error": f"Lỗi phân tích Recap: {str(e)}"}


def extract_recap_segments_robustly(resp_txt: str) -> list:
    """
    Bóc tách danh sách phân cảnh siêu bền bỉ (Infallible JSON Extractor):
    Tự động sửa lỗi thiếu dấu phẩy, dấu nháy kép chưa escape, JSON bị cắt cụt.
    """
    if not resp_txt:
        return []

    clean_txt = resp_txt.strip()
    if clean_txt.startswith("```"):
        clean_txt = clean_txt.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    # 1. Thử parse trực tiếp chuẩn JSON
    try:
        data = json.loads(clean_txt)
        if isinstance(data, list) and data:
            return data
        elif isinstance(data, dict) and "segments" in data and isinstance(data["segments"], list):
            return data["segments"]
    except Exception:
        pass

    # 2. Sửa lỗi thiếu dấu phẩy giữa các object: "}\s*{" -> "}, {"
    fixed_txt = re.sub(r"\}\s*\{", "}, {", clean_txt)

    # 3. Thử phục hồi JSON bị cắt cụt ở cuối
    last_brace = fixed_txt.rfind("}")
    if last_brace != -1:
        try_salvage = fixed_txt[:last_brace + 1]
        if not try_salvage.startswith("["):
            first_bracket = try_salvage.find("[")
            if first_bracket != -1:
                try_salvage = try_salvage[first_bracket:]
            else:
                try_salvage = "[" + try_salvage
        try_salvage += "]"
        try:
            data = json.loads(try_salvage)
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass

    # 4. Regex Object-by-Object extraction (Cứu từng object một)
    extracted = []
    blocks = re.findall(r"\{[^{}]*\}", fixed_txt, re.DOTALL)
    for b in blocks:
        try:
            obj = json.loads(b)
            if isinstance(obj, dict) and any(k in obj for k in ["start_time", "start_sec", "script", "title"]):
                extracted.append(obj)
                continue
        except Exception:
            pass

        idx_m = re.search(r"\"index\"\s*:\s*(\d+)", b)
        st_m = re.search(r"\"start_time\"\s*:\s*\"([^\"]+)\"", b)
        en_m = re.search(r"\"end_time\"\s*:\s*\"([^\"]+)\"", b)
        va_m = re.search(r"\"visual_action\"\s*:\s*\"([^\"]*)\"", b)
        title_m = re.search(r"\"title\"\s*:\s*\"([^\"]*)\"", b)

        script_val = ""
        script_m = re.search(r"\"script\"\s*:\s*\"(.*?)(?:\"\s*\}|\"\s*,|\"$)", b, re.DOTALL)
        if script_m:
            script_val = script_m.group(1).replace('"', "").strip()
        else:
            script_parts = b.split('"script"')
            if len(script_parts) > 1:
                script_val = script_parts[1].replace(":", "").replace('"', "").replace("}", "").strip()

        if st_m or script_val:
            extracted.append({
                "index": int(idx_m.group(1)) if idx_m else len(extracted) + 1,
                "start_time": st_m.group(1) if st_m else "00:00",
                "end_time": en_m.group(1) if en_m else "00:10",
                "visual_action": va_m.group(1) if va_m else "",
                "title": title_m.group(1) if title_m else f"Phân cảnh {len(extracted)+1}",
                "script": script_val
            })

    return extracted


def get_audio_duration(audio_path: Path) -> float:
    """Lấy thời lượng chính xác của file audio."""
    if not audio_path or not Path(audio_path).exists():
        return 0.0
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path)
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        return float(res.stdout.strip())
    except Exception:
        return 0.0


def wrap_text_for_drawtext(text: str, max_chars_per_line: int = 38) -> str:
    """Ngắt dòng chữ mượt mà cho bộ lọc phụ đề FFmpeg drawtext."""
    words = text.split()
    lines = []
    cur_line = []
    cur_len = 0
    for w in words:
        if cur_len + len(w) + 1 > max_chars_per_line and cur_line:
            lines.append(" ".join(cur_line))
            cur_line = [w]
            cur_len = len(w)
        else:
            cur_line.append(w)
            cur_len += len(w) + 1
    if cur_line:
        lines.append(" ".join(cur_line))
    return "\n".join(lines[:2])  # Tối đa 2 dòng


def render_synced_recap_pipeline(
    video_path: Path,
    segments: list,
    voice_info: dict,
    output_video_path: Path,
    aspect_ratio: str = "16:9",
    bgm_volume: float = 0.12,
    voice_volume: float = 1.60,
    sync_mode: str = "smart_motion",  # "smart_motion", "voice_paced", "keep_original"
    burn_subtitles: bool = False,
    recap_mode: str = "movie_recap",  # "movie_recap", "naodong_review", "votritv_comedy"
    canvas_color: str = "0x94A48A",   # Xanh rêu pastel chuẩn kênh @78votritv
    footer_text: str = "",
    custom_bgm_path: str = None,
    mirror_flip: bool = False,
    cinematic_letterbox: bool = False,
    crop_bottom_sub_pct: float = 0.0,
    color_enhance: bool = True,
    logo_watermark_path: Optional[str] = None,
    voice_speed: float = 1.0,
    voice_engine: str = "capcut",
    ref_audio_path: Optional[str] = None,
    ref_start_sec: float = 5.0,
    ref_duration_sec: float = 8.0,
    progress_callback=None
) -> tuple:
    """
    Quy trình Dựng Video Recap & Review Phim Tốc Độ Cao & Khớp 100% Khung Hình (Parallel GPU Sync Engine):
    1. Tạo đồng thời đa luồng tất cả giọng đọc AI (CapCut TTS hoặc OmniVoice Zero-Shot Cloning).
    2. Cắt, lách bản quyền (Lật hình, Cắt sub gốc, Viền đen điện ảnh, Đóng logo tròn góc trái) & hòa âm song song.
    3. Tự động xuất kèm file phụ đề .SRT đồng bộ từng khung hình.
    Returns: (bool success, str final_path, list broll_items, str merged_audio_path)
    """
    if not segments:
        return False, "Không có phân cảnh nào để xử lý.", [], None

    from utils.hardware_accelerator import get_optimal_h264_encoder_args, detect_best_video_encoder

    temp_dir = Path(tempfile.mkdtemp())
    ffmpeg_exe = get_ffmpeg_cmd()
    total_segs = len(segments)
    total_source_dur = get_video_duration(video_path)
    hw_enc_info = detect_best_video_encoder()
    hw_enc_args = get_optimal_h264_encoder_args(use_gpu=True, bitrate="8500k", crf="18", preset="veryfast", fps=30)

    # Mặc định voice_type: Thanh Niên Tự Tin cho Vô Tri, Cô Gái Hoạt Ngôn / Nam Trầm cho Phim
    target_voice_id = voice_info.get("id") or voice_info.get("voice_type") or ("BV075_streaming" if recap_mode == "votritv_comedy" else "BV074_streaming")
    target_resource_id = voice_info.get("resource_id") or "7102355709945188865"

    # Chuẩn bị huy hiệu Logo tròn góc trên bên trái (nếu người dùng bật Watermark Logo chuẩn Não Động Review)
    prepared_badge_png = None
    if logo_watermark_path and Path(logo_watermark_path).exists():
        badge_candidate = temp_dir / "channel_badge_circle.png"
        prepared_badge_png = create_circular_logo_badge(Path(logo_watermark_path), badge_candidate, size=116)

    try:
        # ─── BƯỚC 1: TẠO GIỌNG ĐỌC ĐA LUỒNG SONG SONG (CAPCUT TTS HOẶC OMNIVOICE CLONING) ───
        use_omnivoice = False
        if voice_engine == "omnivoice" and ref_audio_path and Path(ref_audio_path).exists():
            try:
                from utils.omnivoice_wrapper import is_omnivoice_available, generate_cloned_voice
                if is_omnivoice_available():
                    use_omnivoice = True
            except Exception:
                use_omnivoice = False

        if progress_callback:
            eng_label = "OmniVoice Nhân Bản Giọng" if use_omnivoice else "AI Thuyết Minh"
            progress_callback(10, f"🎙️ Đang tạo giọng đọc ({eng_label}) cho {total_segs} phân cảnh...")

        tts_results = {}
        start_tts_time = time.time()

        def apply_voice_speed_if_needed(in_mp3: Path, speed: float) -> Path:
            if abs(speed - 1.0) < 0.03 or not in_mp3.exists():
                return in_mp3
            spd = max(0.8, min(1.5, float(speed)))
            fast_mp3 = in_mp3.parent / f"spd_{in_mp3.name}"
            cmd_spd = [
                ffmpeg_exe, "-y", "-nostdin",
                "-i", str(in_mp3),
                "-af", f"atempo={spd:.2f}",
                "-c:a", "libmp3lame", "-q:a", "2",
                str(fast_mp3)
            ]
            subprocess.run(cmd_spd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
            if fast_mp3.exists() and fast_mp3.stat().st_size > 200:
                return fast_mp3
            return in_mp3

        def worker_tts(idx_seg):
            idx, s_text = idx_seg
            if not s_text:
                return idx, False, 0.0, None
            v_mp3 = temp_dir / f"voice_seg_{idx:03d}.mp3"
            ok = False
            if use_omnivoice:
                from utils.omnivoice_wrapper import generate_cloned_voice
                ok, _ = generate_cloned_voice(
                    text=s_text,
                    ref_audio_path=str(ref_audio_path),
                    output_path=str(v_mp3),
                    ref_start_sec=ref_start_sec,
                    ref_duration_sec=ref_duration_sec
                )
            if not ok:
                ok, _ = generate_tts(
                    text=s_text,
                    voice_type=target_voice_id,
                    resource_id=target_resource_id,
                    output_path=str(v_mp3)
                )
            if ok and v_mp3.exists():
                v_mp3 = apply_voice_speed_if_needed(v_mp3, voice_speed)
                d = get_audio_duration(v_mp3)
                return idx, True, d, v_mp3
            return idx, False, 0.0, None

        tasks_tts = [(i, seg.get("script", "").strip()) for i, seg in enumerate(segments)]
        tts_workers = 1 if use_omnivoice else min(8, os.cpu_count() or 4)
        with concurrent.futures.ThreadPoolExecutor(max_workers=tts_workers) as executor_tts:
            fut_tts_map = {executor_tts.submit(worker_tts, t): t[0] for t in tasks_tts}
            completed_tts = 0
            for fut in concurrent.futures.as_completed(fut_tts_map):
                idx, has_v, v_dur, v_path = fut.result()
                tts_results[idx] = (has_v, v_dur, v_path)
                completed_tts += 1
                if progress_callback:
                    elapsed_t = time.time() - start_tts_time
                    rem_t = int((elapsed_t / completed_tts) * (total_segs - completed_tts))
                    pct = int(10 + (completed_tts / total_segs) * 30)
                    progress_callback(pct, f"🎙️ Đã tạo giọng đọc {completed_tts}/{total_segs} phân cảnh | ⏳ Còn lại: ~{rem_t}s...")

        voice_part_paths = []
        for i in range(total_segs):
            if i in tts_results and tts_results[i][0] and tts_results[i][2]:
                voice_part_paths.append(tts_results[i][2])

        # ─── BƯỚC 2: RENDER & HÒA ÂM PHÂN CẢNH ĐA LUỒNG (GPU + LÁCH BẢN QUYỀN CHUẨN NÃO ĐỘNG REVIEW) ───
        if progress_callback:
            progress_callback(45, f"🎞️ Đang dựng {total_segs} phân cảnh ({hw_enc_info['label']})...")

        rendered_scene_map = {}
        broll_item_map = {}
        scene_durations_map = {}
        font_footer_file = get_system_font("condensed")
        font_sub_file = get_system_font("bold")

        def worker_render_scene(i):
            seg = segments[i]
            has_voice, voice_dur, voice_mp3_path = tts_results.get(i, (False, 0.0, None))
            st_sec = float(seg.get("start_sec", 0.0))
            en_sec = float(seg.get("end_sec", st_sec + 4.0))
            if en_sec <= st_sec:
                en_sec = st_sec + 4.0
            orig_clip_dur = max(0.6, min(40.0, en_sec - st_sec))

            # 1. Trích xuất chính xác phân đoạn video gốc (đảm bảo đủ độ dài bao phủ lời thoại)
            target_clip_dur = round(voice_dur + 0.25, 2) if (has_voice and voice_dur > 0) else orig_clip_dur
            cut_extract_dur = max(orig_clip_dur, target_clip_dur + 0.5) if (has_voice and voice_dur > 0) else orig_clip_dur

            raw_subclip_path = temp_dir / f"raw_sub_{i:03d}.mp4"
            cmd_cut = [
                ffmpeg_exe, "-y", "-nostdin",
                "-ss", str(st_sec),
                "-t", str(cut_extract_dur),
                "-i", str(video_path),
                "-c", "copy",
                str(raw_subclip_path)
            ]
            subprocess.run(cmd_cut, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
            if not raw_subclip_path.exists() or raw_subclip_path.stat().st_size == 0:
                cmd_cut_fallback = [
                    ffmpeg_exe, "-y", "-nostdin",
                    "-accurate_seek",
                    "-ss", str(st_sec),
                    "-t", str(cut_extract_dur),
                    "-i", str(video_path),
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    str(raw_subclip_path)
                ]
                subprocess.run(cmd_cut_fallback, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)

            # 2. ĐỒNG BỘ THOẠI LIÊN TỤC & ĐIỀU CHỈNH CHUYỂN ĐỘNG (CONTINUOUS VOICE-PACED & SMART MOTION)
            repeat_cnt = 0
            setpts_filter = "setpts=PTS-STARTPTS"

            if has_voice and voice_dur > 0:
                if recap_mode == "votritv_comedy":
                    if voice_dur > orig_clip_dur:
                        repeat_cnt = max(1, math.ceil((voice_dur + 0.25) / orig_clip_dur) - 1)
                        final_clip_dur = round(max(voice_dur + 0.35, orig_clip_dur * (repeat_cnt + 1)), 2)
                    else:
                        final_clip_dur = round(max(orig_clip_dur, voice_dur + 0.25), 2)
                elif sync_mode == "keep_original":
                    final_clip_dur = round(max(orig_clip_dur, target_clip_dur), 2)
                elif sync_mode == "voice_paced":
                    final_clip_dur = target_clip_dur
                    setpts_filter = "setpts=PTS-STARTPTS"
                else:
                    speed_ratio = orig_clip_dur / target_clip_dur
                    if 0.85 <= speed_ratio <= 1.25:
                        setpts_filter = f"setpts={(1.0 / speed_ratio):.4f}*(PTS-STARTPTS)"
                    elif speed_ratio > 1.25:
                        setpts_filter = "setpts=0.8696*(PTS-STARTPTS)"
                    else:
                        setpts_filter = "setpts=PTS-STARTPTS"
                    final_clip_dur = target_clip_dur

                if (st_sec + final_clip_dur) > total_source_dur and total_source_dur > 0:
                    avail_dur = max(0.5, total_source_dur - st_sec)
                    if final_clip_dur > avail_dur:
                        repeat_cnt = max(1, math.ceil(final_clip_dur / avail_dur) - 1)
            else:
                final_clip_dur = round(orig_clip_dur, 2)

            scene_out_path = temp_dir / f"scene_{i:03d}.mp4"

            # 3. Xây dựng Chuỗi Filter Lách Bản Quyền & Khung Hình Điện Ảnh Chuẩn Não Động Review
            pre_fx_list = []
            if crop_bottom_sub_pct > 0.01:
                # Cắt bỏ phần đáy có chứa phụ đề gốc của phim (ví dụ 8% đáy) và giữ cân đối khung hình
                keep_h_ratio = max(0.75, 1.0 - float(crop_bottom_sub_pct))
                pre_fx_list.append(f"crop=iw*{keep_h_ratio:.3f}:ih*{keep_h_ratio:.3f}:(iw-iw*{keep_h_ratio:.3f})/2:0")
            if mirror_flip:
                pre_fx_list.append("hflip")
            if color_enhance:
                pre_fx_list.append("eq=contrast=1.04:saturation=1.05:brightness=0.01")

            pre_fx_str = (",".join(pre_fx_list) + ",") if pre_fx_list else ""

            is_votritv_canvas = (aspect_ratio == "9:16_votritv") or (recap_mode == "votritv_comedy" and "9:16" in aspect_ratio)

            if is_votritv_canvas:
                safe_canvas = canvas_color.replace("#", "0x")
                if not safe_canvas.startswith("0x"):
                    safe_canvas = f"0x{safe_canvas}"

                if footer_text and footer_text.strip():
                    f_footer_esc = font_footer_file.replace(" ", "\\ ") if font_footer_file else ""
                    f_footer_clause = f":fontfile=\\'{f_footer_esc}\\'" if f_footer_esc else ""
                    clean_footer = footer_text.strip().replace("'", "").replace('"', "")
                    footer_filter = f"[v_mid]drawtext=text='{clean_footer}'{f_footer_clause}:fontcolor=white:fontsize=58:x=(w-text_w)/2:y=1540:shadowcolor=black@0.35:shadowx=2:shadowy=2[v_base]"
                    base_v_filter = (
                        f"color=c={safe_canvas}:s=1080x1920:r=30[bg];"
                        f"[0:v]{pre_fx_str}scale=1080:-2:flags=lanczos,{setpts_filter}[fg];"
                        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[v_mid];"
                        f"{footer_filter}"
                    )
                else:
                    base_v_filter = (
                        f"color=c={safe_canvas}:s=1080x1920:r=30[bg];"
                        f"[0:v]{pre_fx_str}scale=1080:-2:flags=lanczos,{setpts_filter}[fg];"
                        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[v_base]"
                    )
                sub_y_pos = "1200"
                font_sz = "48"
            elif aspect_ratio == "9:16":
                base_v_filter = (
                    f"[0:v]{pre_fx_str}split=2[bg_src][fg_src];"
                    f"[bg_src]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,boxblur=25:2,eq=brightness=-0.03:contrast=1.05[bg];"
                    f"[fg_src]scale=1404:-2:flags=lanczos,crop=1080:ih:(iw-1080)/2:0,unsharp=3:3:0.6:3:3:0.3[fg];"
                    f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,{setpts_filter}[v_base]"
                )
                sub_y_pos = "h-360"
                font_sz = "44"
            else:
                letterbox_clause = ""
                if cinematic_letterbox:
                    # Viền đen điện ảnh 2.35:1 trên và dưới chuẩn khung hình kênh Não Động Review
                    letterbox_clause = ",drawbox=x=0:y=0:w=iw:h=68:color=black@1:t=fill,drawbox=x=0:y=ih-68:w=iw:h=68:color=black@1:t=fill"
                base_v_filter = (
                    f"[0:v]{pre_fx_str}scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos,"
                    f"crop=1920:1080,unsharp=5:5:0.8:3:3:0.4{letterbox_clause},fps=30,{setpts_filter}[v_base]"
                )
                sub_y_pos = "h-140"
                font_sz = "36"

            # Phụ đề chữ vàng viền đen (chỉ hiển thị khi người dùng chọn bật burn_subtitles)
            if burn_subtitles and seg.get("script", "").strip():
                clean_sub_text = seg.get("script", "").strip().replace("'", "").replace('"', "").replace(":", " -")
                if is_votritv_canvas:
                    clean_sub_text = clean_sub_text.upper()
                wrapped_sub = wrap_text_for_drawtext(clean_sub_text, max_chars_per_line=30 if "9:16" in aspect_ratio else 52)
                escaped_sub = wrapped_sub.replace("\n", "\\\n").replace("%", "\\%")
                f_sub_esc = font_sub_file.replace(" ", "\\ ") if font_sub_file else ""
                f_sub_clause = f":fontfile=\\'{f_sub_esc}\\'" if f_sub_esc else ""
                v_sub_stage = (
                    f"{base_v_filter};"
                    f"[v_base]drawtext=text='{escaped_sub}'{f_sub_clause}:fontcolor=yellow:bordercolor=black:borderw=5:fontsize={font_sz}:x=(w-text_w)/2:y={sub_y_pos}:shadowcolor=black@0.75:shadowx=3:shadowy=3[v_sub]"
                )
            else:
                v_sub_stage = f"{base_v_filter};[v_base]null[v_sub]"

            # Đính Huy Hiệu Logo Tròn Góc Trái-Trên (Chuẩn Não Động Review)
            if prepared_badge_png and prepared_badge_png.exists():
                badge_esc = str(prepared_badge_png).replace("\\", "/").replace(":", "\\:")
                v_filter_full = f"{v_sub_stage};movie='{badge_esc}'[logo];[v_sub][logo]overlay=42:22[v_out]"
            else:
                v_filter_full = f"{v_sub_stage};[v_sub]null[v_out]"

            # Render clip với stream_loop (lặp lại nếu thoại dài hơn video) và adelay cho voice
            input_v_target = raw_subclip_path if (raw_subclip_path.exists() and raw_subclip_path.stat().st_size > 0) else video_path
            input_v_args = ["-stream_loop", str(repeat_cnt), "-i", str(input_v_target)]

            if has_voice and voice_mp3_path and voice_mp3_path.exists():
                cmd = [
                    ffmpeg_exe, "-y",
                    "-nostdin",
                    *input_v_args,
                    "-i", str(voice_mp3_path),
                    "-filter_complex",
                    f"{v_filter_full};"
                    f"[0:a]volume={bgm_volume:.2f},asetpts=PTS-STARTPTS,aresample=48000:async=1000:first_pts=0[bgm];"
                    f"[1:a]volume={voice_volume:.2f},adelay=120|120,asetpts=PTS-STARTPTS,aresample=48000:async=1000:first_pts=0[voice];"
                    f"[bgm][voice]amix=inputs=2:duration=first:dropout_transition=0[a_out]",
                    "-map", "[v_out]",
                    "-map", "[a_out]",
                    *hw_enc_args,
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-ar", "48000",
                    "-ac", "2",
                    "-video_track_timescale", "30000",
                    "-t", str(final_clip_dur),
                    str(scene_out_path)
                ]
            else:
                cmd = [
                    ffmpeg_exe, "-y",
                    "-nostdin",
                    *input_v_args,
                    "-filter_complex",
                    f"{v_filter_full};"
                    f"[0:a]volume={bgm_volume:.2f},asetpts=PTS-STARTPTS,aresample=48000:async=1000:first_pts=0[a_out]",
                    "-map", "[v_out]",
                    "-map", "[a_out]",
                    *hw_enc_args,
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-ar", "48000",
                    "-ac", "2",
                    "-video_track_timescale", "30000",
                    "-t", str(final_clip_dur),
                    str(scene_out_path)
                ]

            render_timeout = max(120, int(final_clip_dur * 8))
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=render_timeout)
            except Exception:
                pass

            if scene_out_path.exists() and scene_out_path.stat().st_size > 1000:
                chk = subprocess.run([ffmpeg_exe, "-v", "error", "-i", str(scene_out_path)], capture_output=True, text=True, timeout=5)
                if "moov atom not found" not in chk.stderr and "Invalid data" not in chk.stderr:
                    return i, str(scene_out_path), {
                        "path": str(scene_out_path),
                        "duration_sec": final_clip_dur,
                        "duration_us": int(final_clip_dur * 1000000)
                    }
            return i, None, None

        max_workers_render = min(os.cpu_count() or 4, 4)
        rendered_count = 0
        start_render_all = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers_render) as executor_render:
            fut_render_map = {executor_render.submit(worker_render_scene, i): i for i in range(total_segs)}
            for fut in concurrent.futures.as_completed(fut_render_map):
                i_idx, sc_path, broll_info = fut.result()
                if sc_path:
                    rendered_scene_map[i_idx] = sc_path
                    broll_item_map[i_idx] = broll_info
                    scene_durations_map[i_idx] = broll_info["duration_sec"]
                rendered_count += 1
                if progress_callback:
                    elapsed_r = time.time() - start_render_all
                    avg_r = elapsed_r / rendered_count
                    rem_r = int(avg_r * (total_segs - rendered_count))
                    el_m, el_s = divmod(int(elapsed_r), 60)
                    rm_m, rm_s = divmod(rem_r, 60)
                    pct = int(45 + (rendered_count / total_segs) * 45)
                    progress_callback(
                        pct,
                        f"🎞️ Đã dựng {rendered_count}/{total_segs} phân cảnh ({int(rendered_count/total_segs*100)}%) | "
                        f"⏱️ Đã chạy: {el_m:02d}:{el_s:02d} | ⏳ Còn lại ước tính: ~{rm_m:02d}:{rm_s:02d}"
                    )

        rendered_scene_paths = [rendered_scene_map[i] for i in range(total_segs) if i in rendered_scene_map]
        broll_items_for_capcut = [broll_item_map[i] for i in range(total_segs) if i in broll_item_map]

        if not rendered_scene_paths:
            return False, "Không thể dựng được phân cảnh nào hợp lệ.", [], None

        # Xuất file phụ đề .SRT đồng bộ thời gian thực tế
        srt_output_path = output_video_path.with_suffix(".srt")
        export_synced_srt_file(segments, scene_durations_map, srt_output_path)

        # ─── BƯỚC 3: GHÉP NỐI TOÀN BỘ PHÂN CẢNH THÀNH VIDEO MASTER ───
        if progress_callback:
            progress_callback(92, "🔗 Đang ghép nối toàn bộ các phân cảnh thành Video Master 1080p...")

        # Lọc các scene thực sự mở được và nguyên vẹn
        valid_scenes = []
        for sp in rendered_scene_paths:
            p = Path(sp)
            if p.exists() and p.stat().st_size > 1000:
                chk = subprocess.run([ffmpeg_exe, "-v", "error", "-i", str(p)], capture_output=True, text=True, timeout=5)
                if "moov atom not found" not in chk.stderr and "Invalid data" not in chk.stderr:
                    valid_scenes.append(sp)

        if not valid_scenes:
            return False, "Không có phân cảnh nguyên vẹn nào để ghép nối.", [], None

        concat_list = temp_dir / "concat_scenes.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for sp in valid_scenes:
                f.write(f"file '{sp}'\n")

        output_video_path.parent.mkdir(parents=True, exist_ok=True)

        # Ghép nối Streamcopy Concat
        cmd_concat = [
            ffmpeg_exe, "-y",
            "-nostdin",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list),
            "-c:v", "copy",
            "-c:a", "copy",
            str(output_video_path)
        ]
        res_c = subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)

        # Fallback: Re-encode nếu streamcopy gặp vấn đề
        if not output_video_path.exists() or output_video_path.stat().st_size == 0:
            cmd_fallback = [
                ffmpeg_exe, "-y",
                "-nostdin",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list),
                "-r", "30",
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "17",
                "-b:v", "12000k",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "256k",
                "-ar", "48000",
                "-ac", "2",
                str(output_video_path)
            ]
            res_fb = subprocess.run(cmd_fallback, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
            if not output_video_path.exists() or output_video_path.stat().st_size == 0:
                err_detail = res_fb.stderr.decode("utf-8", errors="ignore").strip()[:300] if res_fb.stderr else (res_c.stderr.decode("utf-8", errors="ignore").strip()[:300] if res_c.stderr else "Lỗi không xác định")
                return False, f"Lỗi khi ghép nối các phân cảnh: {err_detail}", [], None

        # Chèn nhạc nền BGM (nếu có, tự động loop và mix mượt mà ở mức âm lượng thấp)
        target_bgm = custom_bgm_path
        if not target_bgm and recap_mode == "votritv_comedy":
            default_funny_bgm = Path("assets/audio/votritv_funny_bgm.mp3")
            if default_funny_bgm.exists():
                target_bgm = str(default_funny_bgm)

        if target_bgm and Path(target_bgm).exists() and output_video_path.exists() and output_video_path.stat().st_size > 0:
            if progress_callback:
                progress_callback(92, "🎵 Đang hòa âm nhạc nền Vô Tri TV tưng tửng mượt mà...")
            bgm_temp_output = temp_dir / "final_with_bgm.mp4"
            cmd_bgm = [
                ffmpeg_exe, "-y", "-nostdin",
                "-i", str(output_video_path),
                "-stream_loop", "-1",
                "-i", str(target_bgm),
                "-filter_complex",
                f"[0:a]volume=1.0[main_a];[1:a]volume={bgm_volume:.2f}[bgm_a];[main_a][bgm_a]amix=inputs=2:duration=first:dropout_transition=2[a_out]",
                "-map", "0:v",
                "-map", "[a_out]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                str(bgm_temp_output)
            ]
            try:
                subprocess.run(cmd_bgm, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=60)
                if bgm_temp_output.exists() and bgm_temp_output.stat().st_size > 0:
                    shutil.move(str(bgm_temp_output), str(output_video_path))
            except Exception:
                pass

        # Tạo file audio tổng hợp cho CapCut nếu có
        merged_voice_path = None
        if voice_part_paths:
            merged_voice_path = temp_dir / "merged_voice.mp3"
            voice_list = temp_dir / "voice_list.txt"
            with open(voice_list, "w", encoding="utf-8") as f:
                for vp in voice_part_paths:
                    f.write(f"file '{vp.name}'\n")
            cmd_vconcat = [
                ffmpeg_exe, "-y", "-nostdin", "-f", "concat", "-safe", "0",
                "-i", str(voice_list), "-c", "copy", str(merged_voice_path)
            ]
            subprocess.run(cmd_vconcat, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)

        if output_video_path.exists() and output_video_path.stat().st_size > 0:
            return True, str(output_video_path), broll_items_for_capcut, str(merged_voice_path) if merged_voice_path and merged_voice_path.exists() else None
        else:
            return False, "Lỗi khi ghép nối các phân cảnh.", [], None

    except Exception as e:
        return False, f"Lỗi dựng video đồng bộ: {str(e)}", [], None
