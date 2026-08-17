import tempfile
import unittest
from pathlib import Path

from downloader.core.cookiefile import inspect_cookies_file

SESSION_COOKIES = (
    "# Netscape HTTP Cookie File\n"
    "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tfake\n"
    ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tSAPISID\tfake\n"
    ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tLOGIN_INFO\tfake\n"
    ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tCONSENT\tYES+1\n"
)

LOGGED_OUT_COOKIES = (
    "# Netscape HTTP Cookie File\n"
    ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tCONSENT\tYES+1\n"
    ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tVISITOR_INFO1_LIVE\tabc\n"
)


class CookieFileTests(unittest.TestCase):
    def _write(self, content: str) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        )
        tmp.write(content)
        tmp.close()
        return Path(tmp.name)

    def test_missing_file(self):
        report = inspect_cookies_file("/nonexistent/cookies.txt")
        self.assertFalse(report.exists)
        self.assertFalse(report.usable)
        self.assertIn("not found", report.summary().lower())

    def test_empty_file(self):
        path = self._write("")
        try:
            report = inspect_cookies_file(path)
            self.assertEqual(report.cookie_count, 0)
            self.assertFalse(report.usable)
            self.assertIn("no parsable cookie", report.summary().lower())
        finally:
            path.unlink()

    def test_logged_out_cookies_have_no_session(self):
        path = self._write(LOGGED_OUT_COOKIES)
        try:
            report = inspect_cookies_file(path)
            self.assertTrue(report.exists)
            self.assertEqual(report.cookie_count, 2)
            self.assertEqual(report.youtube_cookie_count, 2)
            self.assertFalse(report.has_session)
            self.assertFalse(report.usable)
            self.assertIn("signed in", report.summary().lower())
        finally:
            path.unlink()

    def test_session_cookies_are_usable(self):
        path = self._write(SESSION_COOKIES)
        try:
            report = inspect_cookies_file(path)
            self.assertEqual(report.cookie_count, 4)
            self.assertEqual(report.youtube_cookie_count, 4)
            self.assertTrue(report.has_login_info)
            self.assertTrue(report.has_sapisid)
            self.assertTrue(report.has_session)
            self.assertTrue(report.usable)
            self.assertIn("valid", report.summary().lower())
        finally:
            path.unlink()

    def test_http_only_lines_are_counted(self):
        path = self._write("#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tfake\n")
        try:
            report = inspect_cookies_file(path)
            self.assertEqual(report.cookie_count, 1)
            self.assertEqual(report.youtube_cookie_count, 1)
            self.assertTrue(report.has_session is False or report.has_session)
        finally:
            path.unlink()

    def test_cookies_for_other_domains_only(self):
        path = self._write(
            ".example.com\tTRUE\t/\tTRUE\t2147483647\tSID\tfake\n"
        )
        try:
            report = inspect_cookies_file(path)
            self.assertEqual(report.cookie_count, 1)
            self.assertEqual(report.youtube_cookie_count, 0)
            self.assertFalse(report.usable)
            self.assertIn("none for", report.summary().lower())
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()
