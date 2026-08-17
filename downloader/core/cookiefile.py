"""Validate Netscape-format cookies files used to bypass YouTube's bot check.

yt-dlp silently ignores a missing or unreadable cookies file — it just uses an
empty cookie jar and YouTube keeps answering with the bot check, with no error
hint. A file exported from a logged-out browser (or with an expired session)
fails the same way. This module inspects the file and reports what a human can
act on: does it exist, is it parseable, does it contain a signed-in YouTube
session?
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# yt-dlp treats the YouTube session as authenticated when LOGIN_INFO is present
# together with at least one SAPISID-family cookie (see the extractor's
# `_has_auth_cookies`). The rest are strong signals of a signed-in session.
SESSION_INDICATOR_COOKIES = {
    "SID",
    "SSID",
    "HSID",
    "SAPISID",
    "LOGIN_INFO",
    "__Secure-1PSID",
    "__Secure-3PSID",
    "__Secure-1PAPISID",
    "__Secure-3PAPISID",
}
SAPISID_COOKIES = {"SAPISID", "__Secure-1PAPISID", "__Secure-3PAPISID"}


@dataclass
class CookieFileReport:
    path: str
    exists: bool = False
    readable: bool = False
    error: str = ""
    cookie_count: int = 0
    youtube_cookie_count: int = 0
    session_cookie_count: int = 0
    has_login_info: bool = False
    has_sapisid: bool = False

    @property
    def has_session(self) -> bool:
        """True when the file looks like a signed-in YouTube session."""
        return self.has_login_info and self.has_sapisid

    @property
    def usable(self) -> bool:
        return (
            self.exists
            and self.readable
            and self.cookie_count > 0
            and self.youtube_cookie_count > 0
            and self.has_session
        )

    def summary(self) -> str:
        """One readable paragraph explaining what is wrong (or that it is fine)."""
        if not self.exists:
            return (
                f"Cookies file not found: {self.path}. yt-dlp silently runs with "
                "ZERO cookies, so YouTube's bot check still fires. Create the file "
                "or fix the path."
            )
        if not self.readable:
            return f"Cookies file exists but is not readable: {self.path}"
        if self.cookie_count == 0:
            return (
                f"Cookies file contains no parsable cookie lines ({self.path}). "
                "Export in Netscape format using an extension such as "
                "'Get cookies.txt LOCALLY'."
            )
        if self.youtube_cookie_count == 0:
            return (
                f"Cookies file has {self.cookie_count} cookies but none for "
                "youtube.com — export cookies for the .youtube.com domain."
            )
        if not self.has_session:
            return (
                f"Cookies file has {self.cookie_count} cookies "
                f"({self.youtube_cookie_count} for youtube.com) but no signed-in "
                "session (no LOGIN_INFO/SAPISID). Export cookies from a browser "
                "while SIGNED IN to YouTube — logged-out or expired exports do "
                "not bypass the bot check."
            )
        return (
            f"Cookies file looks valid: {self.cookie_count} cookies "
            f"({self.youtube_cookie_count} for youtube.com), including a "
            "signed-in session."
        )


def inspect_cookies_file(path: str | os.PathLike) -> CookieFileReport:
    """Inspect a Netscape-format cookies file and report its usability."""
    p = Path(path)
    report = CookieFileReport(path=str(p))
    if not p.exists():
        return report
    report.exists = True
    if not os.access(p, os.R_OK):
        return report
    report.readable = True

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        report.error = str(exc)
        return report

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # "#HttpOnly_..." lines are cookie rows, not comments.
        if line.startswith("#HttpOnly_"):
            pass
        elif line.startswith("#") or line.startswith("//"):
            continue

        parts = line.split("\t")
        if len(parts) < 7:
            parts = line.split()
        if len(parts) < 7:
            continue

        domain = parts[0]
        if domain.startswith("#HttpOnly_"):
            domain = domain[len("#HttpOnly_"):]
        name = parts[5]

        report.cookie_count += 1
        if "youtube.com" in domain:
            report.youtube_cookie_count += 1
        if name in SESSION_INDICATOR_COOKIES:
            report.session_cookie_count += 1
        if name == "LOGIN_INFO":
            report.has_login_info = True
        if name in SAPISID_COOKIES:
            report.has_sapisid = True

    return report
