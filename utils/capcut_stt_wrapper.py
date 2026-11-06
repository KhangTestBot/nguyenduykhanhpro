import sys
import json
import subprocess
import time
import tempfile
from pathlib import Path

CURRENT_DIR = Path(__file__).parent
CAPCUT_API_DIR = CURRENT_DIR / "capcut_tts"
CLIENT_SCRIPT = CAPCUT_API_DIR / "capcut_common_task_client.py"

def generate_stt(file_path: str, language: str = "vi-VN"):
    """
    Tải file lên và tạo STT.
    Returns: (bool success, dict payload_or_error)
    """
    temp_audio_file = None
    try:
        p = Path(file_path)
        # Nếu file là video hoặc dung lượng > 50MB, nén/tách audio sang MP3 mono 64k nhẹ nhàng
        if p.suffix.lower() in [".mp4", ".mov", ".mkv", ".webm", ".avi", ".flv", ".m4v"] or (p.exists() and p.stat().st_size > 50 * 1024 * 1024):
            temp_dir = tempfile.mkdtemp()
            temp_audio_file = Path(temp_dir) / "converted_audio.mp3"
            cmd_conv = [
                "ffmpeg", "-y", "-i", str(p),
                "-vn", "-acodec", "libmp3lame", "-ac", "1", "-ar", "16000", "-b:a", "64k",
                str(temp_audio_file)
            ]
            conv_res = subprocess.run(cmd_conv, capture_output=True)
            if conv_res.returncode == 0 and temp_audio_file.exists() and temp_audio_file.stat().st_size > 0:
                file_path = str(temp_audio_file)

        # 1. Gọi lệnh stt-file
        cmd = [
            sys.executable, str(CLIENT_SCRIPT),
            "stt-file",
            "--audio-file", file_path,
            "--language", language
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return False, f"Lỗi tải file / tạo task: {result.stderr}"
            
        # Tìm JSON từ stdout (lấy dòng cuối cùng)
        output = result.stdout.strip()
        lines = [line.strip() for line in output.split('\n') if line.strip().startswith('{')]
        if not lines:
            return False, f"Không tìm thấy JSON trả về. Output: {output}"
            
        json_str = lines[-1]
        data = json.loads(json_str)
        if data.get("ret") != "0":
            return False, f"API Error: {data.get('errmsg')}"
            
        tasks = data.get("data", {}).get("tasks", [])
        if not tasks:
            return False, "Không nhận được task ID từ CapCut"
            
        task_id = tasks[0]["id"]
        token = tasks[0]["token"]
        
        # 2. Polling
        cmd_query = [
            sys.executable, str(CLIENT_SCRIPT),
            "stt-query",
            "--task-id", task_id,
            "--token", token
        ]
        
        max_retries = 300 # Audio dài có thể tốn thời gian upload + STT (5 phút)
        for _ in range(max_retries):
            time.sleep(1)
            q_res = subprocess.run(cmd_query, capture_output=True, text=True)
            if q_res.returncode != 0:
                continue
                
            q_out = q_res.stdout.strip()
            if '{' not in q_out: continue
            q_json_str = q_out[q_out.find('{'):]
            
            try:
                q_data = json.loads(q_json_str)
                q_tasks = q_data.get("data", {}).get("tasks", [])
                if not q_tasks:
                    continue
                    
                status = q_tasks[0].get("status")
                if status == "succeed":
                    payload_str = q_tasks[0].get("payload", "{}")
                    payload = json.loads(payload_str)
                    return True, payload
                elif status in ["failed", "error"]:
                    err_msg = q_tasks[0].get("err_msg", "Unknown error")
                    err_code = q_tasks[0].get("err_code", "No code")
                    return False, f"Task thất bại trên server: {err_msg} (Mã lỗi: {err_code})"
            except Exception:
                pass
                
        return False, "Timeout khi chờ CapCut xử lý STT"
    except Exception as e:
        return False, f"Lỗi hệ thống: {str(e)}"
    finally:
        if temp_audio_file and Path(temp_audio_file).exists():
            try:
                import shutil
                shutil.rmtree(Path(temp_audio_file).parent, ignore_errors=True)
            except Exception:
                pass

def format_ms_to_srt_time(ms: int) -> str:
    seconds, ms = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"

PUNCTUATIONS = set('.,?!:;。，！？、；：…~')

def is_cjk(text: str) -> bool:
    """Kiểm tra chuỗi có chứa ký tự tiếng Trung/Nhật/Hàn hay không."""
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff' or '\u3040' <= ch <= '\u30ff':
            return True
    return False

def split_long_text_segment(text: str, start_time: int, end_time: int, max_chars: int = 15, max_duration_ms: int = 3500) -> list:
    """Chia nhỏ một đoạn hội thoại dài thành các dòng phụ đề ngắn 2-4 giây với timestamp nội suy tỷ lệ."""
    import re
    total_duration = max(100, end_time - start_time)
    
    # Tách theo khoảng trắng, dấu câu tiếng Trung & tiếng Anh
    raw_tokens = [c.strip() for c in re.split(r'([ \t\u3000。，！？、；：…?!:;,~]+)', text) if c.strip()]
    if not raw_tokens:
        return [{"text": text.strip(), "start_time": start_time, "end_time": end_time}]
        
    cjk = is_cjk(text)
    limit = max_chars if cjk else 35
    
    phrases = []
    curr = ""
    for tok in raw_tokens:
        if tok in '。，！？、；：…?!:;,~':
            if curr:
                curr += tok
                phrases.append(curr)
                curr = ""
            continue
        if len(curr) + len(tok) > limit and curr:
            phrases.append(curr)
            curr = tok
        else:
            sep = "" if (cjk or not curr) else " "
            curr = curr + sep + tok if curr else tok
            
    if curr:
        phrases.append(curr)
        
    if not phrases:
        phrases = [text]

    # Tính toán timestamp theo độ dài ký tự của từng câu con
    total_len = sum(len(p) for p in phrases) or 1
    results = []
    cur_t = start_time
    for i, p in enumerate(phrases):
        p_len = len(p)
        dur = int((p_len / total_len) * total_duration)
        p_end = end_time if i == len(phrases) - 1 else min(end_time, cur_t + dur)
        results.append({
            "text": p.strip(),
            "start_time": cur_t,
            "end_time": p_end
        })
        cur_t = p_end
        
    return results

def payload_to_srt(payload: dict, max_duration_ms: int = 4800, max_words_per_line: int = 10) -> str:
    """
    Chuyển đổi kết quả STT thành phụ đề SRT tiêu chuẩn, tự nhiên và trọn vẹn từng câu.
    Ngăn chặn việc ngắt dòng vụn vặt (1-2 từ) bằng thuật toán ghép câu ngữ nghĩa thông minh.
    """
    utterances = payload.get("utterances", [])
    if not utterances:
        audio_subs = payload.get("audio_subtitles", [])
        if audio_subs and "utterances" in audio_subs[0]:
            utterances = audio_subs[0]["utterances"]

    all_segments = []

    for u in utterances:
        u_text = u.get("text", "").strip()
        u_start = u.get("start_time", 0)
        u_end = u.get("end_time", 0)
        u_words = u.get("words", [])

        if not u_text and not u_words:
            continue

        # Nếu utterance có danh sách từ chi tiết
        if u_words and len(u_words) > 1:
            cjk_mode = any(is_cjk(w.get("text", "")) for w in u_words[:10])
            curr_words = []
            curr_start = -1
            curr_end = -1

            for i, w in enumerate(u_words):
                t = w.get("text", "").strip()
                if not t:
                    continue
                st = w.get("start_time", 0)
                et = w.get("end_time", 0)

                if curr_start == -1:
                    curr_start = st
                curr_end = et
                curr_words.append(t)

                join_char = "" if cjk_mode else " "
                combined_text = join_char.join(curr_words).strip()
                duration = curr_end - curr_start

                # Khoảng lặng thật sự giữa các câu (tối thiểu 750ms)
                has_real_pause = False
                if i + 1 < len(u_words):
                    next_st = u_words[i + 1].get("start_time", 0)
                    if next_st - et >= 750:
                        has_real_pause = True

                ends_with_punct = any(t.endswith(p) for p in PUNCTUATIONS)
                
                if cjk_mode:
                    len_limit = len(combined_text) >= 16
                    should_break = ends_with_punct or (len_limit and len(combined_text) >= 8) or duration >= max_duration_ms or (has_real_pause and len(combined_text) >= 6)
                else:
                    word_count = len(combined_text.split())
                    len_limit = word_count >= max_words_per_line or len(combined_text) >= 55
                    should_break = (ends_with_punct and (duration >= 2000 or word_count >= 5)) or len_limit or duration >= max_duration_ms or (has_real_pause and word_count >= 5)

                if should_break and len(combined_text) > 0:
                    all_segments.append({
                        "start_time": curr_start,
                        "end_time": curr_end,
                        "text": combined_text
                    })
                    curr_words = []
                    curr_start = -1

            if curr_words:
                join_char = "" if cjk_mode else " "
                all_segments.append({
                    "start_time": curr_start,
                    "end_time": curr_end,
                    "text": join_char.join(curr_words).strip()
                })
        else:
            # Utterance không có danh sách từ hoặc là 1 câu nguyên khối
            duration = u_end - u_start
            if duration > max_duration_ms or len(u_text) > 60:
                chunks = split_long_text_segment(u_text, u_start, u_end, max_chars=18, max_duration_ms=max_duration_ms)
                all_segments.extend(chunks)
            else:
                all_segments.append({
                    "start_time": u_start,
                    "end_time": u_end,
                    "text": u_text
                })

    if not all_segments:
        return ""

    # Gộp các đoạn phụ đề quá ngắn (< 1.5s hoặc < 3 từ) vào câu liền kề để phụ đề không bị vụn
    merged_segments = []
    for seg in all_segments:
        text = seg["text"].strip()
        if not text:
            continue
        
        words = text.split()
        dur = seg["end_time"] - seg["start_time"]
        
        if merged_segments:
            prev = merged_segments[-1]
            prev_text = prev["text"].strip()
            prev_words = prev_text.split()
            prev_dur = prev["end_time"] - prev["start_time"]
            prev_ends_punc = any(prev_text.endswith(p) for p in ['.', '!', '?', ';', '。', '！', '？'])
            
            # Nếu câu trước hoặc câu hiện tại quá ngắn (1-2 từ) và câu trước không có dấu chấm hết câu -> gộp lại
            if not prev_ends_punc and (len(words) <= 2 or dur < 1400) and (len(prev_words) + len(words) <= max_words_per_line + 3) and (prev_dur + dur <= max_duration_ms + 1000):
                prev["end_time"] = seg["end_time"]
                prev["text"] = f"{prev_text} {text}".strip()
                continue

        merged_segments.append(seg)

    lines = []
    for idx, seg in enumerate(merged_segments, 1):
        start = format_ms_to_srt_time(seg["start_time"])
        end = format_ms_to_srt_time(seg["end_time"])
        text = seg["text"].strip()
        if text:
            lines.append(f"{idx}\n{start} --> {end}\n{text}\n")

    return "\n".join(lines)

def payload_to_text(payload: dict) -> str:
    utterances = payload.get("utterances", [])
    if not utterances:
        audio_subs = payload.get("audio_subtitles", [])
        if audio_subs and "utterances" in audio_subs[0]:
            utterances = audio_subs[0]["utterances"]
            
    return "\n".join(u.get("text", "").strip() for u in utterances if u.get("text", "").strip())


def transcribe_audio_to_srt(audio_path: str, output_srt_path: str, language: str = "vi-VN") -> tuple:
    """
    Nhận diện giọng nói từ file âm thanh và lưu thành file phụ đề .srt hoàn chỉnh.
    """
    ok, result = generate_stt(audio_path, language=language)
    if not ok:
        return False, str(result)
    try:
        srt_content = payload_to_srt(result)
        with open(output_srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)
        return True, output_srt_path
    except Exception as e:
        return False, f"Lỗi tạo file SRT: {str(e)}"
