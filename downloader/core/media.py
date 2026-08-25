from __future__ import annotations

import logging
import mimetypes
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import importlib

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from ..errors import is_bot_check_error
from .cookiefile import inspect_cookies_file


logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = Path(os.getenv("YTVIDEOFREE_OUTPUT_DIR", tempfile.gettempdir())) / "ytvideofree"

# Directory where a standalone Node.js binary is downloaded when no JS runtime
# is installed on the server. Override with YTVIDEOFREE_RUNTIME_DIR.
RUNTIME_DIR = Path(
    os.getenv("YTVIDEOFREE_RUNTIME_DIR", str(ROOT_DIR / ".cache" / "runtimes"))
)

# Node version used for the auto-downloaded runtime (official nodejs.org build).
NODE_VERSION = os.getenv("YTVIDEOFREE_NODE_VERSION", "v22.14.0")

# Set to "0" to disable auto-downloading a Node.js runtime on bare servers.
AUTO_DOWNLOAD_RUNTIME = os.getenv("YTVIDEOFREE_AUTO_RUNTIME", "1") != "0"

# YouTube runs many playback clients (web, Android, iOS, TV, ...) and trusts
# each one to a different degree. The ``tv`` (television) client is the least
# scrutinised and the one that most reliably clears the "Sign in to confirm
# you're not a bot" challenge from datacenter/VPS IPs without an account or
# cookies; ``web_safari`` is its recommended companion. Each group below is
# tried in its own YoutubeDL run, in order, so a rejected group falls through
# to the next one — no cookies or user sign-in required.
#
# Override the whole sequence with YTVIDEOFREE_PLAYER_CLIENTS: a
# comma-separated list of groups, where ":" joins clients inside one group.
# Example: "tv:web_safari,ios:android,mweb,tv_embedded,web"
DEFAULT_PLAYER_CLIENT_GROUPS = (
    ("tv", "web_safari"),
    ("ios", "android"),
    ("mweb", "web_embedded"),
    ("tv_embedded",),
    ("web",),
)


def player_client_groups() -> tuple[tuple[str, ...], ...]:
    """Return the ordered player-client groups to try, from config or defaults."""
    configured = os.getenv("YTVIDEOFREE_PLAYER_CLIENTS")
    if configured:
        groups = tuple(
            tuple(client.strip() for client in group.split(":") if client.strip())
            for group in configured.split(",")
            if group.strip()
        )
        if groups:
            return groups
    return DEFAULT_PLAYER_CLIENT_GROUPS

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

# yt-dlp silently ignores JS runtimes older than its minimum supported version
# (Node >= 22 for the EJS PO-token solver, Bun >= 1.2.11, Deno >= 2.3.0,
# QuickJS >= 2023.12.9). Used only as a fallback when yt-dlp's own runtime
# classes are unavailable; the primary gate uses those classes so it always
# matches the installed yt-dlp version exactly.
FALLBACK_MIN_RUNTIME_VERSIONS = {
    "node": (22, 0, 0),
    "bun": (1, 2, 11),
    "deno": (2, 3, 0),
    "quickjs": (2023, 12, 9),
}

# One lock shared by all workers so only a single Node download happens at a
# time; the process-local flag avoids re-attempting a failed download forever.
_runtime_lock = threading.Lock()
_runtime_download_attempted = False
_ejs_install_attempted = False

# Probe results are cached per (runtime name, binary path) so requests do not
# re-run subprocess version probes on every call.
_runtime_probe_cache: dict[tuple[str, str], tuple[str | None, bool]] = {}


def _parse_runtime_version(name: str, output: str) -> tuple[int, ...] | None:
    """Parse a runtime's version from ``--version``/``--help`` output."""
    patterns = {
        "node": r"v?(\d+(?:\.\d+)*)",
        "bun": r"(\d+(?:\.\d+)*)",
        "deno": r"deno\s+v?(\d+(?:\.\d+)*)",
        # QuickJS versions are dates (e.g. "2023-12-09" or "2024-01-13").
        "quickjs": r"version\s+(\d+(?:[.-]\d+){1,2})",
    }
    match = re.search(patterns[name], output or "")
    if not match:
        return None
    try:
        return tuple(int(part) for part in re.split(r"[.-]", match.group(1)))
    except ValueError:
        return None


