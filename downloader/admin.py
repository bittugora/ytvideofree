from django.contrib import admin
from django.urls import path

from .admin_views import bot_check_status
from .models import ClientUsage, RateLimitConfig


@admin.register(RateLimitConfig)
class RateLimitConfigAdmin(admin.ModelAdmin):
    list_display = (
        "enabled",
        "max_concurrent_requests",
        "max_requests_per_window",
        "window_seconds",
        "max_downloads_per_day",
    )
    # No change-form link (the config is a singleton), so every setting is
    # edited inline on the list page instead of via a detail form.
    list_display_links = None
    list_editable = (
        "enabled",
        "max_concurrent_requests",
        "max_requests_per_window",
        "window_seconds",
        "max_downloads_per_day",
    )

    def has_delete_permission(self, request, obj=None):
        # Keep the singleton config from being accidentally deleted.
        return False


@admin.register(ClientUsage)
class ClientUsageAdmin(admin.ModelAdmin):
    list_display = (
        "key",
        "window_start",
        "window_count",
        "day",
        "links_downloaded",
        "day_downloads",
        "active_requests",
    )
    search_fields = ("key",)
    readonly_fields = (*list_display, "downloaded_links")
    actions = ["reset_usage"]

    @admin.display(description="Links today")
    def links_downloaded(self, obj):
        return len(obj.downloaded_links or [])

    @admin.action(description="Reset usage counters for selected clients")
    def reset_usage(self, request, queryset):
        updated = queryset.update(
            window_count=0, day_downloads=0, active_requests=0, downloaded_links=[]
        )
        self.message_user(request, f"Reset usage counters for {updated} client(s).")


# Add the YouTube bot-check diagnostic page to the admin site at /admin/status/.
# It reuses the admin's authentication and URL namespace, so it appears under
# the admin login like every other admin page.
_admin_get_urls = admin.site.get_urls


def _admin_urls():
    urls = _admin_get_urls()
    urls.insert(0, path("status/", bot_check_status, name="bot-check-status"))
    return urls


admin.site.get_urls = _admin_urls
