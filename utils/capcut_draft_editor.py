import os
import json
import uuid
import shutil
from pathlib import Path
import pysrt

def get_mac_capcut_projects():
    """
    Tìm danh sách các Project CapCut hiện có trên máy Mac.
    Trả về danh sách dictionary: [{"name": "0719", "path": "/Users/.../0719/draft_content.json"}]
    """
    meta_path = os.path.expanduser("~/Movies/CapCut/User Data/Projects/com.lveditor.draft/root_meta_info.json")
    if not os.path.exists(meta_path):
        # Có thể người dùng cài CapCut ở thư mục khác, tìm theo đường dẫn mặc định thay thế
        meta_path = os.path.expanduser("~/Documents/capcut/CapCut Drafts/root_meta_info.json")
        if not os.path.exists(meta_path):
            return []
        
    try:
        with open(meta_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        drafts = []
        for draft in data.get("all_draft_store", []):
            name = draft.get("draft_name")
            json_file = draft.get("draft_json_file")
            if name and json_file and os.path.exists(json_file):
                try:
                    mtime = os.path.getmtime(json_file)
                    from datetime import datetime
                    mtime_str = datetime.fromtimestamp(mtime).strftime("%d/%m %H:%M")
                except Exception:
                    mtime = 0
                    mtime_str = ""
                drafts.append({
                    "name": name,
                    "path": json_file,
                    "modified_time": mtime,
                    "modified_str": mtime_str
                })
        drafts.sort(key=lambda d: d.get("modified_time", 0), reverse=True)
        return drafts
    except Exception as e:
        print(f"Error reading root_meta_info: {e}")
        return []

def backup_draft(draft_json_path):
    """Tạo file backup .bak nếu chưa có"""
    backup_path = draft_json_path + ".bak"
    shutil.copy2(draft_json_path, backup_path)
    return backup_path

def generate_uuid():
    return str(uuid.uuid4()).upper()

def get_template_segment(data):
    """Tìm 1 segment mẫu để clone các properties phức tạp"""
    for track in data.get('tracks', []):
        if track.get('type') == 'video':
            for seg in track.get('segments', []):
                # Kiểm tra xem segment này trỏ đến material nào
                mat_id = seg.get('material_id')
                for vid in data.get('materials', {}).get('videos', []):
                    if vid.get('id') == mat_id and vid.get('type') == 'photo':
                        return seg, vid
    # Fallback to any video material
    for track in data.get('tracks', []):
        if track.get('type') == 'video':
            for seg in track.get('segments', []):
                mat_id = seg.get('material_id')
                for vid in data.get('materials', {}).get('videos', []):
                    if vid.get('id') == mat_id:
                        return seg, vid
    return None, None

def create_ken_burns_keyframes(duration_us: int) -> list:
    """
    Tạo hiệu ứng Ken Burns mượt mà:
    - Zoom từ từ vào khoảng 5% - 10% (scale: 1.0 -> 1.05..1.10)
    - Kết hợp Pan/Drift ngẫu nhiên sang Trái, Phải, Trên, Dưới hoặc chéo nhẹ nhàng
    """
    import random
    
    # Mức zoom từ 5% đến 10% (1.05 đến 1.10)
    zoom_scale = round(random.uniform(1.05, 1.10), 3)
    
    # Các kiểu chuyển động ngẫu nhiên: (start_scale, end_scale, start_x, end_x, start_y, end_y)
    motion_types = [
        # Zoom vào + Pan sang Phải
        (1.0, zoom_scale, 0.0, round(random.uniform(0.015, 0.035), 3), 0.0, 0.0),
        # Zoom vào + Pan sang Trái
        (1.0, zoom_scale, 0.0, round(random.uniform(-0.035, -0.015), 3), 0.0, 0.0),
        # Zoom vào + Pan lên Trên
        (1.0, zoom_scale, 0.0, 0.0, 0.0, round(random.uniform(0.015, 0.035), 3)),
        # Zoom vào + Pan xuống Dưới
        (1.0, zoom_scale, 0.0, 0.0, 0.0, round(random.uniform(-0.035, -0.015), 3)),
        # Zoom vào + Pan từ Trái sang Phải
        (1.0, zoom_scale, round(random.uniform(-0.02, -0.01), 3), round(random.uniform(0.01, 0.02), 3), 0.0, 0.0),
        # Zoom vào + Pan từ Phải sang Trái
        (1.0, zoom_scale, round(random.uniform(0.01, 0.02), 3), round(random.uniform(-0.02, -0.01), 3), 0.0, 0.0),
        # Zoom vào + Pan chéo Lên Phải
        (1.0, zoom_scale, 0.0, round(random.uniform(0.012, 0.025), 3), 0.0, round(random.uniform(0.012, 0.025), 3)),
        # Zoom vào + Pan chéo Xuống Trái
        (1.0, zoom_scale, 0.0, round(random.uniform(-0.025, -0.012), 3), 0.0, round(random.uniform(-0.025, -0.012), 3)),
    ]
    start_s, end_s, sx, ex, sy, ey = random.choice(motion_types)
    
    kf_lists = []
    
    def make_kf_list(prop_type, v_start, v_end):
        return {
            "id": generate_uuid(),
            "material_id": "",
            "property_type": prop_type,
            "keyframe_list": [
                {
                    "curveType": "Line",
                    "graphID": "",
                    "id": generate_uuid(),
                    "left_control": {"x": 0.0, "y": 0.0},
                    "right_control": {"x": 0.0, "y": 0.0},
                    "time_offset": 0,
                    "values": [float(v_start)]
                },
                {
                    "curveType": "Line",
                    "graphID": "",
                    "id": generate_uuid(),
                    "left_control": {"x": 0.0, "y": 0.0},
                    "right_control": {"x": 0.0, "y": 0.0},
                    "time_offset": int(duration_us),
                    "values": [float(v_end)]
                }
            ]
        }
    
    # Scale X & Scale Y
    kf_lists.append(make_kf_list("KFTypeScaleX", start_s, end_s))
    kf_lists.append(make_kf_list("KFTypeScaleY", start_s, end_s))
    
    # Position X (nếu có chuyển động)
    if sx != 0.0 or ex != 0.0:
        kf_lists.append(make_kf_list("KFTypePositionX", sx, ex))
    
    # Position Y (nếu có chuyển động)
    if sy != 0.0 or ey != 0.0:
        kf_lists.append(make_kf_list("KFTypePositionY", sy, ey))
        
    return kf_lists


def apply_ken_burns_to_segment(seg: dict, duration_us: int, data: dict):
    """
    Gắn keyframe zoom & pan vào segment và đăng ký vào keyframes['videos'] của draft
    """
    kf_lists = create_ken_burns_keyframes(duration_us)
    seg["common_keyframes"] = kf_lists
    seg["keyframe_refs"] = [kf["id"] for kf in kf_lists]
    
    if "keyframes" not in data or not isinstance(data["keyframes"], dict):
        data["keyframes"] = {
            "videos": [], "audios": [], "texts": [], "stickers": [],
            "filters": [], "adjusts": [], "handwrites": [], "effects": []
        }
    if "videos" not in data["keyframes"]:
        data["keyframes"]["videos"] = []
        
    for kf in kf_lists:
        data["keyframes"]["videos"].append(kf)


def create_photo_material(image_path, template_vid, duration_us):
    import copy
    new_vid = copy.deepcopy(template_vid) if template_vid else {
        "id": generate_uuid(),
        "type": "photo",
        "path": image_path,
        "duration": duration_us,
        "width": 1080,
        "height": 1920,
        "crop_scale": 1.0,
        "crop_ratio": "free",
        "extra_type_option": 0
    }
    
    new_vid["id"] = generate_uuid()
    new_vid["type"] = "photo"
    new_vid["path"] = os.path.abspath(image_path)
    new_vid["duration"] = duration_us
    new_vid["material_name"] = os.path.basename(image_path)
    return new_vid

def inject_timeline_to_draft(draft_json_path, srt_path, images, insert_mode="new_track"):
    """
    draft_json_path: Đường dẫn tới draft_content.json
    srt_path: Đường dẫn tới SRT
    images: list các đường dẫn ảnh
    insert_mode: "new_track" hoặc "main_track"
    """
    try:
        project_dir = os.path.dirname(draft_json_path)
        json_files = []
        for root, dirs, files in os.walk(project_dir):
            if "draft_content.json" in files:
                json_files.append(os.path.join(root, "draft_content.json"))
                
        subs = pysrt.open(srt_path)
        if not subs or not images:
            return False, "Không có dữ liệu phụ đề hoặc hình ảnh."

        for current_json_path in json_files:
            backup_draft(current_json_path)
            
            with open(current_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            template_seg, template_vid = get_template_segment(data)
        
            if "materials" not in data:
                data["materials"] = {}
            if "videos" not in data["materials"]:
                data["materials"]["videos"] = []
                
            if "keyframes" not in data or not isinstance(data["keyframes"], dict):
                data["keyframes"] = {
                    "videos": [], "audios": [], "texts": [], "stickers": [],
                    "filters": [], "adjusts": [], "handwrites": [], "effects": []
                }
            if "videos" not in data["keyframes"]:
                data["keyframes"]["videos"] = []
                
            new_segments = []
            current_time_us = 0
            
            # Calculate timestamps
            for i, sub in enumerate(subs):
                start_us = int((sub.start.ordinal / 1000.0) * 1000000)
                end_us = int((sub.end.ordinal / 1000.0) * 1000000)
                duration_us = end_us - start_us
                
                if duration_us <= 0:
                    continue
                    
                # Xử lý gap
                if start_us > current_time_us:
                    gap_duration = start_us - current_time_us
                    gap_img = images[(i - 1) % len(images)] if i > 0 else images[0]
                    
                    mat = create_photo_material(gap_img, template_vid, gap_duration)
                    data["materials"]["videos"].append(mat)
                    
                    import copy
                    new_seg = copy.deepcopy(template_seg) if template_seg else {
                        "id": generate_uuid(),
                        "speed": 1.0,
                        "volume": 1.0,
                        "clip": {"scale": {"x":1.0, "y":1.0}, "rotation": 0.0, "transform": {"x":0.0, "y":0.0}, "flip": {"vertical": False, "horizontal": False}, "alpha": 1.0},
                        "extra_material_refs": []
                    }
                    new_seg["id"] = generate_uuid()
                    new_seg["material_id"] = mat["id"]
                    new_seg["source_timerange"] = {"start": 0, "duration": gap_duration}
                    new_seg["target_timerange"] = {"start": current_time_us, "duration": gap_duration}
                    
                    # Áp dụng Ken Burns Zoom & Pan ngẫu nhiên
                    apply_ken_burns_to_segment(new_seg, gap_duration, data)
                    
                    new_segments.append(new_seg)
                    current_time_us += gap_duration
                    
                # Xử lý đoạn chính
                img = images[i % len(images)]
                mat = create_photo_material(img, template_vid, duration_us)
                data["materials"]["videos"].append(mat)
                
                import copy
                new_seg = copy.deepcopy(template_seg) if template_seg else {
                    "id": generate_uuid(),
                    "speed": 1.0,
                    "volume": 1.0,
                    "clip": {"scale": {"x":1.0, "y":1.0}, "rotation": 0.0, "transform": {"x":0.0, "y":0.0}, "flip": {"vertical": False, "horizontal": False}, "alpha": 1.0},
                    "extra_material_refs": []
                }
                new_seg["id"] = generate_uuid()
                new_seg["material_id"] = mat["id"]
                new_seg["source_timerange"] = {"start": 0, "duration": duration_us}
                new_seg["target_timerange"] = {"start": current_time_us, "duration": duration_us}
                
                # Áp dụng Ken Burns Zoom & Pan ngẫu nhiên
                apply_ken_burns_to_segment(new_seg, duration_us, data)
                
                new_segments.append(new_seg)
                current_time_us += duration_us
                
            # Add to tracks
            if insert_mode == "new_track":
                new_track = {
                    "id": generate_uuid(),
                    "type": "video",
                    "segments": new_segments
                }
                # Thêm track mới lên trên cùng
                if "tracks" not in data:
                    data["tracks"] = []
                data["tracks"].insert(0, new_track)
            else:
                # Tìm main track
                main_track = None
                if "tracks" not in data:
                    data["tracks"] = []
                for track in data.get("tracks", []):
                    if track.get("type") == "video":
                        main_track = track
                        break
                if main_track:
                    last_time = 0
                    for s in main_track.get("segments", []):
                        tr = s.get("target_timerange", {})
                        if tr.get("start", 0) + tr.get("duration", 0) > last_time:
                            last_time = tr.get("start", 0) + tr.get("duration", 0)
                    
                    for s in new_segments:
                        # Dịch chuyển start_time
                        s["target_timerange"]["start"] += last_time
                        main_track["segments"].append(s)
                else:
                    new_track = {
                        "id": generate_uuid(),
                        "type": "video",
                        "segments": new_segments
                    }
                    data["tracks"].insert(0, new_track)
                    
            # Cập nhật tổng thời lượng project
            max_duration = 0
            for track in data.get("tracks", []):
                for s in track.get("segments", []):
                    tr = s.get("target_timerange", {})
                    end_time = tr.get("start", 0) + tr.get("duration", 0)
                    if end_time > max_duration:
                        max_duration = end_time
            data["duration"] = max_duration
                        
            # Ghi đè lại
            with open(current_json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            
        return True, f"Thành công! Đã thêm {len(new_segments)} ảnh vào Timeline cùng hiệu ứng Zoom & Pan Ken Burns ngẫu nhiên. (File backup đã tạo: .bak)"
    except Exception as e:
        import traceback
        return False, f"Lỗi xử lý JSON: {str(e)}\n{traceback.format_exc()}"

def sync_existing_segments_to_srt(draft_json_path, srt_path):
    """
    Quét Track Video chính đã có hình ảnh, tự động co giãn duration của chúng theo SRT.
    Nếu thiếu ảnh, tự copy ảnh lặp lại.
    Tự động áp dụng hiệu ứng Zoom 5-10% & Pan ngẫu nhiên cho mỗi bức ảnh.
    """
    try:
        project_dir = os.path.dirname(draft_json_path)
        
        # Xoá các file cache/restore của CapCut để tránh bị rollback
        import glob
        for tmp_file in glob.glob(os.path.join(project_dir, "*.tmp")):
            try: os.remove(tmp_file)
            except: pass
        for tmp_file in glob.glob(os.path.join(project_dir, "**", "*.tmp"), recursive=True):
            try: os.remove(tmp_file)
            except: pass
            
        try: os.remove(os.path.join(project_dir, ".locked"))
        except: pass
        try: os.remove(os.path.join(project_dir, "draft_virtual_store.json"))
        except: pass
        
        json_files = []
        for root, dirs, files in os.walk(project_dir):
            if "draft_content.json" in files:
                json_files.append(os.path.join(root, "draft_content.json"))
                
        subs = pysrt.open(srt_path)
        if not subs:
            return False, "File SRT trống hoặc không hợp lệ."

        new_segments_len = 0
        for current_json_path in json_files:
            backup_draft(current_json_path)
            
            with open(current_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Tìm Main Track
            main_track = None
            for track in data.get("tracks", []):
                if track.get("type") == "video":
                    main_track = track
                    break
                    
            if not main_track:
                continue

            existing_segments = main_track.get("segments", [])
            if not existing_segments:
                continue # Nếu track trống thì bỏ qua JSON này
                
            if "keyframes" not in data or not isinstance(data["keyframes"], dict):
                data["keyframes"] = {
                    "videos": [], "audios": [], "texts": [], "stickers": [],
                    "filters": [], "adjusts": [], "handwrites": [], "effects": []
                }
            if "videos" not in data["keyframes"]:
                data["keyframes"]["videos"] = []
            else:
                data["keyframes"]["videos"] = []
                
            new_segments = []
            current_time_us = 0
        
            for i, sub in enumerate(subs):
                start_us = int((sub.start.ordinal / 1000.0) * 1000000)
                end_us = int((sub.end.ordinal / 1000.0) * 1000000)
                duration_us = end_us - start_us
                
                if duration_us <= 0:
                    continue
                    
                # Xử lý gap (Khoảng nghỉ giữa các câu)
                if start_us > current_time_us:
                    gap_duration = start_us - current_time_us
                    # Copy ảnh trước đó để lấp gap
                    import copy
                    gap_seg = copy.deepcopy(existing_segments[(i - 1) % len(existing_segments)] if i > 0 else existing_segments[0])
                    gap_seg["id"] = generate_uuid()
                    gap_seg["source_timerange"] = {"start": 0, "duration": gap_duration}
                    gap_seg["target_timerange"] = {"start": current_time_us, "duration": gap_duration}
                    
                    # Cập nhật duration của material cho gap
                    mat_id_gap = gap_seg.get("material_id")
                    for vid in data.get("materials", {}).get("videos", []):
                        if vid.get("id") == mat_id_gap:
                            if vid.get("duration", 0) < gap_duration:
                                vid["duration"] = gap_duration
                            break
                            
                    # Áp dụng Ken Burns Zoom & Pan ngẫu nhiên
                    apply_ken_burns_to_segment(gap_seg, gap_duration, data)
                    
                    new_segments.append(gap_seg)
                    current_time_us += gap_duration
                    
                # Copy/Sửa segment chính
                import copy
                seg = copy.deepcopy(existing_segments[i % len(existing_segments)])
                seg["id"] = generate_uuid() if i >= len(existing_segments) else seg.get("id", generate_uuid()) # Tạo ID mới nếu là bản copy
                seg["source_timerange"] = {"start": 0, "duration": duration_us}
                seg["target_timerange"] = {"start": current_time_us, "duration": duration_us}
                
                # Cập nhật duration của material
                mat_id = seg.get("material_id")
                for vid in data.get("materials", {}).get("videos", []):
                    if vid.get("id") == mat_id:
                        # Material duration phải bao phủ toàn bộ source_timerange
                        if vid.get("duration", 0) < duration_us:
                            vid["duration"] = duration_us
                        break
                        
                # Áp dụng Ken Burns Zoom & Pan ngẫu nhiên
                apply_ken_burns_to_segment(seg, duration_us, data)
                
                new_segments.append(seg)
                current_time_us += duration_us
                
            main_track["segments"] = new_segments
            new_segments_len = len(new_segments)
            
            # Cập nhật tổng thời lượng project
            max_duration = 0
            for track in data.get("tracks", []):
                for s in track.get("segments", []):
                    tr = s.get("target_timerange", {})
                    end_time = tr.get("start", 0) + tr.get("duration", 0)
                    if end_time > max_duration:
                        max_duration = end_time
            data["duration"] = max_duration
            
            # Ghi đè lại
            with open(current_json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
                
        if new_segments_len == 0:
            return False, "Track Video đang trống. Vui lòng thả ít nhất 1 hình ảnh vào CapCut trước!"
            
        return True, f"Thành công! Đã đồng bộ xong {new_segments_len} phân đoạn ảnh với hiệu ứng Zoom & Pan Ken Burns ngẫu nhiên. (File backup đã tạo: .bak)"
    except Exception as e:
        import traceback
        return False, f"Lỗi xử lý JSON: {str(e)}\n{traceback.format_exc()}"


def split_capcut_project_into_chunks(draft_json_path: str, chunk_minutes: float = 14.0, split_all_tracks: bool = True) -> tuple:
    """
    Can thiệp trực tiếp vào Project CapCut (Timeline Draft):
    Tự động cắt nhỏ bất kỳ video/audio dài nào trên Timeline CapCut thành các đoạn 14 phút (<= 14m).
    Giúp người dùng ngay lập tức click chuột phải chọn 'Tách giọng nói' (Bỏ lời / Giữ lời)
    trực tiếp trong CapCut mà không bị dính giới hạn 15 phút.
    """
    import copy
    import glob
    try:
        project_dir = os.path.dirname(draft_json_path)

        # 1. Dọn dẹp cache/lock của CapCut để CapCut load file JSON mới nhất
        for tmp_file in glob.glob(os.path.join(project_dir, "*.tmp")):
            try: os.remove(tmp_file)
            except: pass
        for tmp_file in glob.glob(os.path.join(project_dir, "**", "*.tmp"), recursive=True):
            try: os.remove(tmp_file)
            except: pass
            
        try: os.remove(os.path.join(project_dir, ".locked"))
        except: pass
        try: os.remove(os.path.join(project_dir, "draft_virtual_store.json"))
        except: pass

        json_files = []
        for root, dirs, files in os.walk(project_dir):
            if "draft_content.json" in files:
                json_files.append(os.path.join(root, "draft_content.json"))

        if not json_files:
            return False, "Không tìm thấy file draft_content.json trong project CapCut."

        chunk_us = int(chunk_minutes * 60 * 1000000)
        total_segments_before = 0
        total_segments_after = 0
        total_cuts_made = 0

        for current_json_path in json_files:
            backup_draft(current_json_path)

            with open(current_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for track in data.get("tracks", []):
                t_type = track.get("type")
                if not split_all_tracks and t_type != "video":
                    continue

                old_segments = track.get("segments", [])
                total_segments_before += len(old_segments)
                new_segments = []

                for seg in old_segments:
                    src_timerange = seg.get("source_timerange", {})
                    tgt_timerange = seg.get("target_timerange", {})

                    src_start = src_timerange.get("start", 0)
                    src_dur = src_timerange.get("duration", 0)
                    tgt_start = tgt_timerange.get("start", 0)
                    tgt_dur = tgt_timerange.get("duration", 0)

                    speed = seg.get("speed", 1.0)
                    if speed <= 0:
                        speed = 1.0

                    if src_dur > chunk_us:
                        # Cắt segment này thành các phần nhỏ <= chunk_us
                        curr_src = src_start
                        curr_tgt = tgt_start
                        remaining_src = src_dur

                        cut_parts = 0
                        while remaining_src > 0:
                            slice_src_dur = min(chunk_us, remaining_src)
                            slice_tgt_dur = int(slice_src_dur / speed)

                            new_seg = copy.deepcopy(seg)
                            new_seg["id"] = generate_uuid()
                            new_seg["source_timerange"] = {"start": curr_src, "duration": slice_src_dur}
                            new_seg["target_timerange"] = {"start": curr_tgt, "duration": slice_tgt_dur}

                            new_segments.append(new_seg)

                            curr_src += slice_src_dur
                            curr_tgt += slice_tgt_dur
                            remaining_src -= slice_src_dur
                            cut_parts += 1

                        total_cuts_made += (cut_parts - 1)
                    else:
                        new_segments.append(seg)

                track["segments"] = new_segments
                total_segments_after += len(new_segments)

            # Cập nhật tổng thời lượng project
            max_duration = 0
            for track in data.get("tracks", []):
                for s in track.get("segments", []):
                    tr = s.get("target_timerange", {})
                    end_time = tr.get("start", 0) + tr.get("duration", 0)
                    if end_time > max_duration:
                        max_duration = end_time
            data["duration"] = max_duration

            # Ghi đè lại JSON
            with open(current_json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)

        if total_cuts_made == 0:
            return True, f"Tất cả các đoạn video trên Timeline CapCut đã sẵn sàng và đều nhỏ hơn {chunk_minutes} phút (Tổng {total_segments_after} đoạn)!"

        return True, f"🎉 Thành công! Đã tự động chia Timeline CapCut thành {total_segments_after} đoạn (mỗi đoạn tối đa {chunk_minutes} phút). Bạn hãy mở CapCut lên để xem thành quả nhé!"

    except Exception as e:
        import traceback
        return False, f"Lỗi xử lý Project CapCut: {str(e)}\n{traceback.format_exc()}"


def inject_broll_sequence_and_audio_to_draft(
    draft_json_path: str,
    video_clips_list: list,  # list of dicts: [{'path': ..., 'duration_us': ...}]
    audio_path: str
) -> tuple:
    """
    Bơm toàn bộ chuỗi Video B-Roll (cắt ngắn 3-5s) và Track Voiceover vào Timeline Dự án CapCut.
    """
    import glob
    import copy
    try:
        project_dir = os.path.dirname(draft_json_path)

        # Dọn dẹp cache
        for tmp_file in glob.glob(os.path.join(project_dir, "*.tmp")):
            try: os.remove(tmp_file)
            except: pass
        for tmp_file in glob.glob(os.path.join(project_dir, "**", "*.tmp"), recursive=True):
            try: os.remove(tmp_file)
            except: pass
        try: os.remove(os.path.join(project_dir, ".locked"))
        except: pass
        try: os.remove(os.path.join(project_dir, "draft_virtual_store.json"))
        except: pass

        json_files = []
        for root, dirs, files in os.walk(project_dir):
            if "draft_content.json" in files:
                json_files.append(os.path.join(root, "draft_content.json"))

        if not json_files:
            return False, "Không tìm thấy file draft_content.json."

        total_broll_us = sum(c["duration_us"] for c in video_clips_list)

        for c_json in json_files:
            backup_draft(c_json)

            with open(c_json, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "materials" not in data:
                data["materials"] = {}
            if "videos" not in data["materials"]:
                data["materials"]["videos"] = []
            if "audios" not in data["materials"]:
                data["materials"]["audios"] = []

            # 1. Tạo video materials & video segments
            video_segments = []
            curr_time_us = 0

            for idx, clip in enumerate(video_clips_list):
                v_mat_id = generate_uuid()
                c_path = os.path.abspath(clip["path"])
                c_dur_us = clip["duration_us"]

                v_mat = {
                    "id": v_mat_id,
                    "type": "video",
                    "path": c_path,
                    "duration": c_dur_us,
                    "material_name": os.path.basename(c_path),
                    "width": 1920,
                    "height": 1080,
                    "crop_scale": 1.0,
                    "crop_ratio": "free",
                    "extra_type_option": 0
                }
                data["materials"]["videos"].append(v_mat)

                v_seg = {
                    "id": generate_uuid(),
                    "material_id": v_mat_id,
                    "source_timerange": {"start": 0, "duration": c_dur_us},
                    "target_timerange": {"start": curr_time_us, "duration": c_dur_us},
                    "speed": 1.0,
                    "volume": 0.0,  # Tắt tiếng B-roll để ưu tiên voice
                    "clip": {"scale": {"x":1.0, "y":1.0}, "rotation": 0.0, "transform": {"x":0.0, "y":0.0}, "flip": {"vertical": False, "horizontal": False}, "alpha": 1.0},
                    "extra_material_refs": []
                }
                video_segments.append(v_seg)
                curr_time_us += c_dur_us

            # 2. Tạo audio material & audio segment cho Voice
            a_mat_id = generate_uuid()
            abs_audio = os.path.abspath(audio_path)
            a_mat = {
                "id": a_mat_id,
                "type": "extract_music",
                "path": abs_audio,
                "duration": total_broll_us,
                "name": os.path.basename(abs_audio),
                "category_name": "",
                "category_id": "",
                "extra_info": "",
                "effect_id": "",
                "source_platform": 0
            }
            data["materials"]["audios"].append(a_mat)

            audio_seg = {
                "id": generate_uuid(),
                "material_id": a_mat_id,
                "source_timerange": {"start": 0, "duration": total_broll_us},
                "target_timerange": {"start": 0, "duration": total_broll_us},
                "volume": 1.0,
                "speed": 1.0,
                "clip": None,
                "extra_material_refs": [],
                "visible": True,
                "desc": "Voiceover"
            }

            # 3. Tạo 2 track: Track 0 là Video B-Roll, Track 1 là Audio Voice
            broll_track = {
                "id": generate_uuid(),
                "type": "video",
                "segments": video_segments
            }
            voice_track = {
                "id": generate_uuid(),
                "type": "audio",
                "segments": [audio_seg]
            }

            if "tracks" not in data:
                data["tracks"] = []
            data["tracks"].insert(0, broll_track)
            data["tracks"].append(voice_track)

            data["duration"] = total_broll_us

            with open(c_json, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)

        return True, f"🎉 Đã bơm thành công {len(video_clips_list)} cảnh Video B-Roll + Track Voiceover vào CapCut Timeline!"

    except Exception as e:
        import traceback
        return False, f"Lỗi inject B-Roll vào CapCut: {str(e)}\n{traceback.format_exc()}"


def add_separated_audio_to_draft(draft_json_path: str, audio_path: str, mute_original_video: bool = True) -> tuple:
    """
    Chèn track âm thanh đã tách lời vào Dự Án CapCut và tùy chọn tắt tiếng track video gốc.
    """
    try:
        if not os.path.exists(draft_json_path):
            return False, f"Không tìm thấy file dự án: {draft_json_path}"
        if not os.path.exists(audio_path):
            return False, f"Không tìm thấy file âm thanh: {audio_path}"

        import subprocess
        ffprobe = shutil.which('ffprobe') or '/usr/local/bin/ffprobe'
        cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
        audio_dur_s = float(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip())
        audio_dur_us = int(audio_dur_s * 1000000)

        c_json = draft_json_path if draft_json_path.endswith("draft_content.json") else os.path.join(os.path.dirname(draft_json_path), "draft_content.json")
        backup_draft(c_json)

        with open(c_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 1. Thêm audio material
        a_mat_id = generate_uuid()
        a_mat = {
            "id": a_mat_id,
            "type": "extract_music",
            "path": os.path.abspath(audio_path),
            "name": os.path.basename(audio_path),
            "duration": audio_dur_us,
            "music_id": "",
            "category_name": "",
            "category_id": "",
            "extra_info": "",
            "effect_id": "",
            "source_platform": 0
        }
        if "materials" not in data:
            data["materials"] = {}
        if "audios" not in data["materials"]:
            data["materials"]["audios"] = []
        data["materials"]["audios"].append(a_mat)

        # 2. Tắt tiếng track video gốc nếu được yêu cầu
        if mute_original_video:
            for track in data.get("tracks", []):
                if track.get("type") == "video":
                    for seg in track.get("segments", []):
                        seg["volume"] = 0.0

        # 3. Tạo audio segment và track mới
        audio_seg = {
            "id": generate_uuid(),
            "material_id": a_mat_id,
            "source_timerange": {"start": 0, "duration": audio_dur_us},
            "target_timerange": {"start": 0, "duration": audio_dur_us},
            "volume": 1.0,
            "speed": 1.0,
            "clip": None,
            "extra_material_refs": [],
            "visible": True,
            "desc": "Separated Instrumental / BGM"
        }

        audio_track = {
            "id": generate_uuid(),
            "type": "audio",
            "segments": [audio_seg]
        }

        if "tracks" not in data:
            data["tracks"] = []
        data["tracks"].append(audio_track)

        with open(c_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        return True, "🎉 Đã chèn thành công track âm thanh đã tách lời vào CapCut Timeline!"
    except Exception as e:
        return False, f"Lỗi chèn âm thanh vào CapCut: {str(e)}"