def _runtime_version_from_binary(name: str, binary: str) -> tuple[int, ...] | None:
    args = ["--help"] if name == "quickjs" else ["--version"]
    try:
        result = subprocess.run(
            [binary, *args], capture_output=True, text=True, timeout=15, check=False
        )
    except Exception:
        return None
    return _parse_runtime_version(name, (result.stdout or "") + (result.stderr or ""))


def _runtime_probe(name: str, binary: str) -> tuple[str | None, bool]:
    """Return (version, supported) for a runtime binary, gated like yt-dlp.

    yt-dlp silently skips runtimes older than its minimum supported version, so
    an installed Node 18 looks "found" but is never used by the solver — the
    app would stay bot-checked. Probe the binary with yt-dlp's own runtime
    classes so the gate matches the installed yt-dlp exactly; fall back to a
    hardcoded minimum-version table if that internal API is unavailable.
    """
    key = (name, binary)
    if key in _runtime_probe_cache:
        return _runtime_probe_cache[key]

    version: str | None = None
    supported = False
    try:
        from yt_dlp.globals import supported_js_runtimes

        runtime_cls = supported_js_runtimes.value.get(name)
        if runtime_cls is not None:
            info = runtime_cls(path=binary).info
            if info is not None:
                version, supported = info.version, info.supported
    except Exception:
        logger.debug("yt-dlp runtime probe unavailable; using fallback version table.", exc_info=True)

    if version is None:
        parsed = _runtime_version_from_binary(name, binary)
        minimum = FALLBACK_MIN_RUNTIME_VERSIONS.get(name)
        supported = bool(parsed) and (minimum is None or parsed >= minimum)
        version = ".".join(str(part) for part in parsed) if parsed else None

    result = (version, supported)
    _runtime_probe_cache[key] = result
    return result


def _runtime_is_supported(name: str, binary: str) -> bool:
    return _runtime_probe(name, binary)[1]


def _resolve_runtime_binary(name: str) -> str | None:
    configured = os.getenv(f"YTVIDEOFREE_{name.upper()}_LOCATION")
    if configured and Path(configured).exists():
        return configured
    binary = shutil.which(JS_RUNTIME_BINARIES[name])
    if name == "quickjs" and not binary:
        binary = shutil.which("quickjs")
    return binary


def discover_runtime_binaries() -> dict[str, dict[str, Any]]:
    """Probe every candidate runtime binary (env-pinned or on PATH).

    Unlike ``find_js_runtimes`` this also reports binaries that are too old for
    yt-dlp's solver (``supported: False``), so the admin status page can explain
    why the bundled Node.js is being used instead. Results are cached.
    """
    details: dict[str, dict[str, Any]] = {}
    for name in JS_RUNTIMES:
        binary = _resolve_runtime_binary(name)
        if binary:
            version, supported = _runtime_probe(name, binary)
            details[name] = {"path": binary, "version": version, "supported": supported}
    return details


def _node_asset() -> tuple[str, str] | None:
    """Return the (basename, archive-ext) of the official Node.js build for this machine."""
    machine = platform.machine().lower()
    system = sys.platform.lower()

    if system.startswith("win"):
        os_name, ext = "win", "zip"
        arch = "x64" if machine in ("amd64", "x86_64") else "arm64" if machine in ("arm64", "aarch64") else None
    elif system == "darwin":
        os_name, ext = "darwin", "tar.gz"
        arch = "arm64" if machine in ("arm64", "aarch64") else "x64" if machine in ("x86_64", "amd64") else None
    elif system.startswith("linux"):
        os_name, ext = "linux", "tar.xz"
        arch = "x64" if machine in ("x86_64", "amd64") else "arm64" if machine in ("arm64", "aarch64") else None
    else:
        return None

    if not arch:
        return None
    # NODE_VERSION defaults to "v22.14.0" (with a leading "v"); the official
    # archives are named node-v22.14.0-..., so strip it to avoid "node-vv22...".
    return f"node-v{NODE_VERSION.lstrip('v')}-{os_name}-{arch}", ext


