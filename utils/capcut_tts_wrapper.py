import os
import sys
import json
import time
import requests
import subprocess
from pathlib import Path

# Thêm utils vào sys.path để có thể load capcut_common_task_client.py nếu cần
CURRENT_DIR = Path(__file__).parent
CAPCUT_API_DIR = CURRENT_DIR / "capcut_tts"
CLIENT_SCRIPT = CAPCUT_API_DIR / "capcut_common_task_client.py"
FAVORITES_FILE = CURRENT_DIR / "favorite_voices.json"

def get_favorite_voices():
    if not FAVORITES_FILE.exists():
        return []
    try:
        with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def toggle_favorite_voice(voice_id: str):
    favs = set(get_favorite_voices())
    if voice_id in favs:
        favs.remove(voice_id)
    else:
        favs.add(voice_id)
    with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
        json.dump(list(favs), f)


def get_available_voices(lang_filter: str = None):
    """Đọc danh sách giọng đọc từ Voice.json, hỗ trợ lọc theo ngôn ngữ"""
    voice_json_path = CAPCUT_API_DIR / "Voice.json"
    if not voice_json_path.exists():
        return []
    
    with open(voice_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    voices = []
    favs = get_favorite_voices()
    
    for v in data:
        vid = v.get("voice_type")
        # Bỏ qua các giọng bị lỗi ID từ file JSON gốc
        if not vid or vid in ["en", "th", "vi", "zh"]:
            continue
            
        v_lan = v.get("lan")
        
        # Xử lý lọc theo lang_filter
        if lang_filter and lang_filter != "all":
            if lang_filter == "ja" and v_lan not in ["ja", "jp"]:
                continue
            elif lang_filter == "other" and v_lan not in ["fr", "de", "pt", "br"]:
                continue
            elif lang_filter not in ["ja", "other"] and v_lan != lang_filter:
                continue

        is_fav = vid in favs
        prefix = "⭐ " if is_fav else ""
        
        voices.append({
            "id": vid,
            "resource_id": v.get("resource_id"),
            "name": f"{prefix}{v.get('display_name')} ({v.get('lang', v_lan)})",
            "lan": v_lan,
            "is_fav": is_fav
        })
            
    # Sort favorites to top
    voices.sort(key=lambda x: (not x["is_fav"], x["name"]))
    return voices

def chunk_text(text: str, max_chars: int = 250) -> list:
    words = text.replace('\n', ' \n ').split(' ')
    chunks = []
    current_chunk = []
    current_len = 0
    for w in words:
        if not w: continue
        if current_len + len(w) + 1 > max_chars and current_chunk:
            chunks.append(" ".join(current_chunk).replace(' \n ', '\n').strip())
            current_chunk = [w]
            current_len = len(w)
        else:
            current_chunk.append(w)
            current_len += len(w) + 1
    if current_chunk:
        chunks.append(" ".join(current_chunk).replace(' \n ', '\n').strip())
    return chunks

def _generate_tts_single(text: str, voice_type: str, resource_id: str, output_path: str):
    """
    Sinh TTS sử dụng capcut_common_task_client.py cho 1 đoạn ngắn
    Returns: (bool success, str error_or_path)
    """
    try:
        # 1. Tạo task TTS
        cmd_new = [
            sys.executable, str(CLIENT_SCRIPT),
            "tts-new",
            "--text", text,
            "--voice", voice_type,
            "--resource-id", resource_id
        ]
        
        result = subprocess.run(cmd_new, capture_output=True, text=True)
        if result.returncode != 0:
            return False, f"Lỗi tạo task: {result.stderr}"
            
        # Parse JSON output (last line is usually the JSON, but we can search for {)
        output = result.stdout.strip()
        json_str = output[output.find('{'):]
        
        data = json.loads(json_str)
        if data.get("ret") != "0":
            return False, f"API Error: {data.get('errmsg')}"
            
        tasks = data.get("data", {}).get("tasks", [])
        if not tasks:
            return False, "Không nhận được task ID từ CapCut"
            
        task_id = tasks[0]["id"]
        token = tasks[0]["token"]
        
        # 2. Polling task kết quả
        cmd_query = [
            sys.executable, str(CLIENT_SCRIPT),
            "tts-query",
            "--task-id", task_id,
            "--token", token
        ]
        
        max_retries = 90
        for _ in range(max_retries):
            time.sleep(1)
            q_res = subprocess.run(cmd_query, capture_output=True, text=True)
            if q_res.returncode != 0:
                continue
                
            q_out = q_res.stdout.strip()
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
                    
                    audio_subs = payload.get("audio_subtitles", [])
                    if not audio_subs:
                        return False, "Không có audio url trong payload"
                        
                    speech_url = audio_subs[0].get("speech_url")
                    
                    # 3. Tải Audio
                    r = requests.get(speech_url)
                    if r.status_code == 200:
                        with open(output_path, "wb") as f:
                            f.write(r.content)
                        return True, output_path
                    else:
                        return False, "Lỗi tải file audio MP3"
                        
                elif status in ["failed", "error"]:
                    err_msg = q_tasks[0].get("err_msg", "Unknown error")
                    err_code = q_tasks[0].get("err_code", "No code")
                    return False, f"Task thất bại trên server CapCut: {err_msg} (Mã lỗi: {err_code})"
            except Exception:
                pass
                
        return False, "Timeout khi chờ CapCut xử lý"
        
    except Exception as e:
        return False, f"Lỗi hệ thống: {str(e)}"

def generate_tts(text: str, voice_type: str, resource_id: str = None, output_path: str = None):
    # Hỗ trợ truyền 3 tham số (text, voice_type, output_path)
    if output_path is None and resource_id is not None and (resource_id.endswith(".mp3") or "/" in resource_id):
        output_path = resource_id
        resource_id = None

    if not resource_id:
        voices = get_available_voices()
        for v in voices:
            if v["id"] == voice_type:
                resource_id = v.get("resource_id")
                break
        if not resource_id:
            # Fallback default resource_id nếu không tìm thấy
            resource_id = "7637460351541447956"

    chunks = chunk_text(text, 250)
    if not chunks:
        return False, "Văn bản rỗng"
        
    if len(chunks) == 1:
        return _generate_tts_single(chunks[0], voice_type, resource_id, output_path)
        
    import tempfile
    import shutil
    
    temp_dir = Path(tempfile.mkdtemp())
    try:
        mp3_files = []
        for i, chunk in enumerate(chunks):
            if i > 0:
                time.sleep(2) # Delay to avoid CapCut rate limits (shark block)
            chunk_path = temp_dir / f"chunk_{i}.mp3"
            
            # Thử lại nhiều lần nếu server CapCut bị nghẽn mạng / RPC Error
            max_chunk_retries = 5
            success = False
            err = ""
            for attempt in range(max_chunk_retries):
                success, err = _generate_tts_single(chunk, voice_type, resource_id, str(chunk_path))
                if success:
                    break
                time.sleep(3 * (attempt + 1)) # Chờ 3s, 6s, 9s... rồi thử lại
                
            if not success:
                return False, f"Lỗi xử lý đoạn văn bản thứ {i+1} (đã thử lại {max_chunk_retries} lần): {err}"
            mp3_files.append(chunk_path)
            
        list_file = temp_dir / "list.txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for mp3 in mp3_files:
                f.write(f"file '{mp3.name}'\n")
                
        cmd_concat = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", 
            "-i", str(list_file), "-c", "copy", output_path
        ]
        subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, output_path
        
    except Exception as e:
        return False, f"Lỗi khi nối audio: {str(e)}"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def get_or_create_voice_preview(voice_data: dict) -> tuple:
    """
    Tạo hoặc lấy file âm thanh mẫu ngắn cho 1 giọng đọc (có cơ chế caching).
    """
    preview_dir = Path("output_clips") / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    
    voice_id = voice_data.get("id")
    resource_id = voice_data.get("resource_id")
    lang = voice_data.get("lan", "vi")
    
    preview_file = preview_dir / f"preview_{voice_id}.mp3"
    if preview_file.exists():
        return True, str(preview_file)
        
    sample_text_map = {
        "vi": "Xin chào, đây là giọng đọc thử nghiệm của tôi.",
        "en": "Hello, this is a sample of my reading voice.",
        "zh": "你好，这是我的语音测试。",
        "ja": "こんにちは、これは私の音声サンプルです。",
        "jp": "こんにちは、これは私の音声サンプルです。",
        "es": "Hola, este es un ejemplo de mi voz.",
        "th": "สวัสดีครับ นี่คือตัวอย่างเสียงของผม",
        "id": "Halo, ini adalah contoh suara saya."
    }
    sample_text = sample_text_map.get(lang, "Hello, this is a sample of my reading voice.")
    
    success, result_or_err = generate_tts(
        text=sample_text,
        voice_type=voice_id,
        resource_id=resource_id,
        output_path=str(preview_file)
    )
    return success, result_or_err

