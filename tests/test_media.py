import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from yt_dlp.utils import DownloadError

from downloader.core.media import (
    InvalidYouTubeUrl,
    _extract_info,
    _opts_with_player_clients,
    default_ydl_opts,
    extract_video_id,
    find_js_runtimes,
    inspect_video,
    player_client_groups,
    serialize_info,
    validate_youtube_url,
)


class MediaTests(unittest.TestCase):
    def setUp(self):
        # Probe results are cached module-wide; keep tests independent.
        from downloader.core.media import _runtime_probe_cache

        _runtime_probe_cache.clear()

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

    def test_player_clients_option_overrides_player_client(self):
        opts = _opts_with_player_clients(default_ydl_opts(), ("tv", "web_safari"))
        self.assertEqual(
            opts["extractor_args"]["youtube"]["player_client"],
            ["tv", "web_safari"],
        )

    def test_default_player_client_groups_lead_with_tv(self):
        groups = player_client_groups()
        self.assertEqual(groups[0], ("tv", "web_safari"))

    def test_extract_info_retries_with_next_client_group_on_bot_check(self):
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
        # The retry opts request the next cookie-free player-client group.
        retry_opts = youtube_dl.call_args_list[1][0][0]
        self.assertEqual(
            retry_opts["extractor_args"]["youtube"]["player_client"],
            ["ios", "android"],
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
        ), patch(
            "downloader.core.media._resolve_runtime_binary",
            side_effect=["/usr/bin/node", "/usr/bin/bun"],
        ), patch("downloader.core.media._runtime_is_supported", return_value=True):
            runtimes = find_js_runtimes()
        self.assertEqual(sorted(runtimes), ["bun", "node"])
        self.assertEqual(runtimes["node"], {"path": "/usr/bin/node"})

    def test_find_js_runtimes_prefers_configured_location(self):
        with patch("downloader.core.media.shutil.which", return_value=None), patch.dict(
            "os.environ",
            {"YTVIDEOFREE_NODE_LOCATION": "/usr/bin/node"},
            clear=False,
        ), patch("downloader.core.media.Path.exists", return_value=True), patch(
            "downloader.core.media._runtime_is_supported", return_value=True
        ):
            runtimes = find_js_runtimes()
        self.assertEqual(runtimes, {"node": {"path": "/usr/bin/node"}})

    def test_find_js_runtimes_replaces_too_old_node_with_bundled(self):
        # The VPS case: Node 18 is installed (yt-dlp silently ignores < 22), so
        # the bundled Node 22 must be downloaded and used instead.
        bundled = Path("/opt/ytvideofree/.cache/runtimes/node-v22.14.0/bin/node")

        def fake_supported(name, binary):
            if name == "node" and binary == "/usr/bin/node":
                return False
            if name == "node" and binary == str(bundled):
                return True
            return False

        with patch(
            "downloader.core.media._resolve_runtime_binary",
            side_effect=[None, "/usr/bin/node", None, None],
        ), patch(
            "downloader.core.media._runtime_is_supported", side_effect=fake_supported
        ), patch("downloader.core.media.ensure_js_runtime", return_value=bundled) as ensure:
            runtimes = find_js_runtimes()

        self.assertEqual(runtimes, {"node": {"path": str(bundled)}})
        ensure.assert_called_once()

    def test_find_js_runtimes_returns_empty_when_nothing_usable(self):
        with patch("downloader.core.media._resolve_runtime_binary", return_value=None), patch(
            "downloader.core.media.ensure_js_runtime", return_value=None
        ):
            runtimes = find_js_runtimes()
        self.assertEqual(runtimes, {})

    def test_parse_runtime_version(self):
        from downloader.core.media import _parse_runtime_version

        self.assertEqual(_parse_runtime_version("node", "v18.19.1"), (18, 19, 1))
        self.assertEqual(_parse_runtime_version("node", "v24.18.0"), (24, 18, 0))
        self.assertEqual(_parse_runtime_version("bun", "1.2.11"), (1, 2, 11))
        self.assertEqual(_parse_runtime_version("deno", "deno 2.3.0"), (2, 3, 0))
        self.assertEqual(
            _parse_runtime_version("quickjs", "QuickJS-ng version 2024-01-13"),
            (2024, 1, 13),
        )
        self.assertIsNone(_parse_runtime_version("node", "garbage output"))

    def test_runtime_probe_fallback_rejects_old_node(self):
        from downloader.core.media import _runtime_probe

        # Force the fallback table (yt-dlp's own probe is made unavailable) and
        # simulate a Node 18 binary: 18 < 22, so it must be rejected.
        with patch(
            "downloader.core.media._runtime_version_from_binary", return_value=(18, 19, 1)
        ), patch("yt_dlp.globals.supported_js_runtimes", MagicMock(value={})):
            version, supported = _runtime_probe("node", "/usr/bin/node")
        self.assertFalse(supported)
        self.assertEqual(version, "18.19.1")

    def test_runtime_probe_fallback_accepts_new_node(self):
        from downloader.core.media import _runtime_probe

        with patch(
            "downloader.core.media._runtime_version_from_binary", return_value=(24, 18, 0)
        ), patch("yt_dlp.globals.supported_js_runtimes", MagicMock(value={})):
            version, supported = _runtime_probe("node", "/usr/bin/node")
        self.assertTrue(supported)
        self.assertEqual(version, "24.18.0")

    def test_node_asset_uses_single_v_prefix(self):
        from downloader.core.media import NODE_VERSION, _node_asset

        basename, _ = _node_asset()
        self.assertIsNotNone(basename)
        # Regression: NODE_VERSION already has a leading "v", so the archive
        # name must not become node-vv22.14.0-... (which 404s on nodejs.org).
        self.assertFalse(basename.startswith("node-vv"))
        self.assertTrue(basename.startswith(f"node-v{NODE_VERSION.lstrip('v')}"))

    def test_discover_runtime_binaries_reports_unsupported_too(self):
        from downloader.core.media import discover_runtime_binaries

        with patch(
            "downloader.core.media._resolve_runtime_binary",
            side_effect=[None, "/usr/bin/node", None, None],
        ), patch("downloader.core.media._runtime_probe", return_value=("18.19.1", False)):
            details = discover_runtime_binaries()
        self.assertEqual(
            details,
            {"node": {"path": "/usr/bin/node", "version": "18.19.1", "supported": False}},
        )


if __name__ == "__main__":
    unittest.main()
