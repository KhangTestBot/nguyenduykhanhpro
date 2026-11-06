"""
Automatic YouTube Bot-Check & Age-Verification Bypass Engine for NgDuyKhanh Pro.
Combines 4 automatic layers (Zero-Cookie required):
1. yt-dlp `android_vr` & `web_embedded` client profiles (bypasses SABR & web age/bot walls).
2. `pytubefix` multi-client engine (`ANDROID_VR`, `WEB_EMBED`, `MWEB`, `TV`) with 1080p FFmpeg muxing.
3. Automatic Cloudflare WARP SOCKS5 Local Proxy (`127.0.0.1:40000`) for Google Colab / Datacenter IPs.
4. Cloud Mirror API Fallback (Piped / Invidious public instances).
"""

import os
import re
import sys
import time
import socket
import shutil
import platform
import subprocess
from pathlib import Path

def extract_youtube_id(url: str) -> str | None:
    """Extracts the 11-character YouTube video ID from any YouTube URL."""
    patterns = [
        r"(?:v=|\/videos\/|embed\/|youtu\.be\/|\/v\/|\/e\/|watch\?v=|&v=|shorts\/|live\/)([A-Za-z0-9_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None

def is_port_open(host: str = "127.0.0.1", port: int = 40000) -> bool:
    """Checks if a local TCP port (e.g. WARP SOCKS5 proxy) is open."""
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except Exception:
        return False

def ensure_colab_warp_proxy(port: int = 40000, ui_updater=None) -> str | None:
    """
    On Linux / Google Colab, automatically installs and starts Cloudflare WARP
    in non-intrusive SOCKS5 proxy mode (`socks5://127.0.0.1:40000`).
    Routes ONLY yt-dlp traffic through Cloudflare's clean IP pool without
    affecting Google Colab's VM connection or Streamlit tunnel.
    """
    if is_port_open("127.0.0.1", port):
        return f"socks5://127.0.0.1:{port}"

    if platform.system().lower() != "linux":
        return None

    try:
        if ui_updater:
            ui_updater(
                status_text="🛡️ Đang tự động bật Cloudflare WARP Proxy để đổi IP sạch trên Colab...",
                pct_val=12.0,
                speed_str="WARP Proxy...",
                phase="connecting"
            )

        if not shutil.which("warp-cli"):
            install_script = (
                "curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg && "
                "echo \"deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(lsb_release -cs) main\" > /etc/apt/sources.list.d/cloudflare-client.list && "
                "apt-get update -qq && apt-get install -y -qq cloudflare-warp"
            )
            subprocess.run(install_script, shell=True, capture_output=True, timeout=90)

        if not shutil.which("warp-cli"):
            return None

        subprocess.run("nohup warp-svc >/dev/null 2>&1 &", shell=True)
        time.sleep(2)

        cmds = [
            "warp-cli --accept-tos registration new || warp-cli --accept-tos register || true",
            "warp-cli --accept-tos mode proxy || warp-cli --accept-tos set-mode proxy || true",
            f"warp-cli --accept-tos proxy port {port} || warp-cli --accept-tos set-proxy-port {port} || true",
            "warp-cli --accept-tos connect || true",
        ]
        for c in cmds:
            subprocess.run(c, shell=True, capture_output=True, timeout=15)

        for _ in range(12):
            if is_port_open("127.0.0.1", port):
                return f"socks5://127.0.0.1:{port}"
            time.sleep(0.5)

    except Exception:
        pass

    return None

def download_via_pytubefix(
    url: str,
    output_dir: Path,
    audio_only: bool = False,
    proxies: dict = None,
    ui_updater=None
) -> dict:
    """
    Uses pytubefix multi-client bypass (`ANDROID_VR`, `WEB_EMBED`, `MWEB`, `IOS`)
    to bypass YouTube age/bot walls and merges 1080p video + audio via FFmpeg.
    Auto-installs pytubefix if not yet installed.
    """
    try:
        import pytubefix
    except ImportError:
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-q", "-U", "pytubefix"],
                capture_output=True,
                timeout=45
            )
        except Exception:
            return {"success": False, "error": "Cannot install pytubefix"}

    try:
        from pytubefix import YouTube
        from utils.hardware_accelerator import get_ffmpeg_bin
        ffmpeg = get_ffmpeg_bin()

        clients_to_try = ["ANDROID_VR", "WEB_EMBED", "MWEB", "IOS", "WEB"]

        for client_name in clients_to_try:
            try:
                if ui_updater:
                    ui_updater(
                        status_text=f"🔓 [Bypass {client_name}] Đang vượt xác minh YouTube tự động...",
                        pct_val=18.0,
                        speed_str="Bypass...",
                        phase="downloading"
                    )

                yt_kwargs = {"client": client_name}
                if proxies:
                    yt_kwargs["proxies"] = proxies

                yt = YouTube(url, **yt_kwargs)
                raw_title = yt.title or "youtube_video"
                safe_title = re.sub(r'[\\/*?:"<>|]', "_", raw_title)[:80]

                if audio_only:
                    a_stream = yt.streams.get_audio_only()
                    if not a_stream:
                        continue
                    out_path = a_stream.download(output_path=str(output_dir), filename=f"{safe_title}.m4a")
                    if out_path and os.path.exists(out_path):
                        return {"success": True, "path": str(out_path), "title": safe_title, "thumbnail_path": None}

                # Try 1080p adaptive stream + audio stream first
                v_stream = (
                    yt.streams.filter(adaptive=True, file_extension="mp4", only_video=True, res="1080p").first()
                    or yt.streams.filter(adaptive=True, file_extension="mp4", only_video=True, res="720p").first()
                    or yt.streams.filter(progressive=True, file_extension="mp4").order_by("resolution").desc().first()
                )
                if not v_stream:
                    continue

                if v_stream.is_progressive:
                    out_path = v_stream.download(output_path=str(output_dir), filename=f"{safe_title}.mp4")
                    if out_path and os.path.exists(out_path):
                        return {"success": True, "path": str(out_path), "title": safe_title, "thumbnail_path": None}
                else:
                    a_stream = yt.streams.get_audio_only()
                    if not a_stream:
                        continue
                    v_tmp = output_dir / "v_temp.mp4"
                    a_tmp = output_dir / "a_temp.m4a"
                    final_mp4 = output_dir / f"{safe_title}.mp4"

                    v_stream.download(output_path=str(output_dir), filename="v_temp.mp4")
                    a_stream.download(output_path=str(output_dir), filename="a_temp.m4a")

                    if ui_updater:
                        ui_updater(
                            status_text="🔄 Đang ghép hình ảnh 1080p & âm thanh gốc...",
                            pct_val=92.0,
                            speed_str="Merging...",
                            phase="merging"
                        )

                    cmd = [
                        ffmpeg, "-y",
                        "-i", str(v_tmp),
                        "-i", str(a_tmp),
                        "-c:v", "copy",
                        "-c:a", "aac",
                        str(final_mp4)
                    ]
                    subprocess.run(cmd, capture_output=True, timeout=180)
                    v_tmp.unlink(missing_ok=True)
                    a_tmp.unlink(missing_ok=True)

                    if final_mp4.exists() and final_mp4.stat().st_size > 10000:
                        return {"success": True, "path": str(final_mp4), "title": safe_title, "thumbnail_path": None}
            except Exception:
                continue
    except Exception:
        pass

    return {"success": False, "error": "pytubefix fallback exhausted"}