def add_custom_voice(display_name: str, voice_type: str, resource_id: str, lan: str = "en", lang: str = "en-US") -> tuple:
    """
    Thêm hoặc cập nhật giọng đọc mới vào Voice.json
    """
    voice_json_path = CAPCUT_API_DIR / "Voice.json"
    if not voice_json_path.exists():
        data = []
    else:
        try:
            with open(voice_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            return False, f"Lỗi đọc Voice.json: {e}"
            
    # Kiểm tra xem đã tồn tại chưa
    for item in data:
        if item.get("voice_type") == voice_type:
            item["display_name"] = display_name
            item["resource_id"] = resource_id
            item["lan"] = lan
            item["lang"] = lang
            with open(voice_json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True, f"Đã cập nhật giọng '{display_name}' ({voice_type})"
            
    from datetime import datetime
    new_item = {
        "lan": lan,
        "lang": lang,
        "voice_type": voice_type,
        "display_name": display_name,
        "resource_id": resource_id,
        "captured_at": datetime.now().isoformat()
    }
    data.insert(0, new_item)
    
    try:
        with open(voice_json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True, f"Đã thêm thành công giọng '{display_name}' ({voice_type}) vào hệ thống!"
    except Exception as e:
        return False, f"Lỗi ghi Voice.json: {e}"


