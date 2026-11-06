#!/bin/bash
# ╔══════════════════════════════════════════════════════════╗
# ║     NgDuyKhanh Pro - Script Cài đặt & Chạy         ║
# ╚══════════════════════════════════════════════════════════╝

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"

echo ""
echo "🎬 VIDEO SPLITTER PRO - Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Kiểm tra Python
if ! command -v python3 &>/dev/null; then
  echo "❌ Python 3 không tìm thấy. Vui lòng cài đặt Python 3.9+."
  exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✅ Python $PYTHON_VERSION tìm thấy"

# Kiểm tra ffmpeg
if ! command -v ffmpeg &>/dev/null; then
  echo "⚠️  ffmpeg chưa được cài. Đang cài qua Homebrew..."
  if command -v brew &>/dev/null; then
    brew install ffmpeg
  else
    echo "❌ Homebrew chưa cài. Vui lòng cài ffmpeg thủ công:"
    echo "   brew install ffmpeg"
    exit 1
  fi
else
  echo "✅ ffmpeg đã có sẵn"
fi

# Tạo virtual environment nếu chưa có
if [ ! -d "$VENV_DIR" ]; then
  echo "📦 Tạo virtual environment..."
  python3 -m venv "$VENV_DIR"
fi

# Kích hoạt venv
source "$VENV_DIR/bin/activate"

# Cài thư viện
echo "📥 Đang cài đặt thư viện Python..."
pip install --upgrade pip -q
pip install -r "$PROJECT_DIR/requirements.txt" -q

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 Khởi động ứng dụng tại http://localhost:8501"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Chạy Streamlit
cd "$PROJECT_DIR"
streamlit run app.py --server.port 8501 --server.address localhost
