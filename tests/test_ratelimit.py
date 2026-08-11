import json
from unittest.mock import patch

from django.test import TestCase

from downloader.models import ClientUsage, RateLimitConfig


class RateLimitTests(TestCase):
    def setUp(self):
        # Known config: 2 requests per window, 1 at a time, 1 link per day.
        RateLimitConfig.objects.create(
            enabled=True,
            max_concurrent_requests=1,
            max_requests_per_window=2,
            window_seconds=60,
            max_downloads_per_day=1,
        )

    def post_inspect(self):
        # Invalid payload returns 422 but still counts as a request.
        return self.client.post(
            "/api/inspect",
            data=json.dumps({"url": "short"}),
            content_type="application/json",
        )

    def download(self, video_id):
        with patch("downloader.views.download_media", side_effect=ValueError("conversion failed")):
            return self.client.post(
                "/api/download",
                data=json.dumps(
                    {"url": f"https://www.youtube.com/watch?v={video_id}", "mode": "video"}
                ),
                content_type="application/json",
            )

    def test_window_limit_returns_429(self):
        self.assertEqual(self.post_inspect().status_code, 422)
        self.assertEqual(self.post_inspect().status_code, 422)
        response = self.post_inspect()
        self.assertEqual(response.status_code, 429)
        self.assertIn("Too many requests", response.json()["detail"])

    def test_concurrent_requests_are_blocked(self):
        ClientUsage.objects.create(key="ip:127.0.0.1", active_requests=1)
        response = self.post_inspect()
        self.assertEqual(response.status_code, 429)
        self.assertIn("in progress", response.json()["detail"])

    def test_concurrency_slot_released_after_request(self):
        self.post_inspect()
        usage = ClientUsage.objects.get(key="ip:127.0.0.1")
        self.assertEqual(usage.active_requests, 0)

    def test_daily_download_limit_counts_distinct_links(self):
        # First new link is allowed (download fails later, but the link counts).
        self.assertEqual(self.download("psVUIguZAQg").status_code, 422)

        # A second, different link exceeds the 1-link/day limit.
        response = self.download("dQw4w9WgXcQ")
        self.assertEqual(response.status_code, 429)
        self.assertIn("Daily download limit", response.json()["detail"])

    def test_redownloading_an_already_counted_link_is_free(self):
        self.assertEqual(self.download("psVUIguZAQg").status_code, 422)
        # Re-downloading the same link does not consume another unit.
        self.assertEqual(self.download("psVUIguZAQg").status_code, 422)

        usage = ClientUsage.objects.get(key="ip:127.0.0.1")
        self.assertEqual(usage.day_downloads, 1)
        self.assertEqual(usage.downloaded_links, ["psVUIguZAQg"])

    def test_daily_limit_rolls_over_for_a_new_link_only(self):
        self.assertEqual(self.download("psVUIguZAQg").status_code, 422)
        usage = ClientUsage.objects.get(key="ip:127.0.0.1")
        usage.day_downloads = 0
        usage.downloaded_links = []
        usage.save()

        # Limit is reset; the same link can be counted again.
        self.assertEqual(self.download("psVUIguZAQg").status_code, 422)
        self.assertEqual(
            ClientUsage.objects.get(key="ip:127.0.0.1").downloaded_links,
            ["psVUIguZAQg"],
        )

    def test_disabled_config_bypasses_limits(self):
        RateLimitConfig.objects.update(enabled=False)
        self.assertEqual(self.post_inspect().status_code, 422)
        self.assertEqual(self.post_inspect().status_code, 422)
        self.assertEqual(self.post_inspect().status_code, 422)
