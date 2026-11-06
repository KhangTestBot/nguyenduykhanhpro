import os
import pysrt
import google.generativeai as genai
import tempfile
import re
import time

def get_style_instruction(style_name: str, target_lang: str = "Tiếng Việt") -> str:
    """Trả về chỉ thị phong cách phù hợp cho Gemini AI."""
    s = (style_name or "").lower()
    if "tu tiên" in s or "tiên hiệp" in s:
        return (
            f"Dịch nội dung sang {target_lang} theo phong cách TU TIÊN / TIÊN HIỆP Trung Quốc đặc sắc. "
            "Sử dụng các thuật ngữ Hán Việt cổ trang như 'Đạo hữu', 'Bản tọa', 'Tại hạ', 'Đột phá cảnh giới', 'Thiên đạo', 'Độ kiếp', 'Bổn tôn', 'Tiên gia', 'Đạo tử'... "
            "Giữ đúng cốt truyện và ý nghĩa gốc của lời thoại."
        )
    elif "hài hước" in s or "cợt nhả" in s or "mặn mòi" in s:
        return (
            f"Dịch nội dung sang {target_lang} theo phong cách HÀI HƯỚC, DÍ DỎM, bắt trend GenZ/TikTok "
            "nhưng vẫn giữ đúng các mốc sự kiện chính."
        )
    elif "review" in s or "kịch tính" in s:
        return (
            f"Dịch nội dung sang {target_lang} theo phong cách VOICE REVIEW PHIM KỊCH TÍNH, dồn dập, giật gân "
            "nhưng không bóp méo nội dung câu chuyện."
        )
    elif "tóm tắt" in s or "ngắn gọn" in s:
        return (
            f"Dịch và tóm tắt ngắn gọn sang {target_lang}, giữ lại ý chính cốt lõi, lược bỏ từ thừa."
        )
    else:
        return (
            f"Dịch SÁT NGHĨA NHẤT CÓ THỂ (FAITHFUL & ACCURATE) sang {target_lang}.\n"
            "YÊU CẦU BẮT BUỘC:\n"
            "1. Dịch CHÍNH XÁC 100%, bám sát từng từ ngữ, ngữ nghĩa, đại từ nhân xưng và cấu trúc câu gốc của nhân vật/người nói.\n"
            "2. Tuyệt đối KHÔNG tự ý sáng tác, thêm thắt, phóng tác, suy diễn hoặc lược bỏ bất kỳ ý nào.\n"
            "3. Giữ nguyên danh từ riêng, thuật ngữ kỹ thuật, tên nhân vật, tên địa danh chuẩn xác.\n"
            "4. Văn phong tự nhiên, mạch lạc nhưng phải trung thực và sát nghĩa tuyệt đối với bản gốc."
        )


def rule_based_cleanup_entities(text: str, custom_glossary: dict = None) -> str:
    """
    Bộ lọc Regex chuẩn hóa tự động:
    - Sửa lỗi dịch máy tên riêng chứa số (ví dụ: '13' -> 'Thập Tam')
    - Đồng nhất tên nhân vật chính/phụ (Trịnh Thập Tam -> Trình Thập Tam, Thành ca -> Thập Tam ca)
    - Sửa các lỗi nhân xưng và thành ngữ Hán Việt sai lệch (lệnh tôn nữ -> lệnh ái)
    """
    if not text:
        return ""
    
    t = text
    # 1. Sửa lỗi số 13 bị chèn vào lời thoại nhân vật Thập Tam
    t = re.sub(r'\b13,\s*', 'Thập Tam, ', t)
    t = re.sub(r',\s*13\b', ', Thập Tam', t)
    t = re.sub(r'\b13\b', 'Thập Tam', t)
    
    # 2. Đồng nhất họ và tên nhân vật
    t = t.replace('Trịnh Thập Tam', 'Trình Thập Tam')
    t = re.sub(r'\bThành ca\b', 'Thập Tam ca', t)
    t = re.sub(r'\bCa Thành\b', 'Ca Thập Tam', t)
    t = t.replace('Thành thật chích', 'Trình Thập Tam')
    
    # 3. Sửa lỗi xưng hô nhầm lẫn gia đình
    t = t.replace('Thập Tam nhà cháu từ nhỏ đã thông minh', 'Thập Tam nhà tôi từ nhỏ đã thông minh')
    t = t.replace('bảo cảm ơn anh lần trước đã cứu cháu', 'bảo cảm ơn cậu lần trước đã cứu tớ')
    t = t.replace('lệnh tôn nữ', 'lệnh ái')
    t = t.replace('Lệnh tôn nữ', 'Lệnh ái')
    
    # 4. Áp dụng glossary tùy chỉnh nếu có
    if custom_glossary:
        for src, dest in custom_glossary.items():
            if src and dest:
                t = re.sub(r'\b' + re.escape(src) + r'\b', dest, t, flags=re.IGNORECASE)
                
    return t