def _node_binary(directory: Path) -> Path:
    return directory / ("node.exe" if sys.platform.startswith("win") else "bin" / "node")


def _node_works(path: Path) -> bool:
    try:
        result = subprocess.run(
            [str(path), "--version"], capture_output=True, timeout=15, check=False
        )
        return result.returncode == 0
    except Exception:
        return False


def ensure_js_runtime() -> Path | None:
    """Download a standalone Node.js binary into RUNTIME_DIR when none is available.

    Bare VPS images (Hostinger PVS, plain Ubuntu, etc.) often ship without a JS
    runtime, which makes yt-dlp fail YouTube's bot check. This downloads the
    official Node.js binary from nodejs.org on first use so the PO-token solver
    works without the operator installing anything. Returns the path to the
    node binary, or None when the download fails or is disabled.
    """
    global _runtime_download_attempted

    asset = _node_asset()
    if asset is None:
        return None

    basename, ext = asset
    node_dir = RUNTIME_DIR / basename
    node_bin = _node_binary(node_dir)

    if (
        node_bin.exists()
        and _node_works(node_bin)
        and _runtime_is_supported("node", str(node_bin))
    ):
        return node_bin

    with _runtime_lock:
        if _runtime_download_attempted:
            # Already tried this process (or another worker is doing it).
            if (
                node_bin.exists()
                and _node_works(node_bin)
                and _runtime_is_supported("node", str(node_bin))
            ):
                return node_bin
            return None
        _runtime_download_attempted = True

        if not AUTO_DOWNLOAD_RUNTIME:
            logger.warning("No JS runtime found and YTVIDEOFREE_AUTO_RUNTIME=0; not downloading Node.")
            return None

        url = f"https://nodejs.org/dist/{NODE_VERSION}/{basename}.{ext}"
        archive = RUNTIME_DIR / f"{basename}.{ext}"
        try:
            RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
            logger.info("Downloading Node.js %s for the yt-dlp bot-check solver: %s", NODE_VERSION, url)
            urllib.request.urlretrieve(url, archive)
            if ext == "zip":
                with zipfile.ZipFile(archive) as zf:
                    zf.extractall(RUNTIME_DIR)
            else:
                with tarfile.open(archive, "r:*") as tf:
                    tf.extractall(RUNTIME_DIR)
        except Exception as exc:
            logger.warning("Failed to auto-download Node.js runtime: %s", exc)
            return None
        finally:
            if archive.exists():
                try:
                    archive.unlink()
                except OSError:
                    pass

        if _node_works(node_bin) and _runtime_is_supported("node", str(node_bin)):
            return node_bin
        logger.warning("Downloaded Node.js binary does not run (or is too old); removing it.")
        shutil.rmtree(node_dir, ignore_errors=True)
        return None


