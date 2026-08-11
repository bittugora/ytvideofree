from __future__ import annotations

import json
from functools import wraps
from pathlib import Path
from typing import Any

from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from yt_dlp.utils import DownloadError

from .core.media import (
    InvalidYouTubeUrl,
    cleanup_directory,
    download_media,
    extract_video_id,
    fetch_thumbnail,
    inspect_video,
    media_type_for,
    safe_download_name,
    validate_youtube_url,
)
from .core.ratelimit import (
    enforce_daily_link_limit,
    enforce_rate_limit,
    release_concurrent_slot,
)
from .core.transcripts import DEFAULT_LANGUAGES, get_transcript
from .errors import clean_error
from .site_pages import SITE_PAGES


class PayloadError(ValueError):
    """Raised when a JSON request body fails schema validation."""


def parse_json_body(request: HttpRequest) -> dict[str, Any]:
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PayloadError("Request body must be valid JSON.") from exc
    if not isinstance(payload, dict):
        raise PayloadError("Request body must be a JSON object.")
    return payload


def require_url(payload: dict[str, Any]) -> str:
    url = payload.get("url")
    if not isinstance(url, str) or not (8 <= len(url) <= 500):
        raise PayloadError("url must be a string of 8 to 500 characters.")
    return url


def parse_download_options(payload: dict[str, Any]) -> tuple[str, str, str]:
    mode = payload.get("mode")
    if mode not in ("video", "audio"):
        raise PayloadError("mode must be either 'video' or 'audio'.")

    quality = payload.get("quality", "best")
    if quality not in ("best", "2160p", "1440p", "1080p", "720p", "480p", "360p"):
        raise PayloadError("quality must be best, 2160p, 1440p, 1080p, 720p, 480p, or 360p.")

    audio_quality = payload.get("audio_quality", "192")
    if audio_quality not in ("128", "192", "256", "320"):
        raise PayloadError("audio_quality must be 128, 192, 256, or 320.")

    return mode, quality, audio_quality


def parse_transcript_options(payload: dict[str, Any]) -> tuple[list[str], str | None, str]:
    languages = payload.get("languages", DEFAULT_LANGUAGES)
    if not isinstance(languages, list) or not all(isinstance(lang, str) for lang in languages):
        raise PayloadError("languages must be a list of language codes.")

    translate_to = payload.get("translate_to")
    if translate_to is not None and (not isinstance(translate_to, str) or len(translate_to) > 12):
        raise PayloadError("translate_to must be a short language code or null.")

    fmt = payload.get("format", "txt")
    if fmt not in ("txt", "srt"):
        raise PayloadError("format must be 'txt' or 'srt'.")

    return languages, translate_to, fmt


def require_video_id(url: str) -> str:
    clean_url = validate_youtube_url(url)
    video_id = extract_video_id(clean_url)
    if not video_id:
        raise InvalidYouTubeUrl("The YouTube link did not include a valid video ID.")
    return video_id


def http_json_error(status: int, detail: str) -> JsonResponse:
    return JsonResponse({"detail": detail}, status=status)


