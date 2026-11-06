#!/bin/bash
# ╔══════════════════════════════════════════════════════════╗
# ║  Video Splitter Pro - 1-Click Launcher cho macOS         ║
# ╚══════════════════════════════════════════════════════════╝

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Kiểm tra xem app đã chạy trên port 8501 chưa
if ! lsof -i :8501 > /dev/null 2>&1; then
    echo "🚀 Đang khởi động Video Splitter Pro..."
    source .venv/bin/activate
    nohup .venv/bin/streamlit run app.py --server.port 8501 --server.address localhost > /dev/null 2>&1 &
    sleep 2
fi

# Mở ngay tab trình duyệt
open "http://localhost:8501"
