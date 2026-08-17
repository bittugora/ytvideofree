import os
import unittest
from unittest.mock import MagicMock, patch

from yt_dlp.utils import DownloadError

import ytdl


class CliTests(unittest.TestCase):
    def test_get_video_info_retries_with_fallback_clients_on_bot_check(self):
        bot_check = (
            "[youtube] JQJgxx38S30: Sign in to confirm you're not a bot. "
            "Use --cookies-from-browser or --cookies for the authentication."
        )

        first = MagicMock()
        first.extract_info.side_effect = DownloadError(bot_check)
        second = MagicMock()
        second.extract_info.return_value = {"id": "JQJgxx38S30", "title": "ok"}

        contexts = [first, second]

        def enter():
            return contexts.pop(0)

        with patch("ytdl.YoutubeDL") as youtube_dl, patch(
            "sys.stdout", new_callable=MagicMock
        ):
            youtube_dl.return_value.__enter__.side_effect = enter
            result = ytdl.get_video_info("https://youtu.be/JQJgxx38S30")

        self.assertEqual(result["id"], "JQJgxx38S30")
        self.assertEqual(youtube_dl.call_count, 2)
        retry_opts = youtube_dl.call_args_list[1][0][0]
        self.assertEqual(
            retry_opts["extractor_args"]["youtube"]["player_client"],
            ["tv_downgraded", "android_vr"],
        )

    def test_get_video_info_does_not_retry_for_other_errors(self):
        with patch("ytdl.YoutubeDL") as youtube_dl:
            youtube_dl.return_value.__enter__.return_value.extract_info.side_effect = DownloadError(
                "Video unavailable"
            )
            with self.assertRaises(DownloadError):
                ytdl.get_video_info("https://youtu.be/JQJgxx38S30")

        self.assertEqual(youtube_dl.call_count, 1)

    def test_default_opts_picks_up_cookies_env(self):
        with patch.dict("os.environ", {"YTVIDEOFREE_COOKIES_FILE": "/tmp/cookies.txt"}, clear=False):
            opts = ytdl.default_opts()
        self.assertEqual(opts["cookiefile"], "/tmp/cookies.txt")

    def test_main_threads_cookies_flag_into_env(self):
        with patch.dict("os.environ", {}, clear=False) as env, patch(
            "ytdl.extract_video_id", return_value="JQJgxx38S30"
        ), patch("ytdl.cmd_info") as cmd_info, patch(
            "sys.argv", ["ytdl.py", "info", "https://youtu.be/JQJgxx38S30", "--cookies", "/tmp/cookies.txt"]
        ), patch("sys.stdout", new_callable=MagicMock):
            ytdl.main()
            cmd_info.assert_called_once_with("https://youtu.be/JQJgxx38S30")
            self.assertEqual(env.get("YTVIDEOFREE_COOKIES_FILE"), "/tmp/cookies.txt")

    def test_main_shows_friendly_message_for_bot_check(self):
        from downloader.errors import BOT_CHECK_MESSAGE

        bot_check = (
            "[youtube] JQJgxx38S30: Sign in to confirm you're not a bot. "
            "Use --cookies-from-browser or --cookies for the authentication."
        )

        with patch.dict("os.environ", {}, clear=False), patch(
            "ytdl.extract_video_id", return_value="JQJgxx38S30"
        ), patch("ytdl.cmd_info", side_effect=DownloadError(bot_check)), patch(
            "sys.argv", ["ytdl.py", "info", "https://youtu.be/JQJgxx38S30"]
        ), patch("sys.stdout", new_callable=MagicMock), patch(
            "sys.stderr", new_callable=MagicMock
        ) as stderr, self.assertRaises(SystemExit) as ctx:
            ytdl.main()

        self.assertEqual(ctx.exception.code, 1)
        written = "".join(str(call) for call in stderr.write.call_args_list)
        self.assertIn("bot check", written.lower())
        self.assertIn("YTVIDEOFREE_COOKIES_FILE", written)


if __name__ == "__main__":
    unittest.main()
