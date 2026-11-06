import os
import pysrt
import subprocess
import tempfile
import time
from pathlib import Path

def get_images_from_dir(directory: str) -> list:
    """Lấy danh sách các file ảnh hợp lệ từ thư mục"""
    supported_exts = {'.png', '.jpg', '.jpeg', '.webp'}
    images = []
    if os.path.exists(directory):
        for f in sorted(os.listdir(directory)):
            if Path(f).suffix.lower() in supported_exts:
                images.append(os.path.join(directory, f))
    return images

def create_video_from_srt_and_images(srt_path: str, images_dir: str, audio_path: str = None, output_path: str = None, resolution="1080:1920") -> tuple[bool, str]:
    """
    Tạo video từ chuỗi hình ảnh, được căn thời gian khớp chính xác với SRT.
    """
    try:
        if not output_path:
            out_dir = Path("output_clips")
            out_dir.mkdir(exist_ok=True)
            output_path = str(out_dir / f"autocut_{int(time.time())}.mp4")

        # 1. Lấy danh sách ảnh
        images = get_images_from_dir(images_dir)
        if not images:
            return False, "Không tìm thấy hình ảnh nào trong thư mục được chọn."

        # 2. Phân tích SRT để lấy Duration
        subs = pysrt.open(srt_path)
        if not subs:
            return False, "File SRT trống hoặc không hợp lệ."

        # 3. Tạo file Concat FFmpeg
        temp_dir = tempfile.mkdtemp()
        concat_file = os.path.join(temp_dir, "concat.txt")
        
        with open(concat_file, "w", encoding="utf-8") as f:
            for i, sub in enumerate(subs):
                # Tính duration theo giây
                start_sec = sub.start.ordinal / 1000.0
                end_sec = sub.end.ordinal / 1000.0
                duration = end_sec - start_sec
                
                if duration <= 0:
                    continue
                    
                # Tính khoảng trống (gap) trước sub này nếu có
                if i > 0:
                    prev_end = subs[i-1].end.ordinal / 1000.0
                    gap = start_sec - prev_end
                    if gap > 0:
                        # Giữ nguyên ảnh của sub trước đó cho phần gap
                        prev_img = images[(i-1) % len(images)]
                        f.write(f"file '{os.path.abspath(prev_img)}'\n")
                        f.write(f"duration {gap:.3f}\n")
                elif start_sec > 0:
                    # Khoảng trống đầu video
                    img = images[0]
                    f.write(f"file '{os.path.abspath(img)}'\n")
                    f.write(f"duration {start_sec:.3f}\n")
                
                # Assign ảnh theo round-robin
                img_path = images[i % len(images)]
                f.write(f"file '{os.path.abspath(img_path)}'\n")
                f.write(f"duration {duration:.3f}\n")
                
            # ffmpeg concat yêu cầu file cuối cùng được repeat lại tên (không có duration)
            if len(subs) > 0:
                last_img = images[(len(subs) - 1) % len(images)]
                f.write(f"file '{os.path.abspath(last_img)}'\n")
                
        # 4. Render Video bằng FFmpeg
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file
        ]
        
        if audio_path and os.path.exists(audio_path):
            cmd.extend(["-i", audio_path])
            
        # Thêm các bộ lọc Scale, Crop, Center
        w, h = resolution.split(":")
        vf_scale = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
        
        cmd.extend([
            "-vf", vf_scale,
            "-vsync", "vfr",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23"
        ])
        
        if audio_path and os.path.exists(audio_path):
            # Lấy âm thanh từ file audio
            cmd.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])
        else:
            # Không có âm thanh
            pass
            
        cmd.append(output_path)
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return False, f"FFmpeg Lỗi: {result.stderr}"
            
        return True, output_path
        
    except Exception as e:
        return False, f"Lỗi hệ thống: {str(e)}"
