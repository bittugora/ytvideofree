import unittest

from downloader.errors import (
    BOT_CHECK_MESSAGE,
    NETWORK_BLOCKED_MESSAGE,
    clean_error,
    is_bot_check_error,
    is_network_permission_error,
)


class ErrorHandlingTests(unittest.TestCase):
    def test_detects_windows_socket_permission_error(self):
        message = (
            "[youtube] psVUIguZAQg: Unable to download API page: "
            "HTTPSConnection(host='www.youtube.com', port=443): "
            "Failed to establish a new connection: [WinError 10013] "
            "An attempt was made to access a socket in a way forbidden by its access permissions"
        )

        self.assertTrue(is_network_permission_error(message))
        self.assertEqual(clean_error(Exception(message)), NETWORK_BLOCKED_MESSAGE)

    def test_detects_youtube_bot_check(self):
        message = (
            "[youtube] sKNq4CqWkT4: Sign in to confirm you're not a bot. "
            "Use --cookies-from-browser or --cookies for the authentication. "
            "See https://github.com/yt-dlp/yt-dlp/wiki/FAQ for details."
        )

        self.assertTrue(is_bot_check_error(message))
        self.assertEqual(clean_error(Exception(message)), BOT_CHECK_MESSAGE)
        self.assertIn("bot check", BOT_CHECK_MESSAGE.lower())

    def test_preserves_normal_errors(self):
        self.assertEqual(clean_error(Exception("Video unavailable")), "Video unavailable")


if __name__ == "__main__":
    unittest.main()
