# 🎬 NgDuyKhanh Pro

> Ứng dụng Streamlit tự động cắt video dài & xử lý lách bản quyền cho TikTok, Reels, Shorts.

---

## 🗂️ Cấu Trúc Thư Mục

```
video-splitter-pro/
├── app.py                  # Ứng dụng Streamlit chính
├── requirements.txt        # Danh sách thư viện
├── run.sh                  # Script cài đặt & chạy nhanh
├── .streamlit/
│   └── config.toml         # Theme dark mode, cấu hình server
└── output_clips/           # Thư mục chứa clip đầu ra (tự tạo)
    └── run_YYYYMMDD_HHMMSS/
        ├── Tên Series Phần 1.mp4
        ├── Tên Series Phần 2.mp4
        └── ...
```

---

## ⚡ Cài Đặt & Chạy Nhanh

### Cách 1: Script tự động (Khuyên dùng)
```bash
cd /Users/mac/.gemini/antigravity/scratch/video-splitter-pro
chmod +x run.sh
./run.sh
```

### Cách 2: Thủ công
```bash
# 1. Vào thư mục dự án
cd /Users/mac/.gemini/antigravity/scratch/video-splitter-pro

# 2. Tạo & kích hoạt môi trường ảo
python3 -m venv .venv
source .venv/bin/activate

# 3. Cài ffmpeg (nếu chưa có)
brew install ffmpeg

# 4. Cài thư viện Python
pip install -r requirements.txt

# 5. Chạy ứng dụng
streamlit run app.py
```

---

## 🛠️ Tính Năng

| Tính năng | Mô tả |
|-----------|-------|
| ✂️ Auto Split | Cắt video dài thành clip ≤59s |
| 📱 9:16 Format | Tự động chuyển 16:9 → 9:16 |
| 🌫️ Blur Background | Nền mờ cho video ngang |
| 🔍 Zoom | Phóng to 0–30% |
| 🔄 Mirror Flip | Lật ngang |
| ⚡ Speed Up | Tăng tốc 1.0x–1.1x |
| ☀️ Brightness | Điều chỉnh độ sáng |
| 🎭 Contrast | Điều chỉnh tương phản |
| 📥 Download | Tải từng clip trực tiếp |

---

## 📋 Yêu Cầu Hệ Thống

- **Python**: 3.9+
- **ffmpeg**: Cài qua `brew install ffmpeg`
- **RAM**: Khuyên dùng ≥8GB cho video HD
- **Disk**: Tối thiểu 10GB trống

---

## 🔗 Truy Cập

Sau khi chạy, mở trình duyệt tại: **http://localhost:8501**
