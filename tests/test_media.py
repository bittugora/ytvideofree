import unittest
from unittest.mock import MagicMock, patch

from downloader.core.media import (
    InvalidYouTubeUrl,
    extract_video_id,
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


if __name__ == "__main__":
    unittest.main()