def download_via_cloud_mirrors(
    video_id: str,
    output_dir: Path,
    audio_only: bool = False,
    ui_updater=None
) -> dict:
    """
    Fallback downloader using public Piped & Invidious API mirrors when YouTube blocks datacenter IPs.
    """
    import requests
    from utils.hardware_accelerator import get_ffmpeg_bin
    ffmpeg = get_ffmpeg_bin()

    if ui_updater:
        ui_updater(
            status_text="🌐 Đang tải qua trạm trung chuyển Cloud Mirror (Bypass Xác Minh Tuổi/Bot)...",
            pct_val=20.0,
            speed_str="Cloud Mirror...",
            phase="downloading"
        )

    piped_apis = [
        "https://pipedapi.kavin.rocks",
        "https://pipedapi.tokhmi.xyz",
        "https://pipedapi.moomoo.me",
        "https://pipedapi.syncpundit.io",
        "https://api-piped.mha.fi",
        "https://pipedapi.drgns.space",
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }

    for api_base in piped_apis:
        try:
            resp = requests.get(f"{api_base}/streams/{video_id}", headers=headers, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            title = data.get("title") or f"youtube_{video_id}"
            safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)[:80]

            if audio_only:
                audio_streams = data.get("audioStreams", [])
                if not audio_streams:
                    continue
                best_a = sorted(audio_streams, key=lambda x: x.get("bitrate", 0), reverse=True)[0]
                a_url = best_a.get("url")
                if not a_url:
                    continue
                out_file = output_dir / f"{safe_title}.m4a"
                cmd = [ffmpeg, "-y", "-i", a_url, "-c", "copy", str(out_file)]
                res = subprocess.run(cmd, capture_output=True, timeout=300)
                if res.returncode == 0 and out_file.exists() and out_file.stat().st_size > 10000:
                    return {"success": True, "path": str(out_file), "title": safe_title, "thumbnail_path": None}

            hls_url = data.get("hls")
            if hls_url:
                out_file = output_dir / f"{safe_title}.mp4"
                cmd = [ffmpeg, "-y", "-i", hls_url, "-c", "copy", "-bsf:a", "aac_adtstoasc", str(out_file)]
                res = subprocess.run(cmd, capture_output=True, timeout=600)
                if res.returncode == 0 and out_file.exists() and out_file.stat().st_size > 50000:
                    return {"success": True, "path": str(out_file), "title": safe_title, "thumbnail_path": None}

            v_streams = [s for s in data.get("videoStreams", []) if not s.get("videoOnly", False)]
            if v_streams:
                best_v = sorted(v_streams, key=lambda x: x.get("height", 0), reverse=True)[0]
                v_url = best_v.get("url")
                if v_url:
                    out_file = output_dir / f"{safe_title}.mp4"
                    with requests.get(v_url, headers=headers, stream=True, timeout=60) as r_dl:
                        r_dl.raise_for_status()
                        with open(out_file, "wb") as f_out:
                            for chunk in r_dl.iter_content(chunk_size=1024 * 512):
                                if chunk:
                                    f_out.write(chunk)
                    if out_file.exists() and out_file.stat().st_size > 50000:
                        return {"success": True, "path": str(out_file), "title": safe_title, "thumbnail_path": None}
        except Exception:
            continue

    return {"success": False, "error": "Cloud mirrors unavailable"}
