"""Admin-only diagnostic page: YouTube bot-check readiness and a live test.

Rendered under /admin/status/ so the operator can see at a glance the player
client groups the app will try, whether a JS runtime (needed only for the web
client's PO-token solver), ffmpeg, and a cookies file are configured, and run a
live extraction against a known YouTube video to confirm the server's IP is not
being bot-checked.
"""

from __future__ import annotations

import os
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

import yt_dlp
from yt_dlp.utils import DownloadError

from .core.cookiefile import inspect_cookies_file
from .core.media import (
    AUTO_DOWNLOAD_RUNTIME,
    NODE_VERSION,
    RUNTIME_DIR,
    _runtime_probe,
    configured_cookies_file,
    discover_runtime_binaries,
    ensure_ejs_package,
    ensure_js_runtime,
    find_ffmpeg,
    find_js_runtimes,
    inspect_video,
    player_client_groups,
)
from .errors import BOT_CHECK_MESSAGE, clean_error, is_bot_check_error

# A stable, well-known public video used for the live bot-check test.
# (The classic yt-dlp test video BaW_jenozKc was removed from YouTube, so we
# use "Me at the zoo", the first YouTube video, which is unlikely to vanish.)
TEST_VIDEO_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


def _check_ejs_package() -> dict[str, Any]:
    """Check whether the yt-dlp-ejs Python package is installed."""
    try:
        import yt_dlp_ejs

        return {"installed": True, "version": getattr(yt_dlp_ejs, "version", "unknown")}
    except ImportError:
        return {"installed": False, "version": None}


def _check_optional_package(name: str) -> dict[str, Any]:
    """Check whether an optional pip package is installed."""
    try:
        from importlib import metadata

        return {"installed": True, "version": metadata.version(name)}
    except Exception:
        return {"installed": False, "version": None}


def _status_context() -> dict[str, Any]:
    # Try to auto-install yt-dlp-ejs if missing.
    ensure_ejs_package()

    runtimes = find_js_runtimes()
    detected = discover_runtime_binaries()

    # Include auto-downloaded (bundled) runtimes in the display table too.
    for name, config in runtimes.items():
        path = config.get("path")
        if path and detected.get(name, {}).get("path") != path:
            version, supported = _runtime_probe(name, path)
            detected[name] = {"path": path, "version": version, "supported": supported}

    runtime_rows = [
        {
            "name": name,
            "path": detail["path"],
            "version": detail.get("version"),
            "supported": detail["supported"],
            "in_use": name in runtimes,
        }
        for name, detail in sorted(detected.items())
    ]

    cookies_file = configured_cookies_file() or ""
    cookie_report = inspect_cookies_file(cookies_file) if cookies_file else None
    return {
        "title": "YouTube bot-check status",
        "test_video_url": TEST_VIDEO_URL,
        "runtimes": runtimes,
        "runtimes_label": ", ".join(sorted(runtimes)) or "none detected",
        "runtime_rows": runtime_rows,
        "too_old_installed": any(not d["supported"] for d in detected.values()),
        "runtime_dir": str(RUNTIME_DIR),
        "auto_download_runtime": AUTO_DOWNLOAD_RUNTIME,
        "node_version": NODE_VERSION,
        "ffmpeg": find_ffmpeg() or "",
        "cookies_file": cookies_file,
        "cookies_exists": bool(cookies_file) and os.path.exists(cookies_file),
        "cookie_report": cookie_report,
        "bot_check_message": BOT_CHECK_MESSAGE,
        "ejs_package": _check_ejs_package(),
        "remote_components_enabled": True,
        "player_client_groups": player_client_groups(),
        "yt_dlp_version": getattr(getattr(yt_dlp, "version", None), "__version__", "unknown"),
        "pot_provider": _check_optional_package("bgutil-ytdlp-pot-provider"),
        "curl_cffi": _check_optional_package("curl_cffi"),
    }


@staff_member_required
@require_http_methods(["GET", "POST"])
def bot_check_status(request: HttpRequest):
    if request.method == "POST":
        return JsonResponse(_run_live_test())

    context = _status_context()
    return render(request, "admin/bot_check_status.html", context)


def _run_live_test() -> dict[str, Any]:
    """Run a real extraction against the test video and report what happened."""
    try:
        info = inspect_video(TEST_VIDEO_URL)
        return {
            "ok": True,
            "bot_check": False,
            "detail": f"Extraction succeeded — “{info.get('title')}”",
        }
    except DownloadError as exc:
        if is_bot_check_error(str(exc)):
            return {"ok": False, "bot_check": True, "detail": BOT_CHECK_MESSAGE}
        return {"ok": False, "bot_check": False, "detail": clean_error(exc)}
    except Exception as exc:
        return {"ok": False, "bot_check": False, "detail": clean_error(exc)}
