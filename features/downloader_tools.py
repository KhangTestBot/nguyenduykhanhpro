"""
Feature module: Video & Thumbnail Downloader (Tải Video & Thumbnail HD)
Dedicated file for downloading videos and HD thumbnail images from YouTube, TikTok, Facebook, Instagram, etc.
"""

import os
import time
import streamlit as st
import tempfile
import urllib.request
import re
from pathlib import Path

from features.common_ui import (
    YTDLP_AVAILABLE,
    download_video_from_url,
    render_download_progress_card,
    human_size,
    safe_filename,
)

def extract_hd_thumbnail(url: str, output_dir: Path) -> dict:
    """Tải nhanh ảnh bìa Thumbnail HD chất lượng cao từ link video mà không cần tải video."""
    url_match = re.search(r'''https?://[^\s<>"'()\[\]{}|]+''', url)
    clean_url = url_match.group(0) if url_match else url.strip()
    if "bilibili.com/video/" in clean_url or "b23.tv" in clean_url or "tiktok.com" in clean_url or "douyin.com" in clean_url:
        clean_url = clean_url.split("?")[0]

    try:
        import yt_dlp
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }
        
        if "bilibili.com" in clean_url or "b23.tv" in clean_url:
            ydl_opts['http_headers'] = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Referer': 'https://www.bilibili.com/',
                'Origin': 'https://www.bilibili.com',
            }
            ydl_opts['extractor_args'] = {'bilibili': {'player_client': ['android']}}
        elif "douyin.com" in clean_url or "tiktok.com" in clean_url:
            ydl_opts['http_headers'] = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.douyin.com/',
            }

        # Trích xuất metadata (ưu tiên Direct trước siêu tốc <0.5s, fallback Brave/Chrome nếu cần)
        info = None
        for b_name in [None, "brave", "chrome"]:
            try:
                opts = dict(ydl_opts)
                if b_name:
                    opts['cookiesfrombrowser'] = (b_name,)
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(clean_url, download=False)
                if info:
                    break
            except Exception:
                continue

        if not info:
            return {"success": False, "error": "Không thể lấy dữ liệu video để trích xuất thumbnail."}
            
        title = info.get('title', 'thumbnail_video')
        thumbnail_url = info.get('thumbnail')
        
        # Chọn thumbnail độ phân giải tốt nhất
        if 'thumbnails' in info and info['thumbnails']:
            sorted_thumbs = sorted(
                info['thumbnails'],
                key=lambda x: (x.get('preference', 0) or 0, x.get('height', 0) or 0, x.get('width', 0) or 0),
                reverse=True
            )
            if sorted_thumbs and sorted_thumbs[0].get('url'):
                thumbnail_url = sorted_thumbs[0]['url']
                
        if not thumbnail_url:
            return {"success": False, "error": "Không tìm thấy đường dẫn ảnh bìa của video này."}
            
        # Xác định định dạng ảnh
        ext = ".jpg"
        if ".png" in thumbnail_url.lower():
            ext = ".png"
        elif ".webp" in thumbnail_url.lower():
            ext = ".webp"
            
        thumb_path = output_dir / f"thumbnail{ext}"
        
        # Tải thumbnail an toàn với SSL bypass và fallback
        try:
            import requests
            r = requests.get(thumbnail_url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}, timeout=15, verify=False)
            with open(thumb_path, 'wb') as f:
                f.write(r.content)
        except Exception:
            import ssl
            ctx = ssl._create_unverified_context()
            req = urllib.request.Request(thumbnail_url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp, open(thumb_path, 'wb') as f:
                f.write(resp.read())
            
        return {
            "success": True,
            "title": title,
            "thumbnail_path": str(thumb_path),
            "thumbnail_url": thumbnail_url
        }
    except Exception as e:
        return {"success": False, "error": f"Không thể lấy thumbnail: {str(e)}"}


def render_downloader_tools():
    """Renders the 'Tải Video' feature tab."""
    st.markdown("""
    <div class="hero-banner">
    <div class="hero-title">📥 Tải Video & Thumbnail HD</div>
    <div class="hero-subtitle">Tải video 1080p và ảnh bìa Thumbnail HD từ YouTube, TikTok, Facebook, Instagram...</div>
    <div class="badge-row">
    <span class="badge">🌐 Đa nền tảng</span>
    <span class="badge">🎞️ Video 1080p Max</span>
    <span class="badge">🖼️ Thumbnail HD (.jpg/.png)</span>
    <span class="badge">⚡ Tăng tốc đa luồng siêu tốc</span>
    </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">🔗 Nhập Link Video & Tùy Chọn</div>', unsafe_allow_html=True)
    
    if not YTDLP_AVAILABLE:
        st.error("⚠️ Cần cài `yt-dlp` để tải video: `pip install yt-dlp`")
        st.markdown('</div>', unsafe_allow_html=True)
        return
        
    video_url = st.text_input(
        "Dán link video vào đây:",
        placeholder="https://www.youtube.com/watch?v=... hoặc link TikTok, Facebook, Douyin, Bilibili",
        label_visibility="collapsed",
        key="downloader_url_input"
    )
    
    download_mode = st.radio(
        "Chọn chế độ cần tải:",
        ["🎬 Tải Cả Video & Thumbnail HD", "🖼️ Chỉ Tải Thumbnail HD (Siêu Tốc <1s)"],
        horizontal=True,
        key="downloader_mode_radio"
    )
    
    if st.button("🚀 Bắt Đầu Tải Ngay", use_container_width=True, type="primary", key="btn_start_downloader"):
        if not video_url.strip():
            st.error("Vui lòng nhập link video!")
        else:
            st.session_state["downloader_result"] = None
            dl_status = st.empty()
            dl_dir = Path("output_clips") / f"download_{int(time.time())}"
            dl_dir.mkdir(parents=True, exist_ok=True)
            
            if download_mode.startswith("🖼️"):
                dl_status.markdown(
                    render_download_progress_card(
                        status_text="🖼️ Đang bóc tách ảnh bìa Thumbnail HD...",
                        pct_val=50.0,
                        speed_str="Siêu tốc",
                        phase="connecting"
                    ),
                    unsafe_allow_html=True
                )
                result = extract_hd_thumbnail(video_url, dl_dir)
                result["only_thumb"] = True
            else:
                result = download_video_from_url(
                    url=video_url,
                    output_dir=dl_dir,
                    progress_placeholder=dl_status,
                )
                result["only_thumb"] = False
                
                # Nếu tải video chưa lấy được thumbnail thì lấy thêm thumbnail
                if result["success"] and not result.get("thumbnail_path"):
                    dl_status.markdown(
                        render_download_progress_card(
                            status_text="🖼️ Đang trích xuất thêm ảnh bìa Thumbnail HD...",
                            pct_val=100.0,
                            speed_str="Hoàn tất tải",
                            phase="merging"
                        ),
                        unsafe_allow_html=True
                    )
                    thumb_res = extract_hd_thumbnail(video_url, dl_dir)
                    if thumb_res["success"]:
                        result["thumbnail_path"] = thumb_res["thumbnail_path"]
                        
            if result["success"]:
                dl_status.markdown(
                    render_download_progress_card(
                        status_text=f"✅ Đã tải xong: {result.get('title', 'Video')}",
                        pct_val=100.0,
                        speed_str="100% Hoàn tất",
                        downloaded_str=human_size(Path(result["path"]).stat().st_size) if result.get("path") and Path(result["path"]).exists() else "",
                        total_str=human_size(Path(result["path"]).stat().st_size) if result.get("path") and Path(result["path"]).exists() else "",
                        phase="completed"
                    ),
                    unsafe_allow_html=True
                )
                st.session_state["downloader_result"] = result
                st.session_state["downloader_temp_dir"] = str(dl_dir)
                st.success(f"🎉 Đã xử lý thành công: **{result.get('title', 'Video')}**")
            else:
                dl_status.empty()
                st.error(f"❌ Tải thất bại: {result.get('error', 'Lỗi không xác định')}")

    # Hiển thị kết quả tải nếu có trong session_state
    if "downloader_result" in st.session_state and st.session_state["downloader_result"]:
        res = st.session_state["downloader_result"]
        dl_title = res.get("title", "downloaded_file")
        safe_title_str = safe_filename(dl_title)
        
        st.markdown("<hr style='border-color: rgba(255,255,255,0.1); margin: 25px 0;'>", unsafe_allow_html=True)
        st.markdown(f'<div class="card-title">📊 Kết Quả Tải Về: {dl_title}</div>', unsafe_allow_html=True)
        
        # 1. Hiển thị Thumbnail Preview nếu có
        thumb_path = res.get("thumbnail_path")
        if thumb_path and Path(thumb_path).exists():
            st.markdown("### 🖼️ Xem Trước Ảnh Bìa (Thumbnail HD)")
            st.image(thumb_path, use_container_width=True)
            
        # 2. Nút tải về & Mở file trực tiếp trên máy
        col_v, col_t = st.columns(2)
        
        # Nút tải Video (nếu có)
        video_path = res.get("path")
        if video_path and Path(video_path).exists():
            file_size = Path(video_path).stat().st_size
            with col_v:
                with open(video_path, "rb") as vf:
                    st.download_button(
                        label=f"🎬 Tải Video Về Máy ({human_size(file_size)})",
                        data=vf,
                        file_name=f"{safe_title_str}.mp4",
                        mime="video/mp4",
                        use_container_width=True,
                        type="primary"
                    )
        elif res.get("only_thumb"):
            with col_v:
                st.info("ℹ️ Đang ở chế độ Chỉ Tải Thumbnail. Nếu muốn lấy file Video, hãy chọn chế độ 'Tải Cả Video & Thumbnail' ở trên.")

        # Nút tải Thumbnail
        if thumb_path and Path(thumb_path).exists():
            ext_name = Path(thumb_path).suffix.lower()
            mime_type = "image/jpeg" if ext_name == ".jpg" else f"image/{ext_name.replace('.', '')}"
            with col_t:
                with open(thumb_path, "rb") as tf:
                    st.download_button(
                        label=f"🖼️ Tải Ảnh Bìa Thumbnail ({human_size(Path(thumb_path).stat().st_size)})",
                        data=tf,
                        file_name=f"{safe_title_str}_thumbnail{ext_name}",
                        mime=mime_type,
                        use_container_width=True
                    )

        # 3. Nút Mở Trực Tiếp Trên Máy Tính (Siêu tốc 0 giây, không lo rớt mạng)
        if video_path and Path(video_path).exists():
            import sys, subprocess
            st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
            if st.button("📂 Mở Thư Mục Chứa Video Trên Máy Tính (Finder/Explorer)", use_container_width=True, key="btn_open_video_folder"):
                try:
                    if sys.platform == "darwin":
                        subprocess.run(["open", "-R", str(video_path)])
                    elif sys.platform == "win32":
                        subprocess.run(["explorer", f"/select,{str(video_path)}"])
                    else:
                        subprocess.run(["xdg-open", str(Path(video_path).parent)])
                    st.toast("📂 Đã mở thư mục chứa video trên máy của bạn!")
                except Exception as e_open:
                    st.warning(f"Đường dẫn file trên máy: `{video_path}`")

    st.markdown('</div>', unsafe_allow_html=True)