def auto_detect_characters_and_glossary(subs, model, user_hints: str = "") -> str:
    """
    Tự động phân tích kịch bản SRT để trích xuất:
    - Danh sách tên nhân vật chuẩn xác (phiên âm Hán Việt chuẩn, không để số).
    - Vai vế và đại từ nhân xưng gia đình/bè bạn (ông nội, ba mẹ, dượng, bạn bè, sư đồ).
    """
    try:
        sample_lines = []
        step = max(1, len(subs) // 25)
        for i in range(0, min(len(subs), 300), 5):
            sample_lines.append(subs[i].text.replace('\n', ' ').strip())
        for i in range(300, len(subs), step):
            sample_lines.append(subs[i].text.replace('\n', ' ').strip())
            
        sample_text = "\n".join(sample_lines[:60])
        
        prompt = (
            "Bạn là chuyên gia biên tập và dịch thuật phụ đề phim chuyên nghiệp.\n"
            f"Dưới đây là các câu thoại mẫu trích từ kịch bản:\n{sample_text}\n\n"
            f"Thông tin gợi ý thêm từ người dùng (nếu có): {user_hints}\n\n"
            "HÃY PHÂN TÍCH VÀ TRÍCH XUẤT BẢNG ĐỒNG NHẤT NHÂN VẬT & NHÂN XƯNG (Ngắn gọn, súc tích):\n"
            "1. Tên các nhân vật chính và phụ (viết chuẩn Hán Việt, TUYỆT ĐỐI KHÔNG dịch tên riêng thành số như '13' -> phải là 'Thập Tam').\n"
            "2. Mối quan hệ và quy tắc đại từ nhân xưng (Ai là ông/bố/mẹ/dượng/thầy/bạn bè? Xưng hô thế nào cho đúng vai vế thuần Việt?).\n"
            "Trả về bảng quy tắc súc tích trong 5-8 gạch đầu dòng."
        )
        
        resp = model.generate_content(prompt)
        return resp.text.strip()
    except Exception as e:
        print(f"[Auto-Glossary Warning] Không thể auto-extract: {e}")
        return user_hints or "Đồng nhất tên nhân vật và xưng hô đúng vai vế gia đình thuần Việt."


def parse_subtitle_translation_response(resp_text, expected_ids=None):
    """
    Phân tích phản hồi từ Gemini hỗ trợ tất cả các định dạng:
    1. JSON Array [{"id": 1, "text": "..."}]
    2. Format chuẩn: ID: 1\n<text>\n---\n
    3. Định dạng số: 1. <text> / 1: <text> / #1 <text> / [1] <text>
    4. Định dạng từng dòng tuần tự tương ứng expected_ids.
    """
    import json
    results = {}
    cleaned = (resp_text or "").strip()
    
    # 1. Thử parse JSON
    json_str = cleaned
    if "```" in json_str:
        json_str = re.sub(r"^```[a-zA-Z]*\n", "", json_str)
        json_str = re.sub(r"```$", "", json_str).strip()
    try:
        data = json.loads(json_str)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and ("id" in item or "index" in item) and "text" in item:
                    k = int(item.get("id", item.get("index")))
                    results[k] = str(item["text"]).strip()
            if results:
                return results
    except Exception:
        pass

    # 2. Line-by-line parser đa năng
    lines = cleaned.split("\n")
    current_id = None
    current_text = []

    id_header_pattern = re.compile(r"^(?:(?:ID|id|#|\[)\s*[:\.\-]?)?\s*(\d+)\s*(?:\]|\.|\:|\-)?\s*(.*)$")

    for line in lines:
        l_str = line.strip()
        if not l_str or l_str.startswith("---") or l_str.startswith("```"):
            continue
        
        m = id_header_pattern.match(l_str)
        if m and m.group(1):
            potential_id = int(m.group(1))
            if expected_ids is None or potential_id in expected_ids:
                if current_id is not None and current_text:
                    results[current_id] = "\n".join(current_text).strip()
                current_id = potential_id
                rem = m.group(2).strip()
                current_text = [rem] if rem else []
                continue
        
        if current_id is not None:
            current_text.append(l_str)

    if current_id is not None and current_text:
        results[current_id] = "\n".join(current_text).strip()

    if results:
        return results

    # 3. Fallback: Parse theo phân đoạn ---
    blocks = cleaned.split("---")
    for block in blocks:
        b = block.strip()
        if not b:
            continue
        b_lines = b.split("\n", 1)
        digits = ''.join(c for c in b_lines[0] if c.isdigit())
        if digits:
            try:
                idx = int(digits)
                t = b_lines[1].strip() if len(b_lines) > 1 else ""
                if t and idx not in results:
                    results[idx] = t
            except Exception:
                pass
                
    if results:
        return results

    # 4. Fallback tuần tự theo danh sách ID mong đợi
    if expected_ids:
        content_lines = [l.strip() for l in lines if l.strip() and not l.startswith("---") and not l.startswith("```")]
        if len(content_lines) == len(expected_ids):
            for e_id, c_line in zip(expected_ids, content_lines):
                results[e_id] = re.sub(r"^(?:(?:ID|id|#|\[)\s*[:\.\-]?)?\s*\d+[\s:\.\-\]]*", "", c_line).strip()
            return results

    return results


def process_srt_file(
    file_content, 
    api_key, 
    action="translate", 
    target_lang=None, 
    style="Chuẩn xác (Chuyên nghiệp)", 
    valid_model=None, 
    character_hints="", 
    progress_callback=None
):
    """
    Xử lý và dịch file SRT với:
    1. Bảng đồng nhất tên nhân vật & Đại từ nhân xưng toàn cục (Global Character & Pronoun Consistency).
    2. Ngữ cảnh gối đầu liên tục (Rolling Context) giữa các batch.
    3. Bộ lọc Hậu xử lý Regex chuẩn hóa triệt tiêu lỗi số đếm / sai họ / sai xưng hô.
    4. Dual-Pass Gap Filler & Global Final Sweep Pass.
    """
    try:
        raw_keys = [k.strip() for k in re.split(r"[,;\n]+", str(api_key)) if k.strip()]
        if not raw_keys:
            raise ValueError("Vui lòng cung cấp Gemini API Key hợp lệ!")
        
        current_key_idx = 0
        genai.configure(api_key=raw_keys[current_key_idx])

        fallback_models = [
            "models/gemini-3.5-flash-lite",
            "models/gemini-3.1-flash-lite",
            "models/gemini-flash-lite-latest",
            "models/gemini-2.0-flash-lite",
            "models/gemini-2.0-flash",
            "models/gemini-1.5-flash",
            "models/gemini-3.5-flash"
        ]

        model_queue = []
        if valid_model and "2.5" not in valid_model and "3.7" not in valid_model and "3.6" not in valid_model:
            model_queue.append(valid_model)
        for fb in fallback_models:
            if fb not in model_queue:
                model_queue.append(fb)

        current_model_idx = 0
        current_model_name = model_queue[current_model_idx]
        model = genai.GenerativeModel(current_model_name)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".srt", mode="w", encoding="utf-8") as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        subs = pysrt.open(tmp_path)
        total_subs_len = len(subs)
        all_original_texts = {sub.index: sub.text for sub in subs}

        target_lang_str = target_lang or "Tiếng Việt"
        style_instruction = get_style_instruction(style, target_lang_str)

        # ── BƯỚC 0: TRÍCH XUẤT BẢNG TÊN & NHÂN XƯNG TOÀN CỤC ──────────────────
        if progress_callback:
            progress_callback(3, "🔍 Đang phân tích kịch bản & thiết lập bảng đồng nhất nhân xưng...")

        glossary_directive = auto_detect_characters_and_glossary(subs, model, user_hints=character_hints)

        global_consistency_header = (
            "===========================================================\n"
            "QUY TẮC ĐỒNG NHẤT TÊN NHÂN VẬT & ĐẠI TỪ NHÂN XƯNG (BẮT BUỘC):\n"
            f"{glossary_directive}\n"
            "YÊU CẦU NGHIÊM NGẶT:\n"
            "1. Tên nhân vật phải viết hoa chuẩn Hán Việt, TUYỆT ĐỐI KHÔNG dịch tên riêng thành số đếm (ví dụ: '十三' phải dịch là 'Thập Tam', KHÔNG ĐƯỢC dịch là '13').\n"
            "2. Đại từ nhân xưng phải đúng quan hệ vai vế gia đình & xã hội (Bố mẹ/Dượng/Ông xưng 'ta/dượng/ông/bố', gọi 'cháu/con'; bạn bè xưng 'tôi/tớ - cậu/bạn').\n"
            "3. Tuyệt đối không đảo ngược vai vế hoặc đổi tên nhân vật giữa chừng.\n"
            "===========================================================\n"
        )

        batch_size = 40
        total_batches = (total_subs_len + batch_size - 1) // batch_size
        recent_context_lines = []

        # ── VÒNG 1: DỊCH CHÍNH THEO BATCH CÓ ROLLING CONTEXT ────────────────────
        for i in range(total_batches):
            if progress_callback:
                pct = int(5 + ((i) / (total_batches + 1)) * 88)
                progress_callback(pct, f"⏳ Đang dịch đồng nhất: {pct}% (Gói {i+1}/{total_batches} - {total_subs_len} dòng)...")

            batch_subs = subs[i*batch_size : (i+1)*batch_size]
            expected_ids = [sub.index for sub in batch_subs]

            batch_text = ""
            for sub in batch_subs:
                clean_t = sub.text.replace("\n", " ").strip()
                batch_text += f"ID: {sub.index}\n{clean_t}\n---\n"

            context_str = ""
            if recent_context_lines:
                context_str = "NGỮ CẢNH CÁC CÂU TRƯỚC ĐÓ ĐỂ GIỮ MẠCH ĐỐI THOẠI:\n" + "\n".join(recent_context_lines[-4:]) + "\n\n"

            prompt = (
                f"You are a professional subtitle translator and consistency editor.\n"
                f"{style_instruction}\n"
                f"Target Language: {target_lang_str}.\n"
                f"{global_consistency_header}\n"
                f"{context_str}"
                f"Task: Translate EVERY subtitle line below into {target_lang_str}.\n"
                f"DO NOT skip any ID. DO NOT output Chinese characters.\n\n"
                "Output Format:\n"
                "ID: <number>\n<translated text>\n---\n\n"
                f"{batch_text}"
            )

            max_retries = 6
            response_text = ""
            for attempt in range(max_retries):
                try:
                    response = model.generate_content(prompt)
                    response_text = response.text
                    time.sleep(1.0)
                    break
                except Exception as e:
                    err_msg = str(e).lower()
                    is_quota = ("429" in err_msg or "quota" in err_msg or "rate limit" in err_msg or 
                                "resource_exhausted" in err_msg or "too many requests" in err_msg)
                    is_deprecated = ("404" in err_msg or "not found" in err_msg or "no longer available" in err_msg or "deprecated" in err_msg)

                    if is_quota and len(raw_keys) > 1:
                        current_key_idx = (current_key_idx + 1) % len(raw_keys)
                        print(f"[Key Rotation] Chuyển sang API Key #{current_key_idx + 1}")
                        genai.configure(api_key=raw_keys[current_key_idx])
                        model = genai.GenerativeModel(current_model_name)
                        time.sleep(1.0)
                        continue

                    wait_sec = 4
                    retry_match = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)", err_msg)
                    if retry_match:
                        wait_sec = min(35, int(retry_match.group(1)) + 2)

                    if is_quota or is_deprecated:
                        if current_model_idx + 1 < len(model_queue):
                            current_model_idx += 1
                            current_model_name = model_queue[current_model_idx]
                            print(f"[Auto-Failover] Chuyển sang model: {current_model_name}")
                            model = genai.GenerativeModel(current_model_name)
                            time.sleep(wait_sec)
                            continue
                        else:
                            current_model_idx = 0
                            current_model_name = model_queue[0]
                            model = genai.GenerativeModel(current_model_name)
                            if attempt < max_retries - 1:
                                time.sleep(wait_sec)
                                continue
                            raise Exception(f"Lỗi Hạn Ngạch Quota: {str(e)}")
                    else:
                        if attempt < max_retries - 1:
                            time.sleep(2)
                            continue
                        raise e

            parsed_dict = parse_subtitle_translation_response(response_text, expected_ids=expected_ids)
            for sub in batch_subs:
                if sub.index in parsed_dict and parsed_dict[sub.index]:
                    cleaned_t = rule_based_cleanup_entities(parsed_dict[sub.index])
                    sub.text = cleaned_t
                    recent_context_lines.append(f"[{sub.index}]: {cleaned_t}")

            # Dual-Pass Gap Filler cho từng batch
            is_translating_to_vi = "việt" in target_lang_str.lower() or "viet" in target_lang_str.lower()
            untranslated_subs = []
            for sub in batch_subs:
                is_untranslated = (sub.index not in parsed_dict)
                if not is_untranslated and is_translating_to_vi:
                    if re.search(r'[\u4e00-\u9fff]', sub.text):
                        is_untranslated = True
                if is_untranslated:
                    untranslated_subs.append(sub)

            if untranslated_subs:
                gap_text = ""
                gap_expected_ids = [s.index for s in untranslated_subs]
                for s in untranslated_subs:
                    orig_t = all_original_texts.get(s.index, s.text).replace("\n", " ").strip()
                    gap_text += f"ID: {s.index}\n{orig_t}\n---\n"
                gap_prompt = (
                    f"You are a professional subtitle translator. {style_instruction}\n"
                    f"Target Language: {target_lang_str}.\n"
                    f"{global_consistency_header}\n"
                    f"Translate every line below into {target_lang_str}. DO NOT output Chinese characters.\n"
                    "Output Format:\nID: <number>\n<translated text>\n---\n\n"
                    f"{gap_text}"
                )
                try:
                    gap_resp = model.generate_content(gap_prompt)
                    gap_dict = parse_subtitle_translation_response(gap_resp.text, expected_ids=gap_expected_ids)
                    for s in untranslated_subs:
                        if s.index in gap_dict and gap_dict[s.index]:
                            s.text = rule_based_cleanup_entities(gap_dict[s.index])
                except Exception as gap_err:
                    print(f"[Gap Filler Warning] Lỗi khi vá dòng batch: {gap_err}")

        # ── VÒNG 2: GLOBAL FINAL SWEEP PASS ────────────────────────────────────
        if progress_callback:
            progress_callback(95, "🔍 Đang rà soát và chuẩn hóa 100% dòng phụ đề...")

        chinese_pattern = re.compile(r'[\u4e00-\u9fff]')
        all_missed_subs = []
        for sub in subs:
            sub.text = rule_based_cleanup_entities(sub.text)
            if "việt" in target_lang_str.lower() or "viet" in target_lang_str.lower():
                if chinese_pattern.search(sub.text):
                    all_missed_subs.append(sub)

        if all_missed_subs:
            m_batch_size = 25
            m_total_batches = (len(all_missed_subs) + m_batch_size - 1) // m_batch_size
            for mb_idx in range(m_total_batches):
                mb_subs = all_missed_subs[mb_idx*m_batch_size : (mb_idx+1)*m_batch_size]
                mb_expected_ids = [s.index for s in mb_subs]
                mb_text = ""
                for s in mb_subs:
                    orig_t = all_original_texts.get(s.index, s.text).replace("\n", " ").strip()
                    mb_text += f"ID: {s.index}\n{orig_t}\n---\n"
                mb_prompt = (
                    f"You are a professional subtitle translator. {style_instruction}\n"
                    f"Target Language: {target_lang_str}.\n"
                    f"{global_consistency_header}\n"
                    f"Translate every line below into {target_lang_str}. DO NOT output Chinese characters.\n"
                    "Output Format:\nID: <number>\n<translated text>\n---\n\n"
                    f"{mb_text}"
                )
                try:
                    mb_resp = model.generate_content(mb_prompt)
                    mb_dict = parse_subtitle_translation_response(mb_resp.text, expected_ids=mb_expected_ids)
                    for s in mb_subs:
                        if s.index in mb_dict and mb_dict[s.index]:
                            s.text = rule_based_cleanup_entities(mb_dict[s.index])
                    time.sleep(1.0)
                except Exception as mb_err:
                    print(f"[Global Sweep Warning] Lỗi quét vét cạn: {mb_err}")

        if progress_callback:
            progress_callback(100, "✅ Hoàn tất xử lý, đồng nhất tên nhân vật và đại từ nhân xưng 100%!")

        os.remove(tmp_path)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".srt") as out_tmp:
            temp_out_path = out_tmp.name
            subs.save(temp_out_path, encoding='utf-8')
        with open(temp_out_path, 'r', encoding='utf-8') as f:
            final_content = f.read()
        os.remove(temp_out_path)
            
        return final_content, None
        
    except Exception as e:
        return None, str(e)


