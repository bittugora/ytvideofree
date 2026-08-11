from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    # The rest of the site is trailing-slash-free (APPEND_SLASH=False), so
    # redirect the common /admin URL to the admin's real location.
    path("admin", RedirectView.as_view(url="/admin/", permanent=True), name="admin-redirect"),
    path("admin/", admin.site.urls),
    path("blog/", include("blog.urls")),
    path("", include("downloader.urls")),
]

handler404 = "downloader.views.page_not_found"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
