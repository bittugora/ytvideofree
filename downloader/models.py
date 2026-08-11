from django.db import models


class RateLimitConfig(models.Model):
    """Admin-editable rate limiting settings (treated as a singleton)."""

    enabled = models.BooleanField(
        default=True,
        help_text="Turn rate limiting on or off for the whole site.",
    )
    max_concurrent_requests = models.PositiveIntegerField(
        default=1,
        help_text="How many API requests one client (IP) may run at the same time.",
    )
    max_requests_per_window = models.PositiveIntegerField(
        default=10,
        help_text="Maximum API requests per client within the window below.",
    )
    window_seconds = models.PositiveIntegerField(
        default=60,
        help_text="Length of the request window in seconds.",
    )
    max_downloads_per_day = models.PositiveIntegerField(
        default=20,
        help_text=(
            "Maximum distinct video links a client may download per day. "
            "Downloading video, audio, and transcript for one link counts once."
        ),
    )

    class Meta:
        verbose_name = "Rate limit configuration"
        verbose_name_plural = "Rate limit configuration"

    def __str__(self) -> str:
        return f"Rate limit config (enabled={self.enabled})"


class ClientUsage(models.Model):
    """Rolling usage counters per client (IP or logged-in user)."""

    key = models.CharField(max_length=100, unique=True)
    window_start = models.DateTimeField(auto_now_add=True)
    window_count = models.PositiveIntegerField(default=0)
    day = models.DateField(auto_now_add=True)
    day_downloads = models.PositiveIntegerField(default=0)
    downloaded_links = models.JSONField(
        default=list,
        blank=True,
        help_text="Video IDs downloaded today by this client (one entry per link).",
    )
    active_requests = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Client usage"
        verbose_name_plural = "Client usage"

    def __str__(self) -> str:
        return self.key
