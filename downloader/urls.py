from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("amp", views.amp_page, name="amp"),
    path("healthz", views.healthz, name="healthz"),
    path("sw.js", views.service_worker, name="service-worker"),
    path("robots.txt", views.robots_txt, name="robots"),
    path("sitemap.xml", views.sitemap_xml, name="sitemap"),
    path("docs", views.docs_page, name="docs"),
    path("terms", views.terms_page, name="terms"),
    path("privacy", views.privacy_page, name="privacy"),
    path("copyright", views.copyright_page, name="copyright"),
    path("api/inspect", views.api_inspect, name="api-inspect"),
    path("api/download", views.api_download, name="api-download"),
    path("api/thumbnail", views.api_thumbnail, name="api-thumbnail"),
    path("api/transcript", views.api_transcript, name="api-transcript"),
    path("api/transcript/download", views.api_transcript_download, name="api-transcript-download"),
]
