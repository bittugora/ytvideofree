from django.contrib import admin
from django.urls import path

from .admin_views import bot_check_status

# Add the YouTube bot-check diagnostic page to the admin site at /admin/status/.
# It reuses the admin's authentication and URL namespace, so it appears under
# the admin login like every other admin page.
_admin_get_urls = admin.site.get_urls


def _admin_urls():
    urls = _admin_get_urls()
    urls.insert(0, path("status/", bot_check_status, name="bot-check-status"))
    return urls


admin.site.get_urls = _admin_urls
