import json
import os
import tempfile
from unittest.mock import patch

from django.test import TestCase


class RouteTests(TestCase):
    def test_healthz(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_home_page_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ytvideofree")
        self.assertContains(response, 'id="paste-button"')
        self.assertContains(response, 'id="install-banner"')
        self.assertContains(response, 'id="theme-toggle"')
        self.assertContains(response, 'id="download-thumbnail"')
        self.assertContains(response, 'property="og:image"')

    def test_blog_feed_renders_published_posts(self):
        from django.contrib.auth import get_user_model
        from django.utils import timezone

        from blog.models import Post

        user = get_user_model().objects.create_user(username="feedauth", password="pass")
        Post.objects.create(
            title="Feed me",
            slug="feed-me",
            author=user,
            body="RSS body.",
            publish=timezone.now(),
            status=Post.Status.PUBLISHED,
        )

        response = self.client.get("/blog/feed/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/rss+xml; charset=utf-8")
        self.assertContains(response, "Feed me")
        self.assertContains(response, "RSS body.")

    def test_robots_txt(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain")
        self.assertIn("Sitemap:", response.content.decode())

    def test_sitemap_xml_lists_pages(self):
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml")
        self.assertIn("/blog/", response.content.decode())

    def test_admin_redirects_without_trailing_slash(self):
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "/admin/")

    def test_admin_login_renders(self):
        response = self.client.get("/admin/login/")
        self.assertEqual(response.status_code, 200)

    def test_admin_bot_check_status_page_requires_staff(self):
        # Anonymous users are redirected to the admin login.
        response = self.client.get("/admin/status/")
        self.assertIn(response.status_code, (301, 302))
        self.assertIn("/admin/login/", response["Location"])

    def test_admin_bot_check_status_page_renders_for_staff(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_superuser(
            username="statuscheck", email="", password="pass"
        )
        self.client.force_login(user)

        # Keep the page hermetic: no real runtime probes or Node downloads.
        with patch("downloader.admin_views.find_js_runtimes", return_value={}), patch(
            "downloader.admin_views.discover_runtime_binaries", return_value={}
        ), patch("downloader.admin_views.ensure_js_runtime", return_value=None):
            response = self.client.get("/admin/status/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "YouTube bot-check status")
        self.assertContains(response, "YTVIDEOFREE_COOKIES_FILE")
        self.assertContains(response, "Run live bot-check test")

    def test_admin_bot_check_status_page_warns_when_runtime_too_old(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_superuser(
            username="statuscheck2", email="", password="pass"
        )
        self.client.force_login(user)

        with patch("downloader.admin_views.find_js_runtimes", return_value={}), patch(
            "downloader.admin_views.discover_runtime_binaries",
            return_value={
                "node": {
                    "path": "/usr/bin/node",
                    "version": "18.19.1",
                    "supported": False,
                }
            },
        ), patch("downloader.admin_views.ensure_js_runtime", return_value=None):
            response = self.client.get("/admin/status/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "18.19.1")
        self.assertContains(response, "too old")

    def test_admin_bot_check_status_page_shows_cookie_report(self):
        from django.contrib.auth import get_user_model

        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        tmp.write(
            "# Netscape HTTP Cookie File\n"
            ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tfake\n"
            ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tSAPISID\tfake\n"
            ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tLOGIN_INFO\tfake\n"
        )
        tmp.close()

        user = get_user_model().objects.create_superuser(
            username="cookiestatus", email="", password="pass"
        )
        self.client.force_login(user)
        try:
            with patch.dict(
                "os.environ", {"YTVIDEOFREE_COOKIES_FILE": tmp.name}, clear=False
            ), patch("downloader.admin_views.find_js_runtimes", return_value={}), patch(
                "downloader.admin_views.discover_runtime_binaries", return_value={}
            ), patch("downloader.admin_views.ensure_js_runtime", return_value=None):
                response = self.client.get("/admin/status/")
        finally:
            os.unlink(tmp.name)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "signed-in session")

    def test_admin_bot_check_status_live_test_reports_success(self):
        from unittest.mock import call

        from django.contrib.auth import get_user_model

        from downloader.admin_views import TEST_VIDEO_URL

        user = get_user_model().objects.create_superuser(
            username="statustest", email="", password="pass"
        )
        self.client.force_login(user)

        with patch(
            "downloader.admin_views.inspect_video",
            return_value={"title": "youtube-dl test video"},
        ) as mock_inspect:
            response = self.client.post("/admin/status/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ok"], True)
        self.assertEqual(response.json()["bot_check"], False)
        self.assertIn("Extraction succeeded", response.json()["detail"])
        # The live test really targets the known-good URL.
        self.assertIn(call(TEST_VIDEO_URL), mock_inspect.mock_calls)

    def test_rate_limit_config_is_editable_from_admin(self):
        from django.contrib.auth import get_user_model

        from downloader.models import RateLimitConfig

        if not RateLimitConfig.objects.exists():
            RateLimitConfig.objects.create()

        user = get_user_model().objects.create_superuser(
            username="admincheck", email="", password="pass"
        )
        self.client.force_login(user)
        response = self.client.get("/admin/downloader/ratelimitconfig/")

        self.assertEqual(response.status_code, 200)
        # Every admin-configurable setting is editable inline on the list page
        # (Django names inline fields form-0-<field>).
        for field in (
            "enabled",
            "max_concurrent_requests",
            "max_requests_per_window",
            "window_seconds",
            "max_downloads_per_day",
        ):
            self.assertContains(response, f'name="form-0-{field}"')

    def test_amp_page_renders(self):
        response = self.client.get("/amp")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "amp-boilerplate")
        self.assertContains(response, "canonical")

    def test_service_worker_served_at_root_scope(self):
        response = self.client.get("/sw.js")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/javascript")
        self.assertEqual(response["Service-Worker-Allowed"], "/")

    def test_blog_list_and_detail_render(self):
        from django.contrib.auth import get_user_model
        from django.utils import timezone

        from blog.models import Post, Tag

        user = get_user_model().objects.create_user(username="author", password="pass")
        post = Post.objects.create(
            title="Hello world",
            slug="hello-world",
            author=user,
            body="First post.",
            publish=timezone.now(),
            status=Post.Status.PUBLISHED,
        )
        post.tags.set([Tag.objects.create(name="transcript")])

        list_response = self.client.get("/blog/")
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Hello world")

        detail_response = self.client.get(f"/blog/post/{post.slug}/")
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "First post.")

        tag_response = self.client.get("/blog/tag/transcript/")
        self.assertEqual(tag_response.status_code, 200)
        self.assertContains(tag_response, "Hello world")

        empty_tag_response = self.client.get("/blog/tag/nonexistent/")
        self.assertEqual(empty_tag_response.status_code, 200)
        self.assertContains(empty_tag_response, "No blog posts yet")

    def test_site_pages_render(self):
        for path in ("/docs", "/terms", "/privacy", "/copyright"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "ytvideofree")

    def test_unknown_page_renders_404_template(self):
        response = self.client.get("/no-such-page")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page not found", status_code=404)

    def test_api_inspect_rejects_invalid_url(self):
        response = self.client.post(
            "/api/inspect",
            data=json.dumps({"url": "https://example.com/watch?v=psVUIguZAQg"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())

    def test_api_inspect_returns_friendly_message_for_bot_check(self):
        from yt_dlp.utils import DownloadError

        from downloader.errors import BOT_CHECK_MESSAGE

        bot_check = (
            "[youtube] sKNq4CqWkT4: Sign in to confirm you're not a bot. "
            "Use --cookies-from-browser or --cookies for the authentication. "
            "See https://github.com/yt-dlp/yt-dlp/wiki/FAQ for details."
        )

        with patch(
            "downloader.views.inspect_video",
            side_effect=DownloadError(bot_check),
        ):
            response = self.client.post(
                "/api/inspect",
                data=json.dumps({"url": "https://www.youtube.com/watch?v=sKNq4CqWkT4"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], BOT_CHECK_MESSAGE)
        self.assertNotIn("cookies-from-browser", response.json()["detail"])

    def test_api_inspect_rejects_invalid_payload(self):
        response = self.client.post(
            "/api/inspect",
            data=json.dumps({"url": "short"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 422)

    def test_api_thumbnail_returns_jpeg_attachment(self):
        with patch("downloader.views.fetch_thumbnail", return_value=(b"\xff\xd8\xff\xe0jpeg", "image/jpeg")):
            response = self.client.post(
                "/api/thumbnail",
                data=json.dumps({"url": "https://www.youtube.com/watch?v=psVUIguZAQg"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("psVUIguZAQg-thumbnail.jpg", response["Content-Disposition"])
        self.assertEqual(response.content, b"\xff\xd8\xff\xe0jpeg")

    def test_api_thumbnail_rejects_invalid_url(self):
        response = self.client.post(
            "/api/thumbnail",
            data=json.dumps({"url": "https://example.com/watch?v=psVUIguZAQg"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_api_download_maps_media_errors_for_video_and_audio(self):
        for mode in ("video", "audio"):
            with self.subTest(mode=mode):
                with patch("downloader.views.download_media", side_effect=ValueError("conversion failed")):
                    response = self.client.post(
                        "/api/download",
                        data=json.dumps(
                            {
                                "url": "https://www.youtube.com/watch?v=psVUIguZAQg",
                                "mode": mode,
                            }
                        ),
                        content_type="application/json",
                    )

                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["detail"], "conversion failed")

    def test_api_download_rejects_bad_mode(self):
        response = self.client.post(
            "/api/download",
            data=json.dumps(
                {
                    "url": "https://www.youtube.com/watch?v=psVUIguZAQg",
                    "mode": "gif",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 422)

    def test_api_transcript_returns_service_payload(self):
        expected = {"text": "hello", "srt": "1\nhello", "segments": []}

        with patch("downloader.views.require_video_id", return_value="psVUIguZAQg"), patch(
            "downloader.views.get_transcript", return_value=expected
        ):
            response = self.client.post(
                "/api/transcript",
                data=json.dumps({"url": "https://www.youtube.com/watch?v=psVUIguZAQg"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)

    def test_thumbnail_button_is_present(self):
        response = self.client.get("/")
        self.assertContains(response, "Download Thumbnail")


class PerLinkDailyLimitTests(TestCase):
    """The daily download limit counts links, not files: video, audio, and
    transcript downloads for one link consume a single unit."""

    def setUp(self):
        from downloader.models import RateLimitConfig

        RateLimitConfig.objects.create(
            enabled=True,
            max_concurrent_requests=1,
            max_requests_per_window=100,
            window_seconds=60,
            max_downloads_per_day=1,
        )

    def test_video_and_transcript_for_one_link_counts_once(self):
        from downloader.models import ClientUsage

        # Video download for link A (fails after counting the link).
        with patch("downloader.views.download_media", side_effect=ValueError("conversion failed")):
            response = self.client.post(
                "/api/download",
                data=json.dumps(
                    {"url": "https://www.youtube.com/watch?v=psVUIguZAQg", "mode": "video"}
                ),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 422)

        # Transcript download for the SAME link is still allowed.
        with patch("downloader.views.require_video_id", return_value="psVUIguZAQg"), patch(
            "downloader.views.get_transcript",
            return_value={"text": "hello", "srt": "1\nhello", "language_code": "en"},
        ):
            response = self.client.post(
                "/api/transcript/download",
                data=json.dumps({"url": "https://www.youtube.com/watch?v=psVUIguZAQg", "format": "txt"}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)

        usage = ClientUsage.objects.get(key="ip:127.0.0.1")
        self.assertEqual(usage.day_downloads, 1)
        self.assertEqual(usage.downloaded_links, ["psVUIguZAQg"])

    def test_new_link_is_blocked_after_daily_limit(self):
        with patch("downloader.views.download_media", side_effect=ValueError("conversion failed")):
            response = self.client.post(
                "/api/download",
                data=json.dumps(
                    {"url": "https://www.youtube.com/watch?v=psVUIguZAQg", "mode": "video"}
                ),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 422)

        with patch("downloader.views.download_media", side_effect=ValueError("conversion failed")):
            response = self.client.post(
                "/api/download",
                data=json.dumps(
                    {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "mode": "video"}
                ),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 429)
        self.assertIn("Daily download limit", response.json()["detail"])

    def test_api_transcript_download_returns_txt_attachment_named_after_title(self):
        with patch("downloader.views.require_video_id", return_value="psVUIguZAQg"), patch(
            "downloader.views.get_transcript",
            return_value={"text": "hello world", "srt": "1\nhello world", "language_code": "en"},
        ):
            response = self.client.post(
                "/api/transcript/download",
                data=json.dumps(
                    {
                        "url": "https://www.youtube.com/watch?v=psVUIguZAQg",
                        "format": "txt",
                        "title": "My Awesome Video",
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("My Awesome Video.txt", response["Content-Disposition"])
        self.assertEqual(response.content.decode(), "hello world")
