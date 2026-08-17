from __future__ import annotations

import mimetypes
import os
import re
import shutil
import tempfile
import urllib.request
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from yt_dlp import YoutubeDL


ROOT_DIR = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = Path(os.getenv("YTVIDEOFREE_OUTPUT_DIR", tempfile.gettempdir())) / "ytvideofree"

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}

VIDEO_QUALITIES = {
    "best": "bv*+ba/b",
    "2160p": "bv*[height<=2160]+ba/b[height<=2160]",
    "1440p": "bv*[height<=1440]+ba/b[height<=1440]",
    "1080p": "bv*[height<=1080]+ba/b[height<=1080]",
    "720p": "bv*[height<=720]+ba/b[height<=720]",
    "480p": "bv*[height<=480]+ba/b[height<=480]",
    "360p": "bv*[height<=360]+ba/b[height<=360]",
}

AUDIO_QUALITIES = {"128", "192", "256", "320"}


class InvalidYouTubeUrl(ValueError):
    """Raised when a submitted URL is not a supported YouTube video URL."""


def normalize_host(host: str) -> str:
    return host.lower().split(":")[0]


def extract_video_id(url: str) -> str | None:
    parsed = urlparse(url.strip())
    host = normalize_host(parsed.netloc)
    path = parsed.path.strip("/")

    if host in {"youtu.be", "www.youtu.be"}:
        candidate = path.split("/")[0]
        return candidate if is_video_id(candidate) else None

    if host not in YOUTUBE_HOSTS:
        return None

    if path == "watch":
        candidate = parse_qs(parsed.query).get("v", [None])[0]
        return candidate if candidate and is_video_id(candidate) else None

    for prefix in ("shorts/", "embed/", "live/", "v/"):
        if path.startswith(prefix):
            candidate = path.removeprefix(prefix).split("/")[0]
            return candidate if is_video_id(candidate) else None

    return None


def is_video_id(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{11}", value or ""))


def validate_youtube_url(url: str) -> str:
    clean_url = (url or "").strip()
    parsed = urlparse(clean_url)
    host = normalize_host(parsed.netloc)

    if parsed.scheme not in {"http", "https"} or host not in YOUTUBE_HOSTS:
        raise InvalidYouTubeUrl("Paste a valid YouTube video, Shorts, Live, or youtu.be URL.")

    if not extract_video_id(clean_url):
        raise InvalidYouTubeUrl("The YouTube link did not include a valid video ID.")

    return clean_url


def find_ffmpeg() -> str | None:
    configured = os.getenv("YTVIDEOFREE_FFMPEG_LOCATION")
    if configured and Path(configured).exists():
        return configured

    if path := shutil.which("ffmpeg"):
        return path

    local = ROOT_DIR / "ffmpeg" / "bin" / "ffmpeg.exe"
    if local.exists():
        return str(local)

    return None


JS_RUNTIMES = ("deno", "node", "bun", "quickjs")
JS_RUNTIME_BINARIES = {"deno": "deno", "node": "node", "bun": "bun", "quickjs": "qjs"}


def find_js_runtimes() -> dict[str, dict[str, str]]:
    """Auto-detect JavaScript runtimes for yt-dlp's YouTube JS-challenge solver.

    Modern yt-dlp needs an external JS runtime (deno, node, bun, quickjs) to
    solve YouTube's bot-check challenges and mint PO tokens; only "deno" is
    enabled by default, which most servers do not have. Without a usable
    runtime YouTube answers with "Sign in to confirm you're not a bot", so we
    enable every runtime found on this machine.

    Returns a dict shaped like yt-dlp's ``js_runtimes`` parameter, e.g.
    ``{"node": {}, "bun": {}}``. Set YTVIDEOFREE_JS_RUNTIMES (comma-separated
    names) to force a specific set; per-runtime locations can be pinned with
    YTVIDEOFREE_DENO_LOCATION / YTVIDEOFREE_NODE_LOCATION / YTVIDEOFREE_BUN_LOCATION /
    YTVIDEOFREE_QUICKJS_LOCATION.
    """
    forced = os.getenv("YTVIDEOFREE_JS_RUNTIMES")
    if forced:
        names = [
            name.strip().lower()
            for name in forced.split(",")
            if name.strip().lower() in JS_RUNTIMES
        ]
        if names:
            return {name: {} for name in names}

    runtimes: dict[str, dict[str, str]] = {}
    for name in JS_RUNTIMES:
        configured = os.getenv(f"YTVIDEOFREE_{name.upper()}_LOCATION")
        if configured and Path(configured).exists():
            runtimes[name] = {"path": configured}
            continue
        binary = shutil.which(JS_RUNTIME_BINARIES[name])
        if name == "quickjs" and not binary:
            binary = shutil.which("quickjs")
        if binary:
            runtimes[name] = {}
    return runtimes


def default_ydl_opts(*, quiet: bool = True) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "cachedir": False,
        "noplaylist": True,
        "no_warnings": True,
        "quiet": quiet,
        "restrictfilenames": True,
        "windowsfilenames": True,
    }

    if ffmpeg := find_ffmpeg():
        opts["ffmpeg_location"] = ffmpeg

    # Enable every available JS runtime so yt-dlp can solve YouTube's
    # anti-bot JS challenges (PO tokens). Without one, YouTube rejects
    # requests from flagged IPs with "Sign in to confirm you're not a bot".
    if runtimes := find_js_runtimes():
        opts["js_runtimes"] = runtimes

    cookies_file = os.getenv("YTVIDEOFREE_COOKIES_FILE")
    if cookies_file:
        opts["cookiefile"] = cookies_file

    return opts