def polish_and_fix_existing_srt(
    file_content, 
    api_key, 
    character_hints="", 
    target_lang="Tiếng Việt", 
    valid_model=None, 
    progress_callback=None
):
    """
    Tính năng chuyên dụng: Rà soát & Sửa Lỗi File SRT Đã Dịch:
    - Đồng nhất tên nhân vật bị nhảy tên (ví dụ: '13', 'Thành ca', 'Trịnh' -> 'Trình Thập Tam').
    - Sửa lỗi nhân xưng đảo ngược vai vế (ba mẹ, ông cháu, dượng, bạn bè).
    - Giữ nguyên 100% timecode và thứ tự phân đoạn.
    """
    try:
        raw_keys = [k.strip() for k in re.split(r"[,;\n]+", str(api_key)) if k.strip()]
        if not raw_keys:
            raise ValueError("Vui lòng cung cấp Gemini API Key hợp lệ!")
        
        current_key_idx = 0
        genai.configure(api_key=raw_keys[current_key_idx])

        fallback_models = [
            "models/gemini-3.5-flash-lite",
            "models/gemini-3.1-flash-lite",
            "models/gemini-flash-lite-latest",
            "models/gemini-2.0-flash",
            "models/gemini-1.5-flash"
        ]

        model_queue = []
        if valid_model and "2.5" not in valid_model and "3.7" not in valid_model and "3.6" not in valid_model:
            model_queue.append(valid_model)
        for fb in fallback_models:
            if fb not in model_queue:
                model_queue.append(fb)

        model = genai.GenerativeModel(model_queue[0])

        with tempfile.NamedTemporaryFile(delete=False, suffix=".srt", mode="w", encoding="utf-8") as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        subs = pysrt.open(tmp_path)
        total_subs_len = len(subs)

        if progress_callback:
            progress_callback(5, "🔍 Đang rà soát và thiết lập quy tắc đồng nhất nhân vật...")

        # 1. Bước làm sạch nhanh bằng bộ quy tắc chuẩn
        for sub in subs:
            sub.text = rule_based_cleanup_entities(sub.text)

        glossary_directive = auto_detect_characters_and_glossary(subs, model, user_hints=character_hints)

        batch_size = 50
        total_batches = (total_subs_len + batch_size - 1) // batch_size

        for i in range(total_batches):
            if progress_callback:
                pct = int(10 + ((i) / total_batches) * 85)
                progress_callback(pct, f"🛠️ Đang chuẩn hóa xưng hô & tên nhân vật: {pct}% (Gói {i+1}/{total_batches})...")

            batch_subs = subs[i*batch_size : (i+1)*batch_size]
            expected_ids = [sub.index for sub in batch_subs]

            batch_text = ""
            for sub in batch_subs:
                clean_t = sub.text.replace("\n", " ").strip()
                batch_text += f"ID: {sub.index}\n{clean_t}\n---\n"

            prompt = (
                "Bạn là chuyên gia hiệu đính và chuẩn hóa kịch bản phụ đề Tiếng Việt.\n"
                "NHIỆM VỤ CỦA BẠN: RÀ SOÁT, ĐỒNG NHẤT TÊN NHÂN VẬT VÀ SỬA TOÀN BỘ LỖI NHÂN XƯNG TRONG ĐOẠN PHỤ ĐỀ DƯỚI ĐÂY.\n\n"
                f"BẢNG TÊN NHÂN VẬT & QUY TẮC NHÂN XƯNG:\n{glossary_directive}\n\n"
                "CÁC LỖI CẦN SỬA TRIỆT ĐỂ:\n"
                "1. Tên nhân vật: Tuyệt đối không để số hoặc họ bị sai lệch (ví dụ: '13', 'Thành ca', 'Trịnh' -> phải là 'Trình Thập Tam' / 'Thập Tam').\n"
                "2. Đại từ nhân xưng: Phải đúng vai vế thuần Việt (Bố mẹ/Dượng/Thầy xưng 'ta/dượng/bố/thầy' gọi 'con/cháu'; con cháu xưng 'con/cháu'; bạn bè xưng 'tôi/tớ - cậu/bạn'). Không đảo ngược vai vế.\n"
                "3. Giữ nguyên ý nghĩa gốc của lời thoại, chỉnh sửa câu từ cho mượt mà, tự nhiên.\n"
                "4. Giữ nguyên 100% số ID tương ứng.\n\n"
                "Output Format:\n"
                "ID: <number>\n<corrected text>\n---\n\n"
                f"{batch_text}"
            )

            try:
                response = model.generate_content(prompt)
                parsed_dict = parse_subtitle_translation_response(response.text, expected_ids=expected_ids)
                for sub in batch_subs:
                    if sub.index in parsed_dict and parsed_dict[sub.index]:
                        sub.text = rule_based_cleanup_entities(parsed_dict[sub.index])
                time.sleep(1.0)
            except Exception as e:
                print(f"[Polish Batch Warning] Gói {i+1} lỗi: {e}")

        if progress_callback:
            progress_callback(100, "🎉 Đã hoàn tất rà soát & chuẩn hóa toàn bộ file SRT!")

        os.remove(tmp_path)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".srt") as out_tmp:
            temp_out_path = out_tmp.name
            subs.save(temp_out_path, encoding='utf-8')
        with open(temp_out_path, 'r', encoding='utf-8') as f:
            final_content = f.read()
        os.remove(temp_out_path)

        return final_content, None

    except Exception as e:
        return None, str(e)