def ensure_ejs_package() -> bool:
    """Install the ``yt-dlp-ejs`` Python package when it is missing.

    yt-dlp's YouTube bot-check solver (EJS) needs two JavaScript scripts:
    ``yt.solver.core.js`` and ``yt.solver.lib.js``.  Only the core script is
    vendored inside yt-dlp itself; the lib script is provided by the separate
    ``yt-dlp-ejs`` package (pypackage source).  Without it the solver falls
    back to a GitHub download which may fail on firewalled VPS images.
    Installing the package locally makes the solver work reliably.

    Returns True when the package is (now) available, False on failure.
    """
    global _ejs_install_attempted

    # Already present — nothing to do.
    try:
        importlib.import_module("yt_dlp_ejs")
        return True
    except ImportError:
        pass

    if _ejs_install_attempted:
        return False
    _ejs_install_attempted = True

    logger.info("yt-dlp-ejs package not found; installing via pip...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "yt-dlp-ejs"],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
        importlib.invalidate_caches()
        importlib.import_module("yt_dlp_ejs")
        logger.info("yt-dlp-ejs installed successfully.")
        return True
    except Exception as exc:
        logger.warning("Failed to auto-install yt-dlp-ejs: %s", exc)
        return False


def find_js_runtimes() -> dict[str, dict[str, str]]:
    """Auto-detect JavaScript runtimes for yt-dlp's YouTube JS-challenge solver.

    Modern yt-dlp needs an external JS runtime (deno, node, bun, quickjs) to
    solve YouTube's bot-check challenges and mint PO tokens; only "deno" is
    enabled by default, which most servers do not have. Without a usable
    runtime YouTube answers with "Sign in to confirm you're not a bot", so we
    enable every runtime found on this machine — but only versions yt-dlp's
    solver actually accepts (e.g. Node >= 22). A too-old runtime is silently
    ignored by yt-dlp, so when none is installed *or* the installed one is too
    old, a standalone Node.js binary is downloaded automatically (see
    ``ensure_js_runtime``), making bare VPS images work out of the box.

    Returns a dict shaped like yt-dlp's ``js_runtimes`` parameter, e.g.
    ``{"node": {"path": "/usr/bin/node"}}``. Set YTVIDEOFREE_JS_RUNTIMES
    (comma-separated names) to force a specific set; per-runtime locations can
    be pinned with YTVIDEOFREE_DENO_LOCATION / YTVIDEOFREE_NODE_LOCATION /
    YTVIDEOFREE_BUN_LOCATION / YTVIDEOFREE_QUICKJS_LOCATION.
    """
    forced = os.getenv("YTVIDEOFREE_JS_RUNTIMES")
    if forced:
        names = [
            name.strip().lower()
            for name in forced.split(",")
            if name.strip().lower() in JS_RUNTIMES
        ]
    else:
        names = list(JS_RUNTIMES)

    runtimes: dict[str, dict[str, str]] = {}
    for name in names:
        binary = _resolve_runtime_binary(name)
        if binary and _runtime_is_supported(name, binary):
            runtimes[name] = {"path": binary}

    # No *usable* runtime: on bare servers there is none at all, and on some VPS
    # images there is one that is too old for yt-dlp's solver (e.g. Node 18,
    # which yt-dlp silently ignores). Either way, grab a standalone Node >= 22
    # so the PO-token solver can run without the operator installing anything.
    if not runtimes:
        if bundled := ensure_js_runtime():
            if _runtime_is_supported("node", str(bundled)):
                runtimes["node"] = {"path": str(bundled)}

    return runtimes


def default_ydl_opts(*, quiet: bool = True) -> dict[str, Any]:
    # Ensure yt-dlp-ejs is installed before building opts.  The solver
    # scripts must be available for the PO-token challenge to work.
    ensure_ejs_package()

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

    # Allow yt-dlp to download EJS challenge-solver scripts from GitHub
    # when the yt-dlp-ejs Python package is not installed.  The solver
    # needs two scripts (yt.solver.lib.js + yt.solver.core.js); on bare
    # VPS images the pypackage source is absent and only the core script
    # is vendored, so the lib script must come from GitHub.
    opts["remote_components"] = {"ejs:github"}

    # Only set the player_client list when the caller hasn't already specified
    # one. ``_extract_info``/``download_media`` always override this with each
    # client group in ``player_client_groups()``; this default keeps the opts
    # valid when used standalone (e.g. by the admin status live test).
    extractor_args = dict(opts.get("extractor_args") or {})
    yt_args = dict(extractor_args.get("youtube") or {})
    if "player_client" not in yt_args:
        yt_args["player_client"] = list(player_client_groups()[0])
    extractor_args["youtube"] = yt_args
    opts["extractor_args"] = extractor_args

    cookies_file = configured_cookies_file()
    if cookies_file:
        opts["cookiefile"] = cookies_file
        report = inspect_cookies_file(cookies_file)
        if not report.usable:
            logger.warning("Configured cookies file is not usable: %s", report.summary())

    return opts


def configured_cookies_file() -> str | None:
    """Absolute path of YTVIDEOFREE_COOKIES_FILE, or None when not configured.

    Relative paths resolve against the project root: systemd/gunicorn may start
    the app from a different working directory, and yt-dlp silently ignores a
    cookie file it cannot find — which leaves the bot check firing with no hint
    why.
    """
    cookies_file = os.getenv("YTVIDEOFREE_COOKIES_FILE")
    if not cookies_file:
        return None
    cookie_path = Path(cookies_file).expanduser()
    if not cookie_path.is_absolute():
        cookie_path = ROOT_DIR / cookie_path
    return str(cookie_path)


def _opts_with_player_clients(
    opts: dict[str, Any], clients: tuple[str, ...]
) -> dict[str, Any]:
    """Return a copy of opts that requests a specific player-client group."""
    opts = dict(opts)
    extractor_args = dict(opts.get("extractor_args") or {})
    extractor_args["youtube"] = {
        **dict(extractor_args.get("youtube") or {}),
        "player_client": list(clients),
    }
    opts["extractor_args"] = extractor_args
    return opts


def _should_try_next_client(message: str) -> bool:
    """Whether a DownloadError should fall through to the next client group.

    Only bot checks, HTTP 403s, and "no usable formats" (e.g. YouTube forcing
    SABR streaming on a client) are worth retrying with a different client.
    Real errors — private videos, removed videos, bad URLs — are re-raised.
    """
    normalized = message.lower()
    return (
        is_bot_check_error(message)
        or "http error 403" in normalized
        or "requested format is not available" in normalized
        or "no video formats" in normalized
        or "no formats" in normalized
    )


def _extract_info(clean_url: str, *, download: bool, opts: dict[str, Any]) -> dict[str, Any]:
    """Run yt-dlp, walking the player-client groups until one is accepted.

    YouTube answers flagged/datacenter IPs with "Sign in to confirm you're not
    a bot" for some clients and lets others through. The client groups are
    ordered most-reliable-first (``tv`` + ``web_safari``) so a server can
    extract metadata without cookies, a JS runtime, or any user sign-in.
    """
    last_error: DownloadError | None = None
    for clients in player_client_groups():
        try:
            with YoutubeDL(_opts_with_player_clients(opts, clients)) as ydl:
                return ydl.extract_info(clean_url, download=download)
        except DownloadError as exc:
            last_error = exc
            if not _should_try_next_client(str(exc)):
                raise
            logger.info(
                "YouTube rejected client(s) %s (%s); trying the next group.",
                ",".join(clients),
                str(exc)[:160],
            )
    raise last_error


def inspect_video(url: str) -> dict[str, Any]:
    clean_url = validate_youtube_url(url)
    info = _extract_info(clean_url, download=False, opts=default_ydl_opts())
    return serialize_info(info)


def extract_raw_info(url: str) -> dict[str, Any]:
    """Return yt-dlp's full info dict (subtitles, captions, formats, ...)."""
    clean_url = validate_youtube_url(url)
    return _extract_info(clean_url, download=False, opts=default_ydl_opts())


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

    last_error: DownloadError | None = None
    for clients in player_client_groups():
        try:
            with YoutubeDL(_opts_with_player_clients(opts, clients)) as ydl:
                ydl.download([clean_url])
            return newest_download(work_dir)
        except DownloadError as exc:
            last_error = exc
            if not _should_try_next_client(str(exc)):
                raise
            logger.info(
                "YouTube rejected client(s) %s during download (%s); trying the next group.",
                ",".join(clients),
                str(exc)[:160],
            )
    raise last_error


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
