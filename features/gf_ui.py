import streamlit as st
import os
import pandas as pd
from utils.file_helpers import get_image_files
from features.gf_tasks import TaskManager

def init_flow_state():
    if 'flow_tasks' not in st.session_state:
        st.session_state['flow_tasks'] = []
    if 'flow_images' not in st.session_state:
        st.session_state['flow_images'] = []
    if 'flow_manager' not in st.session_state:
        st.session_state['flow_manager'] = None
    if 'flow_input_method' not in st.session_state:
        st.session_state['flow_input_method'] = 'Paste'
    if 'flow_manager_state' not in st.session_state:
        st.session_state['flow_manager_state'] = {
            'logs': [],
            'tasks': [],
            'is_running': False,
            'is_paused': False
        }

def render_google_flow():
    init_flow_state()

    is_running = st.session_state['flow_manager_state']['is_running']
    is_paused = st.session_state['flow_manager_state']['is_paused']

    if is_running: badge = '<span style="background:#16a34a;padding:4px 14px;border-radius:20px;font-size:0.8rem;font-weight:600;">⚡ ĐANG CHẠY</span>'
    elif is_paused: badge = '<span style="background:#ca8a04;padding:4px 14px;border-radius:20px;font-size:0.8rem;font-weight:600;">⏸ TẠM DỪNG</span>'
    else: badge = '<span style="background:#334155;padding:4px 14px;border-radius:20px;font-size:0.8rem;font-weight:600;">💤 SẴN SÀNG</span>'

    st.markdown(f"""
    <div style="display:flex;align-items:center;justify-content:space-between;background:linear-gradient(135deg,#1e293b,#0f172a);border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:12px 20px;margin-bottom:16px;">
        <div><span style="font-size:1.3rem;font-weight:700;color:#f8fafc;">🤖 Google Flow</span><br><span style="font-size:0.8rem;color:#94a3b8;">Tự động tạo ảnh trên Google Labs</span></div>
        <div>{badge}</div>
    </div>
    """, unsafe_allow_html=True)

    # ─── CONFIG ROW ─────────────────────────────────────────────
    with st.container():
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: st.text_input("🔌 Port", value="9222", key="flow_port")
        with c2: st.selectbox("🤖 Model", ["Nano Banana 2", "Nano Banana Pro", "Nano Banana Lite"], key="flow_model")
        with c3: st.selectbox("📐 Tỉ lệ", ["16:9", "1:1", "9:16"], key="flow_ratio")
        with c4: st.number_input("📑 Tabs", min_value=1, max_value=10, value=1, key="flow_max_tabs")
        with c5: st.selectbox("⌨️ Kiểu", ["Paste", "Type"], key="flow_input_method")

        out_dir = st.text_input("📁 Thư mục lưu ảnh đầu ra:", value=st.session_state.get('out_dir', '/Users/mac/Documents/ảnh đầu ra'), key="out_dir")

    # ─── PROMPT UPLOAD ──────────────────────────────────────────
    prompt_file = st.file_uploader("📄 Upload file prompt (.txt)", type=["txt"])
    if prompt_file:
        import re
        content = prompt_file.getvalue().decode('utf-8')
        blocks = content.split('\n')

        parsed_items = []
        for block in blocks:
            block = block.replace('\ufeff', '').strip()
            if not block: continue
            if re.match(r'^(={5,}|\-{5,}|\*{5,})', block): continue
            custom_id = None
            m_id = re.search(r'^(\*\*|_)?(?:Prompt\s*|Image\s*)?(\d+):?\.\s*(\*\*|_)?', block, re.IGNORECASE)
            if not m_id:
                m_id = re.search(r'^(\*\*|_)?(\d+)\.\s*(\*\*|_)?', block)
            if m_id: custom_id = int(m_id.group(2))
            block = re.sub(r'^(\*\*|_)?(Prompt\s*\d+:?\s*|Image\s*\d+:?\s*|\d+\.\s*)(\*\*|_)?', '', block, flags=re.IGNORECASE).strip()
            if re.match(r'^[\W_]+$', block): continue
            if re.match(r'^(\*\*|_)?(IMAGE PROMPTS?|PROMPTS? \-|TITLE:|SCENE(S)? \-|VIDEO PROMPTS?|BATCH\s*\d+|PART\s*\d+|\d+\s*prompts? total|Main character:|Keep bottom|No gradients)', block, re.IGNORECASE): continue
            if not block: continue
            block = re.sub(r'^(\[|\()?(\d{1,2}:)?\d{1,2}:\d{2}(\]|\))?\s*', '', block)
            cleaned_prompt = block.replace('\n', ' ').strip()
            parsed_items.append((custom_id, cleaned_prompt))

        content_hash = hash(content)
        if st.session_state.get('last_prompt_hash') != content_hash:
            tasks = []
            for i, (custom_id, prompt) in enumerate(parsed_items):
                task_id = custom_id if custom_id is not None else (i + 1)
                tasks.append({'id': task_id, 'prompt': prompt, 'status': 'Wait...'})
            st.session_state['flow_tasks'] = tasks
            st.session_state['flow_manager_state']['tasks'] = tasks
            st.session_state['last_prompt_hash'] = content_hash

    cols = st.columns([4, 1])
    with cols[0]:
        st.caption("💡 Bot sẽ tự động dán từng câu prompt và tự động lưu ảnh về thư mục đã chọn.")

    # ─── CONTROL BUTTONS ────────────────────────────────────────
    with cols[1]:
        if st.button("▶ START", use_container_width=True, type="primary"):
            if not st.session_state['flow_tasks']:
                st.error("Upload file prompt trước!")
            else:
                is_paused = st.session_state['flow_manager_state']['is_paused']
                is_running = st.session_state['flow_manager_state']['is_running']
                if is_paused:
                    st.session_state['flow_manager'].resume()
                elif not is_running:
                    config = {
                        'port': st.session_state.get('flow_port', '9222'),
                        'mode': st.session_state.get('flow_mode', 'Create Image'),
                        'model': st.session_state.get('flow_model', 'Nano Banana 2'),
                        'ratio': st.session_state.get('flow_ratio', '16:9'),
                        'input_method': st.session_state.get('flow_input_method', 'Paste'),
                        'max_tabs': st.session_state.get('flow_max_tabs', 1),
                        'output_dir': st.session_state.get('out_dir', '/Users/mac/Documents/ảnh đầu ra')
                    }
                    for t in st.session_state['flow_manager_state']['tasks']:
                        t['status'] = 'Wait...'
                    st.session_state['flow_manager_state']['logs'] = []
                    manager = TaskManager(st.session_state['flow_manager_state']['tasks'], config, st.session_state['flow_manager_state'])
                    st.session_state['flow_manager'] = manager
                    manager.start()

        c1, c2 = st.columns(2)
        with c1:
            if st.button("⏸ PAUSE", use_container_width=True):
                if st.session_state['flow_manager']:
                    st.session_state['flow_manager'].pause()
        with c2:
            if st.button("⏹ STOP", use_container_width=True):
                port = st.session_state.get('flow_port', '9222')
                if st.session_state.get('flow_manager'):
                    st.session_state['flow_manager'].stop()
                import subprocess
                subprocess.run(f"pkill -9 -f 'remote-debugging-port={port}'", shell=True, check=False)
                subprocess.run(f"pkill -9 -f 'chrome_debug_profile_{port}'", shell=True, check=False)
                st.session_state['flow_manager_state']['is_running'] = False
                st.session_state['flow_manager_state']['is_paused'] = False
                st.session_state['flow_manager_state']['logs'].append("⏹ Đã dừng tác vụ và kill toàn bộ tab Chrome.")

        st.markdown("---")
        if st.button("🔄 Đổi tài khoản", use_container_width=True):
            import subprocess, shutil
            port = st.session_state.get('flow_port', '9222')
            if st.session_state.get('flow_manager'):
                st.session_state['flow_manager'].stop()
            subprocess.run(f"pkill -9 -f 'remote-debugging-port={port}'", shell=True, check=False)
            subprocess.run(f"pkill -9 -f 'chrome_debug_profile_{port}'", shell=True, check=False)
            profile_dir = os.path.expanduser(f"~/.gemini/antigravity/scratch/chrome_debug_profile_{port}")
            if os.path.exists(profile_dir):
                try: shutil.rmtree(profile_dir)
                except: pass
            st.session_state['flow_manager_state']['is_running'] = False
            st.session_state['flow_manager_state']['is_paused'] = False
            st.success("✅ Đã xoá session. Bấm START để đăng nhập lại.")

    # ─── TASK TABLE ─────────────────────────────────────────────
    tasks = st.session_state['flow_manager_state']['tasks']
    if tasks:
        df = pd.DataFrame(tasks)
        st.dataframe(df, use_container_width=True, height=180)
    else:
        st.info("📝 Upload file prompt để bắt đầu.")

    # ─── LARGE LOG CONSOLE ──────────────────────────────────────
    st.markdown('<div style="margin-top:8px;"></div>', unsafe_allow_html=True)

    c_log, c_clear = st.columns([10, 2])
    with c_log:
        st.markdown("**📄 Log Automation**")
    with c_clear:
        if st.button("🧹 Xoá log", use_container_width=True):
            st.session_state['flow_manager_state']['logs'] = []

    if is_running:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=1000, key="log_refresh")

    logs = st.session_state['flow_manager_state']['logs']
    log_text = "\n".join(logs[-100:]) if logs else "Đang chờ hoạt động..."
    import html
    escaped = html.escape(log_text)
    st.markdown(f'<div style="background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:12px;height:400px;overflow:auto;font-family:monospace;font-size:0.85rem;color:#e2e8f0;white-space:pre-wrap;">{escaped}</div>', unsafe_allow_html=True)