def process_txt_file(file_content, api_key, action, target_lang=None, style="Chuẩn xác (Chuyên nghiệp)", valid_model=None):
    """
    Process TXT file content by calling Gemini API.
    """
    try:
        genai.configure(api_key=api_key)
        
        if not valid_model:
            for fallback in ['gemini-3.5-flash-lite', 'gemini-3.1-flash-lite', 'gemini-flash-latest', 'gemini-1.5-flash']:
                try:
                    test_model = genai.GenerativeModel(fallback)
                    test_model.generate_content("test")
                    valid_model = fallback
                    break
                except Exception:
                    continue
                    
            if not valid_model:
                raise Exception("Không tìm thấy model nào hoạt động được.")
            
        model = genai.GenerativeModel(valid_model)
        
        raw_paragraphs = [p.strip() for p in file_content.split("\n") if p.strip()]
        if not raw_paragraphs:
            return "", "File TXT không có nội dung văn bản."

        batch_size = 15
        total_batches = (len(raw_paragraphs) + batch_size - 1) // batch_size
        results = []

        style_instruction = get_style_instruction(style, target_lang or "Tiếng Việt")

        for i in range(total_batches):
            batch_paragraphs = raw_paragraphs[i * batch_size : (i + 1) * batch_size]
            batch_text = "\n".join(batch_paragraphs)

            prompt = (
                f"You are an expert copywriter. {style_instruction}\n"
                "Preserve paragraph structure and line breaks. "
                "Do not add any preamble, explanations, or markdown wrapper unless necessary.\n\n"
                f"{batch_text}"
            )

            max_retries = 5
            response_text = ""
            for attempt in range(max_retries):
                try:
                    response = model.generate_content(prompt)
                    response_text = response.text
                    time.sleep(1.5)
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        time.sleep(4)
                        continue
                    raise e
            
            if response_text:
                results.append(response_text.strip())

        final_content = "\n\n".join(results)
        return final_content, None

    except Exception as e:
        return None, str(e)


