"""
YouTube Downloader & Transcript Extractor

Downloads YouTube videos, audio, and transcripts via URL.
Supports regular videos, Shorts, and playlist URLs.

Usage:
  python ytdl.py info <url>
  python ytdl.py video <url> [options]
  python ytdl.py audio <url> [options]
  python ytdl.py transcript <url> [options]
  python ytdl.py all <url> [options]
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter, SRTFormatter

from downloader.core.cookiefile import CookieFileReport, inspect_cookies_file
from downloader.core.media import (
    _opts_with_fallback_clients,
    find_js_runtimes as app_find_js_runtimes,
)
from downloader.errors import BOT_CHECK_MESSAGE, is_bot_check_error


OUTPUT_DIR = Path.cwd() / "downloads"

# Set from the --verbose flag in main() so default_opts() can forward it.
_VERBOSE = False


def extract_video_id(url: str) -> str | None:
    patterns = [
        r"(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/watch\?v=)([a-zA-Z0-9_-]{11})",
        r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/v/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        if m := re.search(pattern, url):
            return m.group(1)
    return None


def find_ffmpeg() -> str | None:
    if path := shutil.which("ffmpeg"):
        return path
    local = Path(__file__).parent / "ffmpeg" / "bin" / "ffmpeg.exe"
    if local.exists():
        return str(local)
    return None


def find_js_runtimes() -> dict:
    """Return yt-dlp js_runtimes config for every runtime found on PATH.

    Modern yt-dlp needs an external JS runtime (deno/node/bun/quickjs) to solve
    YouTube's anti-bot JS challenges; only deno is enabled by default. Delegates
    to the app's shared detection, which also auto-downloads a standalone Node.js
    on bare servers when none is installed.
    """
    return app_find_js_runtimes()


def cookies_file() -> str | None:
    """Absolute path of the configured cookies file (YTVIDEOFREE_COOKIES_FILE)."""
    value = os.getenv("YTVIDEOFREE_COOKIES_FILE")
    if not value:
        return None
    return str(Path(value).expanduser().resolve())


def cookie_report() -> CookieFileReport | None:
    """Inspect the configured cookies file; None when none is configured."""
    path = cookies_file()
    if not path:
        return None
    return inspect_cookies_file(path)


def default_opts() -> dict:
    opts = {"quiet": False, "no_warnings": True}
    if _VERBOSE:
        opts["verbose"] = True
    ffmpeg = find_ffmpeg()
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg
    runtimes = find_js_runtimes()
    if runtimes:
        opts["js_runtimes"] = runtimes
    else:
        print(
            "Warning: no JavaScript runtime available for yt-dlp's anti-bot solver. "
            "Install nodejs, or set YTVIDEOFREE_COOKIES_FILE to a cookies.txt file.",
            file=sys.stderr,
        )
    path = cookies_file()
    if path:
        opts["cookiefile"] = path
        report = inspect_cookies_file(path)
        if not report.usable:
            print(f"Warning: {report.summary()}", file=sys.stderr)
    return opts


def retry_bot_check(url: str, opts: dict, *, download: bool):
    """Run yt-dlp once, retrying with cookie-free fallback player clients when
    YouTube answers with the bot check. Mirrors downloader/core/media.py."""
    try:
        with YoutubeDL(opts) as ydl:
            if download:
                return ydl.download([url])
            return ydl.extract_info(url, download=False)
    except DownloadError as exc:
        if is_bot_check_error(str(exc)):
            print("YouTube bot check detected — retrying with fallback player clients...")
            with YoutubeDL(_opts_with_fallback_clients(opts)) as ydl:
                if download:
                    return ydl.download([url])
                return ydl.extract_info(url, download=False)
        raise


def get_video_info(url: str) -> dict:
    return retry_bot_check(url, {**default_opts(), "quiet": True}, download=False)


def format_duration(seconds: int) -> str:
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"


def cmd_install_ffmpeg():
    dest = Path(__file__).parent / "ffmpeg"
    if (dest / "bin" / "ffmpeg.exe").exists():
        print("ffmpeg already installed.")
        return

    arch = "win64" if sys.maxsize > 2**32 else "win32"
    url = f"https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-{arch}-gpl.zip"
    zip_path = dest / "ffmpeg.zip"

    print(f"Downloading ffmpeg ({arch})...")
    dest.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, zip_path)

    print("Extracting...")
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            if member.startswith("ffmpeg-master") and ("/bin/" in member or "\\bin\\" in member):
                zf.extract(member, dest)
                src = dest / member
                rel = Path(*member.split("/")[1:] if "/" in member else member.split("\\")[1:])
                (dest / rel).parent.mkdir(parents=True, exist_ok=True)
                if not (dest / rel).exists():
                    (dest / rel).parent.mkdir(parents=True, exist_ok=True)
                    Path(dest / member).rename(dest / rel)

    zip_path.unlink()
    print(f"ffmpeg installed at: {dest / 'bin' / 'ffmpeg.exe'}")


def cmd_info(url: str):
    info = get_video_info(url)
    print(f"Title:       {info.get('title', 'N/A')}")
    print(f"Channel:     {info.get('channel', info.get('uploader', 'N/A'))}")
    print(f"Duration:    {format_duration(info.get('duration', 0))}")
    print(f"Views:       {info.get('view_count', 0):,}")
    print(f"Upload date: {info.get('upload_date', 'N/A')}")
    print(f"Video ID:    {info.get('id', 'N/A')}")
    print(f"Type:        {'Short' if info.get('duration', 0) <= 60 else 'Video'}")
    if formats := info.get("formats", []):
        best_video = next(
            (f for f in reversed(formats) if f.get("vcodec") != "none"), None
        )
        best_audio = next(
            (f for f in formats if f.get("acodec") != "none" and f.get("vcodec") == "none"), None
        )
        if best_video:
            print(f"Best video:  {best_video.get('height', '?')}p ({best_video.get('ext', '?')})")
        if best_audio:
            print(f"Best audio:  {best_audio.get('abr', '?')}kbps ({best_audio.get('ext', '?')})")


def cmd_video(url: str, output: str, quality: str):
    out = Path(output) if output else OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)

    quality_map = {
        "best": "bestvideo+bestaudio/best",
        "2160p": "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
        "1440p": "bestvideo[height<=1440]+bestaudio/best[height<=1440]",
        "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
    }
    fmt = quality_map.get(quality, quality_map["best"])

    opts = {
        **default_opts(),
        "format": fmt,
        "outtmpl": str(out / "%(title)s.%(ext)s"),
        "merge_output_format": "mp4",
    }

    if not find_ffmpeg():
        print("Warning: ffmpeg not found. Video+audio merging disabled (limited quality).")
        print("Run 'python ytdl.py install-ffmpeg' for best quality.\n")
        opts["format"] = "best[height<=720]/best"

    retry_bot_check(url, opts, download=True)
    print(f"\nDownloaded to: {out.resolve()}")


def cmd_audio(url: str, output: str):
    out = Path(output) if output else OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)

    if not find_ffmpeg():
        print("Error: Audio extraction requires ffmpeg.")
        print("Run 'python ytdl.py install-ffmpeg' to install it.")
        sys.exit(1)

    opts = {
        **default_opts(),
        "format": "bestaudio/best",
        "outtmpl": str(out / "%(title)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    retry_bot_check(url, opts, download=True)
    print(f"\nDownloaded to: {out.resolve()}")


def cmd_transcript(url: str, output: str, srt: bool = False, languages: list[str] | None = None):
    video_id = extract_video_id(url)
    if not video_id:
        print("Error: Could not extract video ID from URL")
        sys.exit(1)

    langs = languages or ["en", "en-US", "en-GB", "a.en"]

    ytt_api = YouTubeTranscriptApi()

    try:
        transcript_list = ytt_api.list(video_id)
    except Exception as e:
        print(f"Error: No transcripts available — {e}")
        sys.exit(1)

    transcript = None
    lang_used = None
    for lang in langs:
        try:
            transcript = transcript_list.find_transcript([lang])
            lang_used = lang
            break
        except Exception:
            continue

    if transcript is None:
        try:
            transcript = transcript_list.find_generated_transcript(["en"])
            lang_used = "en"
        except Exception:
            available = [t.language_code for t in transcript_list]
            print(f"No suitable transcript found. Available: {available}")
            sys.exit(1)

    captions = transcript.fetch()

    ext = "srt" if srt else "txt"
    if srt:
        formatter = SRTFormatter()
    else:
        formatter = TextFormatter()

    text = formatter.format_transcript(captions)

    if output:
        out_path = Path(output)
        if out_path.is_dir():
            out_path = out_path / f"{video_id}.{ext}"
    else:
        out_path = OUTPUT_DIR / f"{video_id}.{ext}"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    print(f"Transcript saved ({lang_used}): {out_path.resolve()}")


def cmd_all(url: str, output: str, quality: str, srt: bool = False):
    print("=" * 50)
    print("Downloading video...")
    print("=" * 50)
    cmd_video(url, output, quality)

    if find_ffmpeg():
        print("\n" + "=" * 50)
        print("Downloading audio...")
        print("=" * 50)
        cmd_audio(url, output)

    print("\n" + "=" * 50)
    print("Downloading transcript...")
    print("=" * 50)
    cmd_transcript(url, output, srt)

    out = Path(output) if output else OUTPUT_DIR
    print(f"\nAll downloads completed. Files saved in: {out.resolve()}")


def main():
    # Emoji and non-Latin characters in video titles crash the console on
    # Windows (cp1252); force UTF-8 output everywhere.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="YouTube Video, Shorts & Transcript Downloader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ytdl.py info "https://youtube.com/watch?v=dQw4w9WgXcQ"
  python ytdl.py video "https://youtube.com/shorts/abc123" -q 1080p
  python ytdl.py audio "https://youtu.be/dQw4w9WgXcQ"
  python ytdl.py transcript "https://youtube.com/watch?v=dQw4w9WgXcQ" --srt
  python ytdl.py all "https://youtube.com/watch?v=dQw4w9WgXcQ" -q 720p
        """,
    )
    parser.add_argument("command", choices=["info", "video", "audio", "transcript", "all", "install-ffmpeg"])
    parser.add_argument("url", nargs="?", help="YouTube video/Short URL")
    parser.add_argument("-o", "--output", help="Output directory (default: ./downloads)")
    parser.add_argument("-q", "--quality", default="best",
                        choices=["best", "2160p", "1440p", "1080p", "720p", "480p", "360p"],
                        help="Video quality (default: best)")
    parser.add_argument("--srt", action="store_true", help="Export transcript as SRT format")
    parser.add_argument("--lang", nargs="+", help="Transcript language codes (e.g. en es fr)")
    parser.add_argument(
        "--cookies",
        help="Path to a Netscape-format cookies.txt file exported from a browser "
        "(for YouTube's bot check; see YTVIDEOFREE_COOKIES_FILE env var)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show the full yt-dlp debug log plus cookie/runtime diagnostics",
    )

    args = parser.parse_args()

    if args.command == "install-ffmpeg":
        cmd_install_ffmpeg()
        return

    if not args.url:
        parser.error("the following arguments are required: url")

    video_id = extract_video_id(args.url)
    if not video_id:
        print("Error: Invalid YouTube URL")
        print("Expected formats:")
        print("  https://youtube.com/watch?v=...")
        print("  https://youtu.be/...")
        print("  https://youtube.com/shorts/...")
        print("  https://youtube.com/embed/...")
        sys.exit(1)

    if args.cookies:
        os.environ["YTVIDEOFREE_COOKIES_FILE"] = args.cookies

    global _VERBOSE
    _VERBOSE = args.verbose

    if args.verbose:
        runtimes = find_js_runtimes()
        print("JS runtimes in use:", ", ".join(sorted(runtimes)) or "NONE")
        if report := cookie_report():
            print("Cookies:", report.summary())
        else:
            print("Cookies: none configured (YTVIDEOFREE_COOKIES_FILE not set)")
        print()

    print(f"Video ID: {video_id}\n")

    try:
        match args.command:
            case "info":
                cmd_info(args.url)
            case "video":
                cmd_video(args.url, args.output, args.quality)
            case "audio":
                cmd_audio(args.url, args.output)
            case "transcript":
                cmd_transcript(args.url, args.output, args.srt, args.lang)
            case "all":
                cmd_all(args.url, args.output, args.quality, args.srt)
    except DownloadError as exc:
        if is_bot_check_error(str(exc)):
            print("\n" + BOT_CHECK_MESSAGE, file=sys.stderr)
            if not args.verbose:
                if report := cookie_report():
                    print("\nDiagnosis:", report.summary(), file=sys.stderr)
                runtimes = find_js_runtimes()
                print(
                    "JS runtimes in use:", ", ".join(sorted(runtimes)) or "NONE",
                    file=sys.stderr,
                )
                print(
                    "Tip: re-run with --verbose for the full yt-dlp debug log.",
                    file=sys.stderr,
                )
            sys.exit(1)
        raise


if __name__ == "__main__":
    main()