def rate_limited():
    """Enforce per-client window/concurrency limits, releasing the slot after.

    The daily per-link download limit is enforced separately by
    enforce_daily_link_limit() inside the download views, once the video ID is
    known.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            error_response, acquired = enforce_rate_limit(request)
            if error_response is not None:
                return error_response
            try:
                return view_func(request, *args, **kwargs)
            finally:
                if acquired:
                    release_concurrent_slot(request)

        return wrapper

    return decorator


# --- Page routes -----------------------------------------------------------


def home(request: HttpRequest) -> HttpResponse:
    return render(request, "index.html", {"app_name": "ytvideofree"})


def amp_page(request: HttpRequest) -> HttpResponse:
    return render(request, "amp.html")


def healthz(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


def service_worker(request: HttpRequest) -> HttpResponse:
    """Serve the PWA service worker from the site root so it controls the whole app."""
    sw_path = Path(__file__).resolve().parent.parent / "static" / "sw.js"
    response = HttpResponse(sw_path.read_text(encoding="utf-8"), content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


def docs_page(request: HttpRequest) -> HttpResponse:
    return render_site_page(request, "docs")


def terms_page(request: HttpRequest) -> HttpResponse:
    return render_site_page(request, "terms")


def privacy_page(request: HttpRequest) -> HttpResponse:
    return render_site_page(request, "privacy")


def copyright_page(request: HttpRequest) -> HttpResponse:
    return render_site_page(request, "copyright")


def render_site_page(request: HttpRequest, slug: str) -> HttpResponse:
    return render(request, "page.html", {"page": SITE_PAGES[slug]})


def page_not_found(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return render(
        request,
        "page.html",
        {
            "page": {
                "title": "Page not found",
                "intro": "The link you followed does not lead to a page on this site.",
                "sections": [
                    {
                        "heading": "Go back",
                        "body": 'Return to the <a href="/">home page</a> to use the download tool.',
                    }
                ],
            }
        },
        status=404,
    )


# --- JSON API routes -------------------------------------------------------


@csrf_exempt
@require_POST
@rate_limited()
def api_inspect(request: HttpRequest) -> JsonResponse:
    try:
        payload = parse_json_body(request)
        return JsonResponse(inspect_video(require_url(payload)))
    except PayloadError as exc:
        return http_json_error(422, str(exc))
    except InvalidYouTubeUrl as exc:
        return http_json_error(400, str(exc))
    except DownloadError as exc:
        return http_json_error(422, clean_error(exc))


@csrf_exempt
@require_POST
@rate_limited()
def api_download(request: HttpRequest) -> HttpResponse:
    try:
        payload = parse_json_body(request)
        url = require_url(payload)
        mode, quality, audio_quality = parse_download_options(payload)
        video_id = require_video_id(url)
        daily_error = enforce_daily_link_limit(request, video_id)
        if daily_error is not None:
            return daily_error
        media_file = download_media(
            url,
            mode=mode,
            quality=quality,
            audio_quality=audio_quality,
        )
    except PayloadError as exc:
        return http_json_error(422, str(exc))
    except InvalidYouTubeUrl as exc:
        return http_json_error(400, str(exc))
    except (DownloadError, FileNotFoundError, ValueError) as exc:
        return http_json_error(422, clean_error(exc))

    return CleanupFileResponse(
        open(media_file, "rb"),
        filename=media_file.name,
        content_type=media_type_for(media_file),
        directory_to_cleanup=media_file.parent,
    )


@csrf_exempt
@require_POST
@rate_limited()
def api_transcript(request: HttpRequest) -> JsonResponse:
    try:
        payload = parse_json_body(request)
        video_id = require_video_id(require_url(payload))
        languages, translate_to, _fmt = parse_transcript_options(payload)
        return JsonResponse(
            get_transcript(video_id, languages=languages, translate_to=translate_to)
        )
    except PayloadError as exc:
        return http_json_error(422, str(exc))
    except InvalidYouTubeUrl as exc:
        return http_json_error(400, str(exc))
    except Exception as exc:
        return http_json_error(422, clean_error(exc))


@csrf_exempt
@require_POST
@rate_limited()
def api_thumbnail(request: HttpRequest) -> HttpResponse:
    try:
        payload = parse_json_body(request)
        video_id = require_video_id(require_url(payload))
        image_bytes, content_type = fetch_thumbnail(video_id)
    except PayloadError as exc:
        return http_json_error(422, str(exc))
    except InvalidYouTubeUrl as exc:
        return http_json_error(400, str(exc))
    except Exception as exc:
        return http_json_error(422, clean_error(exc))

    filename = f"{video_id}-thumbnail.jpg"
    response = HttpResponse(image_bytes, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@csrf_exempt
@require_POST
@rate_limited()
def api_transcript_download(request: HttpRequest) -> HttpResponse:
    try:
        payload = parse_json_body(request)
        video_id = require_video_id(require_url(payload))
        daily_error = enforce_daily_link_limit(request, video_id)
        if daily_error is not None:
            return daily_error
        languages, translate_to, fmt = parse_transcript_options(payload)
        transcript = get_transcript(video_id, languages=languages, translate_to=translate_to)
        title = payload.get("title")
        if title is not None and (not isinstance(title, str) or len(title) > 300):
            raise PayloadError("title must be a short string.")
    except PayloadError as exc:
        return http_json_error(422, str(exc))
    except InvalidYouTubeUrl as exc:
        return http_json_error(400, str(exc))
    except Exception as exc:
        return http_json_error(422, clean_error(exc))

    body = transcript["srt"] if fmt == "srt" else transcript["text"]
    extension = "srt" if fmt == "srt" else "txt"
    media_type = "application/x-subrip" if fmt == "srt" else "text/plain; charset=utf-8"
    base_name = (title or "").strip() or f"{video_id}-{transcript['language_code']}"
    filename = safe_download_name(base_name, extension)

    response = HttpResponse(body, content_type=media_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# --- Site metadata routes --------------------------------------------------


def robots_txt(request: HttpRequest) -> HttpResponse:
    sitemap_url = request.build_absolute_uri("/sitemap.xml")
    body = f"User-agent: *\nAllow: /\n\nSitemap: {sitemap_url}\n"
    return HttpResponse(body, content_type="text/plain")


def sitemap_xml(request: HttpRequest) -> HttpResponse:
    from blog.models import Post

    paths = ["/", "/blog/", "/docs", "/terms", "/privacy", "/copyright"]
    urls = [request.build_absolute_uri(path) for path in paths]
    urls.extend(
        request.build_absolute_uri(post.get_absolute_url()) for post in Post.published.all()
    )

    from xml.sax.saxutils import escape

    items = "\n".join(f"  <url><loc>{escape(url)}</loc></url>" for url in urls)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{items}\n"
        "</urlset>\n"
    )
    return HttpResponse(xml, content_type="application/xml")


class CleanupFileResponse(FileResponse):
    """FileResponse that removes the temporary download directory when done.

    Mirrors the original app's FastAPI background task: temporary media files
    are deleted after the response is sent.
    """

    def __init__(self, *args: Any, directory_to_cleanup: Path | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._directory_to_cleanup = directory_to_cleanup

    def close(self) -> None:
        super().close()
        if self._directory_to_cleanup is not None:
            cleanup_directory(self._directory_to_cleanup)
