import unittest
from unittest.mock import MagicMock, patch

from yt_dlp.utils import DownloadError

from downloader.core.media import (
    InvalidYouTubeUrl,
    _extract_info,
    _opts_with_fallback_clients,
    default_ydl_opts,
    extract_video_id,
    find_js_runtimes,
    inspect_video,
    serialize_info,
    validate_youtube_url,
)


class MediaTests(unittest.TestCase):
    def test_extract_video_id_from_supported_urls(self):
        cases = {
            "https://www.youtube.com/watch?v=psVUIguZAQg": "psVUIguZAQg",
            "https://youtu.be/psVUIguZAQg?si=test": "psVUIguZAQg",
            "https://www.youtube.com/shorts/psVUIguZAQg": "psVUIguZAQg",
            "https://www.youtube.com/embed/psVUIguZAQg": "psVUIguZAQg",
            "https://www.youtube.com/live/psVUIguZAQg": "psVUIguZAQg",
        }

        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(extract_video_id(url), expected)

    def test_validate_youtube_url_rejects_non_youtube_urls(self):
        with self.assertRaises(InvalidYouTubeUrl):
            validate_youtube_url("https://example.com/watch?v=psVUIguZAQg")

    def test_serialize_info_returns_expected_quality_choices(self):
        info = serialize_info(
            {
                "id": "psVUIguZAQg",
                "title": "Sample",
                "channel": "Channel",
                "duration": 125,
                "formats": [
                    {"height": 1080, "vcodec": "avc1"},
                    {"height": 720, "vcodec": "avc1"},
                    {"height": 144, "vcodec": "none"},
                ],
            }
        )

        self.assertEqual(info["duration_label"], "2:05")
        self.assertEqual(info["video_qualities"], ["best", "1080p", "720p"])

    def test_inspect_video_uses_yt_dlp_without_live_network(self):
        downloader = MagicMock()
        downloader.extract_info.return_value = {
            "id": "psVUIguZAQg",
            "title": "Sample",
            "channel": "Channel",
            "duration": 61,
            "formats": [],
        }

        with patch("downloader.core.media.YoutubeDL") as youtube_dl:
            youtube_dl.return_value.__enter__.return_value = downloader
            info = inspect_video("https://www.youtube.com/watch?v=psVUIguZAQg")

        self.assertEqual(info["id"], "psVUIguZAQg")
        downloader.extract_info.assert_called_once()

    def test_fallback_clients_option_overrides_player_client(self):
        opts = _opts_with_fallback_clients(default_ydl_opts())
        self.assertEqual(
            opts["extractor_args"]["youtube"]["player_client"],
            ["tv_downgraded", "android_vr"],
        )

    def test_extract_info_retries_with_fallback_clients_on_bot_check(self):
        bot_check = (
            "[youtube] sKNq4CqWkT4: Sign in to confirm you're not a bot. "
            "Use --cookies-from-browser or --cookies for the authentication."
        )

        first = MagicMock()
        first.extract_info.side_effect = DownloadError(bot_check)
        second = MagicMock()
        second.extract_info.return_value = {"id": "sKNq4CqWkT4", "title": "ok"}

        contexts = [first, second]

        def enter():
            return contexts.pop(0)

        with patch("downloader.core.media.YoutubeDL") as youtube_dl:
            youtube_dl.return_value.__enter__.side_effect = enter
            result = _extract_info(
                "https://www.youtube.com/watch?v=sKNq4CqWkT4",
                download=False,
                opts=default_ydl_opts(),
            )

        self.assertEqual(result["id"], "sKNq4CqWkT4")
        self.assertEqual(youtube_dl.call_count, 2)
        # The retry opts request the cookie-free fallback player clients.
        retry_opts = youtube_dl.call_args_list[1][0][0]
        self.assertEqual(
            retry_opts["extractor_args"]["youtube"]["player_client"],
            ["tv_downgraded", "android_vr"],
        )

    def test_extract_info_does_not_retry_for_other_errors(self):
        with patch("downloader.core.media.YoutubeDL") as youtube_dl:
            youtube_dl.return_value.__enter__.return_value.extract_info.side_effect = DownloadError(
                "Video unavailable"
            )
            with self.assertRaises(DownloadError):
                _extract_info(
                    "https://www.youtube.com/watch?v=psVUIguZAQg",
                    download=False,
                    opts=default_ydl_opts(),
                )

        self.assertEqual(youtube_dl.call_count, 1)

    def test_find_js_runtimes_returns_forced_set(self):
        with patch.dict(
            "os.environ",
            {"YTVIDEOFREE_JS_RUNTIMES": "node, bun"},
            clear=False,
        ):
            runtimes = find_js_runtimes()
        self.assertEqual(sorted(runtimes), ["bun", "node"])

    def test_find_js_runtimes_prefers_configured_location(self):
        with patch("downloader.core.media.shutil.which", return_value=None), patch.dict(
            "os.environ",
            {"YTVIDEOFREE_NODE_LOCATION": "/usr/bin/node"},
            clear=False,
        ), patch("downloader.core.media.Path.exists", return_value=True):
            runtimes = find_js_runtimes()
        self.assertEqual(runtimes, {"node": {"path": "/usr/bin/node"}})


if __name__ == "__main__":
    unittest.main()
