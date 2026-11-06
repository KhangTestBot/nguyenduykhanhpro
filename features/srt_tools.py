"""
Feature module: SRT Subtitle Tools (Xử lý SRT)
Dedicated file for subtitle translation, paraphrasing, character consistency, and error fixing.
"""

import streamlit as st
import importlib

def render_srt_tools():
    """Renders the 'Xử lý SRT' feature tab."""
    import srt_processor
    importlib.reload(srt_processor)

    st.markdown("""
    <div class="hero-banner">
    <div class="hero-title">📝 Xử Lý & Đồng Nhất Phụ Đề (SRT / TXT)</div>
    <div class="hero-subtitle">Dịch thuật & Rà soát đồng nhất tên nhân vật, chuẩn hóa đại từ nhân xưng (ba mẹ, dượng, ông cháu) bằng Gemini AI</div>
    <div class="badge-row">
    <span class="badge">👥 Đồng nhất tên nhân vật</span>
    <span class="badge">👨‍👩‍👧‍👦 Chuẩn hóa nhân xưng</span>
    <span class="badge">🌐 Dịch tự động</span>
    <span class="badge">✍️ Viết lại (Paraphrase)</span>
    <span class="badge">📄 SRT & TXT</span>
    </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">🔑 Cấu hình API</div>', unsafe_allow_html=True)
    api_key = st.text_input("Gemini API Key", type="password", value=os.environ.get("GEMINI_API_KEY", ""), placeholder="Nhập API Key vào đây...")
    
    force_recheck = False
    if "api_key_valid" not in st.session_state or st.session_state.get("current_api_key") != api_key:
        force_recheck = True
    elif not st.session_state.get("api_key_valid") and not st.session_state.get("api_error"):
        force_recheck = True
    elif "all_candidates" not in st.session_state:
        force_recheck = True
        
    if force_recheck:
        st.session_state["api_key_valid"] = False
        st.session_state["valid_model"] = None
        st.session_state["available_models"] = []
        st.session_state["current_api_key"] = api_key
        st.session_state["api_error"] = ""
        
        if api_key:
            with st.spinner("Đang kiểm tra API Key..."):
                available_models = []
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=api_key)
                    
                    models = list(genai.list_models())
                    if models:
                        st.session_state["api_key_valid"] = True
                        for m in models:
                            if 'generateContent' in m.supported_generation_methods:
                                available_models.append(m.name)
                                
                        st.session_state["all_candidates"] = available_models
                        
                        default_model = None
                        preferences = ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-flash-lite-latest", "gemini-3.1-flash-lite", "gemini-3.6-flash", "gemini-flash-latest"]
                        
                        test_candidates = []
                        for pref in preferences:
                            for m in available_models:
                                if pref in m and m not in test_candidates:
                                    test_candidates.append(m)
                                    break
                                    
                        if not test_candidates:
                            test_candidates = available_models[:3]
                            
                        for m in test_candidates:
                            try:
                                test_m = genai.GenerativeModel(m)
                                test_m.generate_content("hello")
                                default_model = m
                                break
                            except Exception:
                                continue
                                
                        if not default_model:
                            default_model = available_models[0] if available_models else None
                                
                        st.session_state["valid_model"] = default_model
                    else:
                        st.session_state["api_error"] = "API Key không hợp lệ hoặc không có quyền truy cập model nào."
                except Exception as e:
                    st.session_state["api_key_valid"] = False
                    st.session_state["api_error"] = f"Lỗi API: {str(e)}"

    if api_key:
        if st.session_state.get("api_key_valid"):
            st.success("✅ Kết nối API Gemini thành công!")
            
            candidates = st.session_state.get("all_candidates", [])
            if not candidates and st.session_state.get("valid_model"):
                candidates = [st.session_state["valid_model"]]
                
            filtered_candidates = [c for c in candidates if "2.5" not in c and "3.7" not in c and "3.6" not in c]
            if not filtered_candidates:
                filtered_candidates = [c for c in candidates if "2.5" not in c]
                
            high_quota_priority = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemini-2.0-flash-lite", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-3.5-flash"]
            sorted_candidates = []
            for p in high_quota_priority:
                for c in filtered_candidates:
                    if p in c and c not in sorted_candidates:
                        sorted_candidates.append(c)
            for c in filtered_candidates:
                if c not in sorted_candidates:
                    sorted_candidates.append(c)
                    
            valid_idx = 0
            if st.session_state.get("valid_model") in sorted_candidates:
                valid_idx = sorted_candidates.index(st.session_state.get("valid_model"))
            
            selected_model = st.selectbox("Chọn Model Gemini để sử dụng (Khuyên dùng gemini-3.5-flash-lite hạn ngạch cao 1,500 lượt/ngày):", sorted_candidates, index=valid_idx)
            st.session_state["selected_model"] = selected_model
        elif st.session_state.get("api_error"):
            st.error(f"❌ {st.session_state['api_error']}")
            
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">⚙️ Xử lý phụ đề & văn bản (SRT / TXT)</div>', unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("Tải lên file .srt hoặc .txt", type=["srt", "txt"], key="srt_tools_uploader")

    processing_mode = st.radio(
        "Mục đích xử lý:",
        [
            "🌐 Dịch Mới & Viết Lại Phụ Đề (Từ file phụ đề gốc Tiếng Trung / Anh...)",
            "🛠️ Rà Soát & Đồng Nhất Tên Nhân Vật / Sửa Lỗi Nhân Xưng (Cho file SRT đã dịch bị lỗi)"
        ],
        index=0,
        key="srt_tools_proc_mode"
    )
    is_polishing_mode = "Rà Soát" in processing_mode
    
    col_act1, col_act2 = st.columns(2)
    with col_act1:
        target_lang = st.selectbox(
            "🌐 Ngôn ngữ đích:", 
            ["Tiếng Việt", "English", "日本語 (Japanese)", "한국어 (Korean)", "中文 (Chinese)", "Français (French)", "Español (Spanish)", "Deutsch (German)", "Ngôn ngữ khác"],
            index=0,
            key="srt_target_lang_select"
        )
        if target_lang == "Ngôn ngữ khác":
            target_lang = st.text_input("Nhập ngôn ngữ đích", value="", key="srt_custom_lang_input")
            
    with col_act2:
        if not is_polishing_mode:
            selected_style = st.selectbox(
                "🎭 Phong cách Dịch & Viết lại:",
                [
                    "🎯 Sát Nghĩa Nhất (Chính xác 100% / Bám sát từng chữ & ngữ cảnh gốc)",
                    "🧙‍♂️ Tu Tiên / Tiên Hiệp (Đạo hữu, Bản tọa, Cảnh giới, Độ kiếp...)",
                    "🤣 Hài Hước / Cợt Nhả / Mặn Mòi (Dí dỏm, GenZ Trend, TikTok)",
                    "🎬 Kịch Tính / Review Phim ('Và ngay lúc này...', Giật gân)",
                    "⚡ Tóm Tắt Ngắn Gọn (Tối giản câu từ cho video ngắn)"
                ],
                index=0,
                key="srt_style_select"
            )
        else:
            st.info("💡 **Chế độ Rà Soát**: Tự động phát hiện tên bị dịch thành số (ví dụ: `13`), chuẩn hóa tên riêng và sửa các lỗi đảo lộn xưng hô gia đình (ba mẹ, ông cháu, dượng, bạn bè).")
            selected_style = "Sát nghĩa"

    # Phần nhập gợi ý tên nhân vật
    character_hints_input = st.text_input(
        "👥 Gợi ý Tên Nhân Vật & Vai Vế Xưng Hô (Tùy chọn — AI sẽ tự động phân tích nếu để trống):",
        placeholder="Ví dụ: Trình Thập Tam (nam chính), Ellie (đội trưởng), Lý Bảo Nhi (bạn gái), Gia Cát... Dượng xưng dượng gọi cháu.",
        help="Giúp AI khóa cứng tên nhân vật và xưng hô đúng 100% từ đầu đến cuối phim, không bị nhảy tên hay lộn vai vế.",
        key="srt_char_hints_input"
    )
        
    if st.button("🚀 Bắt Đầu Xử Lý Ngay", use_container_width=True, type="primary", key="btn_start_srt_proc"):
        if not api_key:
            st.error("Vui lòng nhập Gemini API Key!")
        elif not uploaded_file:
            st.error("Vui lòng tải lên file SRT hoặc TXT!")
        else:
            progress_bar = st.progress(0)
            status_box = st.empty()
            
            def update_progress(pct, msg):
                progress_bar.progress(min(100, max(0, pct)))
                status_box.info(msg)
                
            try:
                content = uploaded_file.read().decode("utf-8")
            except UnicodeDecodeError:
                content = uploaded_file.read().decode("latin-1", errors="replace")
            
            act = "translate_rewrite"
            ext = uploaded_file.name.lower().split(".")[-1]
            
            if ext == "txt":
                final_result, err = srt_processor.process_txt_file(
                    content, api_key, act, target_lang, style=selected_style,
                    valid_model=st.session_state.get("selected_model", st.session_state.get("valid_model"))
                )
            else:
                if is_polishing_mode:
                    final_result, err = srt_processor.polish_and_fix_existing_srt(
                        content, 
                        api_key, 
                        character_hints=character_hints_input.strip(), 
                        target_lang=target_lang,
                        valid_model=st.session_state.get("selected_model", st.session_state.get("valid_model")),
                        progress_callback=update_progress
                    )
                else:
                    final_result, err = srt_processor.process_srt_file(
                        content, 
                        api_key, 
                        action=act, 
                        target_lang=target_lang, 
                        style=selected_style,
                        valid_model=st.session_state.get("selected_model", st.session_state.get("valid_model")),
                        character_hints=character_hints_input.strip(),
                        progress_callback=update_progress
                    )
                
            status_box.empty()
            progress_bar.empty()
            
            if err:
                st.error(f"Lỗi: {err}")
            else:
                st.session_state["srt_tools_result"] = final_result
                st.session_state["srt_tools_filename"] = uploaded_file.name
                st.success("🎉 Đã xử lý & chuẩn hóa thành công toàn bộ phụ đề!")

    if st.session_state.get("srt_tools_result"):
        res_text = st.session_state["srt_tools_result"]
        orig_fname = st.session_state.get("srt_tools_filename", "subtitle.srt")
        
        st.markdown("<hr style='border-color: rgba(255,255,255,0.1); margin: 20px 0;'>", unsafe_allow_html=True)
        st.markdown("### 👀 Bản xem trước kết quả đã đồng nhất")
        st.text_area("Nội dung kết quả (bản xem trước)", value=res_text, height=300, key="srt_tools_preview_area")
        
        st.download_button(
            "📥 Tải file SRT đã chuẩn hóa", 
            res_text, 
            file_name=f"polished_{orig_fname}", 
            mime="text/plain",
            type="primary",
            key="btn_dl_srt_persist"
        )
    st.markdown('</div>', unsafe_allow_html=True)