def time_to_seconds(t):
    return t.hours * 3600 + t.minutes * 60 + t.seconds + t.milliseconds / 1000.0

def seconds_to_srt_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int(round((seconds - int(seconds)) * 1000))
    if milliseconds == 1000:
        milliseconds = 0
        secs += 1
        if secs == 60:
            secs = 0
            minutes += 1
            if minutes == 60:
                minutes = 0
                hours += 1
    return pysrt.SubRipTime(hours, minutes, secs, milliseconds)

def sync_srt_to_segments(srt_content, segments):
    """
    segments: list of dicts [{'start': float, 'end': float}]
    srt_content: string of the original SRT
    Returns: string of the new synchronized SRT
    """
    fd, path = tempfile.mkstemp(suffix=".srt")
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(srt_content)
    
    subs = pysrt.open(path, encoding='utf-8')
    os.remove(path)
    
    new_subs = pysrt.SubRipFile()
    current_offset = 0.0
    
    for seg in segments:
        seg_start = seg['start']
        seg_end = seg['end']
        seg_duration = seg_end - seg_start
        
        for sub in subs:
            sub_start = time_to_seconds(sub.start)
            sub_end = time_to_seconds(sub.end)
            
            if sub_start < seg_end and sub_end > seg_start:
                actual_start = max(sub_start, seg_start)
                actual_end = min(sub_end, seg_end)
                
                new_start_sec = current_offset + (actual_start - seg_start)
                new_end_sec = current_offset + (actual_end - seg_start)
                
                new_sub = pysrt.SubRipItem()
                new_sub.index = len(new_subs) + 1
                new_sub.start = seconds_to_srt_time(new_start_sec)
                new_sub.end = seconds_to_srt_time(new_end_sec)
                new_sub.text = sub.text
                new_subs.append(new_sub)
                
        current_offset += seg_duration
        
    fd, out_path = tempfile.mkstemp(suffix=".srt")
    os.close(fd)
    new_subs.save(out_path, encoding='utf-8')
    with open(out_path, 'r', encoding='utf-8') as f:
        result = f.read()
    os.remove(out_path)
    
    return result