def inspect_video(url: str) -> dict[str, Any]:
    clean_url = validate_youtube_url(url)

    with YoutubeDL(default_ydl_opts()) as ydl:
        info = ydl.extract_info(clean_url, download=False)

    return serialize_info(info)


def serialize_info(info: dict[str, Any]) -> dict[str, Any]:
    formats = info.get("formats") or []
    heights = sorted(
        {
            int(fmt["height"])
            for fmt in formats
            if fmt.get("height") and fmt.get("vcodec") != "none"
        },
        reverse=True,
    )

    video_qualities = ["best"]
    video_qualities.extend(f"{height}p" for height in heights if f"{height}p" in VIDEO_QUALITIES)

    return {
        "id": info.get("id"),
        "title": info.get("title") or "Untitled video",
        "channel": info.get("channel") or info.get("uploader") or "Unknown channel",
        "duration": info.get("duration") or 0,
        "duration_label": format_duration(info.get("duration") or 0),
        "thumbnail": info.get("thumbnail"),
        "webpage_url": info.get("webpage_url"),
        "view_count": info.get("view_count"),
        "upload_date": format_upload_date(info.get("upload_date")),
        "video_qualities": video_qualities,
        "audio_qualities": sorted(AUDIO_QUALITIES, key=int),
        "has_ffmpeg": bool(find_ffmpeg()),
    }


def download_media(url: str, *, mode: str, quality: str = "best", audio_quality: str = "192") -> Path:
    clean_url = validate_youtube_url(url)
    work_dir = OUTPUT_ROOT / uuid.uuid4().hex
    work_dir.mkdir(parents=True, exist_ok=True)

    if mode == "video":
        fmt = VIDEO_QUALITIES.get(quality, VIDEO_QUALITIES["best"])
        opts = {
            **default_ydl_opts(quiet=False),
            "format": fmt,
            "merge_output_format": "mp4",
            "outtmpl": str(work_dir / "%(title).160B.%(ext)s"),
        }
    elif mode == "audio":
        preferred_quality = audio_quality if audio_quality in AUDIO_QUALITIES else "192"
        opts = {
            **default_ydl_opts(quiet=False),
            "format": "bestaudio/best",
            "outtmpl": str(work_dir / "%(title).160B.%(ext)s"),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": preferred_quality,
                }
            ],
        }
    else:
        raise ValueError("mode must be either 'video' or 'audio'")

    with YoutubeDL(opts) as ydl:
        ydl.download([clean_url])

    return newest_download(work_dir)


def newest_download(directory: Path) -> Path:
    files = [
        path
        for path in directory.iterdir()
        if path.is_file() and not path.name.endswith((".part", ".ytdl", ".temp"))
    ]
    if not files:
        raise FileNotFoundError("The media file was not produced.")

    return max(files, key=lambda path: path.stat().st_mtime)


def cleanup_directory(directory: Path) -> None:
    shutil.rmtree(directory, ignore_errors=True)


def media_type_for(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def format_duration(seconds: int | float) -> str:
    total = int(seconds or 0)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_upload_date(value: str | None) -> str | None:
    if not value or len(value) != 8:
        return value
    return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"


def safe_download_name(title: str, suffix: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._ -]+", "", title).strip(" .")
    clean = re.sub(r"\s+", " ", clean).strip()
    clean = clean[:120] or "youtube-transcript"
    return f"{clean}.{suffix}"


# Ordered by quality; YouTube returns 404 for sizes a video does not have.
THUMBNAIL_TEMPLATES = (
    "https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
    "https://i.ytimg.com/vi/{video_id}/sddefault.jpg",
    "https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
)


def fetch_thumbnail(video_id: str) -> tuple[bytes, str]:
    """Return the largest available thumbnail (JPEG bytes, content type)."""
    for template in THUMBNAIL_TEMPLATES:
        url = template.format(video_id=video_id)
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                data = response.read()
        except Exception:
            continue
        # Skip HTML error/redirect pages and only accept real JPEG data.
        if data and data[:3] == b"\xff\xd8\xff":
            return data, "image/jpeg"
    raise LookupError("No thumbnail image is available for this video.")
