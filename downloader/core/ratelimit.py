"""Per-client rate limiting for the JSON API.

Limits are stored in the database (RateLimitConfig, editable from the admin)
and usage counters in ClientUsage. Clients are identified by IP address, or by
user id when a request is authenticated. No sign-up/sign-in is required: the
IP address is the user's identity.
"""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.http import HttpRequest, JsonResponse
from django.utils import timezone

from downloader.models import ClientUsage, RateLimitConfig


def get_config() -> RateLimitConfig:
    """Return the singleton config, creating it with defaults on first use."""
    config = RateLimitConfig.objects.first()
    if config is None:
        config = RateLimitConfig.objects.create()
    return config


def client_key(request: HttpRequest) -> str | None:
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return f"user:{user.pk}"
    ip = request.META.get("REMOTE_ADDR", "").strip()
    if not ip:
        return None
    return f"ip:{ip}"


def _rate_limit_error(message: str) -> JsonResponse:
    return JsonResponse({"detail": message}, status=429)


def enforce_rate_limit(
    request: HttpRequest,
) -> tuple[JsonResponse | None, bool]:
    """Check window and concurrency limits for this request.

    Returns (error_response, slot_acquired). When slot_acquired is True the
    caller must call release_concurrent_slot() when the request finishes.
    """
    config = get_config()
    key = client_key(request)
    if not config.enabled or key is None:
        return None, False

    now = timezone.now()
    try:
        with transaction.atomic():
            usage, _created = ClientUsage.objects.select_for_update().get_or_create(
                key=key,
                defaults={"window_start": now, "day": now.date()},
            )

            # Roll the window over once it has expired.
            if usage.window_start + timedelta(seconds=config.window_seconds) < now:
                usage.window_start = now
                usage.window_count = 0

            if usage.window_count >= config.max_requests_per_window:
                return (
                    _rate_limit_error(
                        "Too many requests from this device/IP. Please wait a moment and try again "
                        f"(limit: {config.max_requests_per_window} per {config.window_seconds}s)."
                    ),
                    False,
                )

            if usage.active_requests >= config.max_concurrent_requests:
                return (
                    _rate_limit_error(
                        "Another request is still in progress. Please wait for it to finish "
                        f"(limit: {config.max_concurrent_requests} request at a time)."
                    ),
                    False,
                )

            usage.window_count = F("window_count") + 1
            usage.active_requests = F("active_requests") + 1
            usage.save(
                update_fields=["window_start", "window_count", "active_requests"]
            )
    except Exception:
        # Never let rate-limit bookkeeping break the feature itself.
        return None, False

    return None, True


def enforce_daily_link_limit(request: HttpRequest, video_id: str) -> JsonResponse | None:
    """Check and record the per-client daily limit of distinct video links.

    The daily download limit counts *links*, not files: downloading the video,
    audio, and transcript of one link together is a single unit. Returns a 429
    JsonResponse when a NEW link would exceed the admin-configured limit, or
    None when the request may proceed. A link is recorded before the download
    starts, so it counts even if the download later fails.
    """
    config = get_config()
    key = client_key(request)
    if not config.enabled or key is None:
        return None

    now = timezone.now()
    try:
        with transaction.atomic():
            usage, _created = ClientUsage.objects.select_for_update().get_or_create(
                key=key,
                defaults={"window_start": now, "day": now.date()},
            )

            # Roll the daily counters over once the date changes.
            if usage.day != now.date():
                usage.day = now.date()
                usage.day_downloads = 0
                usage.downloaded_links = []

            if video_id in usage.downloaded_links:
                # This link was already counted today; re-downloading it is free.
                usage.save(update_fields=["day"])
                return None

            if usage.day_downloads >= config.max_downloads_per_day:
                return _rate_limit_error(
                    "Daily download limit reached for this device/IP "
                    f"({config.max_downloads_per_day} video links per day). "
                    "Try again tomorrow."
                )

            usage.day_downloads += 1
            usage.downloaded_links.append(video_id)
            usage.save(update_fields=["day", "day_downloads", "downloaded_links"])
    except Exception:
        # Never let rate-limit bookkeeping break the feature itself.
        return None

    return None


def release_concurrent_slot(request: HttpRequest) -> None:
    key = client_key(request)
    if key is None:
        return
    ClientUsage.objects.filter(key=key).update(active_requests=F("active_requests") - 1)
