from __future__ import annotations

import logging
import re
import urllib.request
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from youtube_transcript_api import YouTubeTranscriptApi


logger = logging.getLogger(__name__)

DEFAULT_LANGUAGES = ["en", "en-US", "en-GB"]


def get_transcript(
    video_id: str,
    *,
    languages: list[str] | None = None,
    translate_to: str | None = None,
) -> dict[str, Any]:
    """Return the transcript for a video.

    The lightweight ``youtube_transcript_api`` is used first. When it fails —
    most commonly because YouTube answers a datacenter/VPS IP with the same
    bot check that blocks media downloads — we fall back to yt-dlp, which
    extracts the caption tracks through the same player-client groups that
    bypass the bot check for video/audio.
    """
    preferred = languages or DEFAULT_LANGUAGES
    try:
        return _transcript_via_api(video_id, preferred, translate_to)
    except Exception as api_error:
        logger.info(
            "youtube_transcript_api failed for %s (%s); trying yt-dlp subtitles.",
            video_id,
            api_error,
        )
        try:
            return _transcript_via_ytdlp(video_id, preferred, translate_to)
        except Exception:
            # Preserve the more specific API error when it is already friendly.
            if isinstance(api_error, LookupError):
                raise
            raise LookupError("No transcript is available for this video.") from api_error


def _transcript_via_api(
    video_id: str, preferred: list[str], translate_to: str | None
) -> dict[str, Any]:
    api = YouTubeTranscriptApi()
    transcript_list = api.list(video_id)
    available = [
        {
            "language": transcript.language,
            "language_code": transcript.language_code,
            "is_generated": transcript.is_generated,
            "is_translatable": transcript.is_translatable,
        }
        for transcript in transcript_list
    ]

    try:
        transcript = transcript_list.find_transcript(preferred)
    except Exception:
        transcript = next(iter(transcript_list), None)

    if transcript is None:
        raise LookupError("No transcript is available for this video.")

    if translate_to and translate_to != transcript.language_code:
        if not transcript.is_translatable:
            raise LookupError("This transcript is not available for translation.")
        transcript = transcript.translate(translate_to)

    segments = normalize_segments(transcript.fetch())
    text = "\n".join(segment["text"] for segment in segments)

    return {
        "language": transcript.language,
        "language_code": transcript.language_code,
        "is_generated": transcript.is_generated,
        "segments": segments,
        "text": text,
        "srt": format_srt(segments),
        "available_languages": available,
    }


def _transcript_via_ytdlp(
    video_id: str, preferred: list[str], translate_to: str | None
) -> dict[str, Any]:
    from .media import extract_raw_info

    url = f"https://www.youtube.com/watch?v={video_id}"
    info = extract_raw_info(url)

    manual = info.get("subtitles") or {}
    automatic = info.get("automatic_captions") or {}
    # Manual captions win over auto-generated ones for the same language code.
    tracks_by_lang: dict[str, list[dict[str, Any]]] = {**automatic, **manual}

    if not tracks_by_lang:
        raise LookupError("No transcript is available for this video.")

    available = [
        {
            "language": lang_code,
            "language_code": lang_code.split("-")[0],
            "is_generated": lang_code in automatic and lang_code not in manual,
            "is_translatable": False,
        }
        for lang_code in tracks_by_lang
    ]

    lang_code = _pick_language(tracks_by_lang, preferred)
    track = _pick_subtitle_track(tracks_by_lang[lang_code])
    segments = _fetch_and_parse_captions(track)

    if translate_to and translate_to != lang_code.split("-")[0]:
        raise LookupError("This transcript is not available for translation.")

    text = "\n".join(segment["text"] for segment in segments)

    return {
        "language": lang_code,
        "language_code": lang_code.split("-")[0],
        "is_generated": lang_code in automatic and lang_code not in manual,
        "segments": segments,
        "text": text,
        "srt": format_srt(segments),
        "available_languages": available,
    }


def _pick_language(
    tracks_by_lang: dict[str, list[dict[str, Any]]], preferred: list[str]
) -> str:
    keys = list(tracks_by_lang)
    for code in preferred:
        if code in keys:
            return code
    # Match the base language (e.g. "en-US" -> "en").
    for code in preferred:
        base = code.split("-")[0]
        for key in keys:
            if key == base or key.startswith(base + "-"):
                return key
    return keys[0]


def _pick_subtitle_track(tracks: list[dict[str, Any]]) -> dict[str, Any]:
    for ext in ("json3", "vtt", "srv3", "srv2", "srv1"):
        for track in tracks:
            if track.get("ext") == ext:
                return track
    return tracks[0]


def _rewrite_to_vtt(url: str) -> str:
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    query["fmt"] = ["vtt"]
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), parts.fragment)
    )


def _fetch_and_parse_captions(track: dict[str, Any]) -> list[dict[str, Any]]:
    url = _rewrite_to_vtt(track.get("url", ""))
    if not url:
        raise LookupError("No transcript is available for this video.")

    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read()

    segments = parse_vtt(data.decode("utf-8", errors="replace"))
    if not segments:
        raise LookupError("No transcript is available for this video.")
    return segments


def parse_vtt(text: str) -> list[dict[str, Any]]:
    """Parse WebVTT into normalized transcript segments."""

    def parse_time(value: str) -> float:
        parts = value.strip().split(":")
        if len(parts) == 3:
            h, m, s = parts
        else:
            h, m, s = "0", parts[0], parts[1]
        return int(h) * 3600 + int(m) * 60 + float(s)

    segments: list[dict[str, Any]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if "-->" in line:
            start_raw, end_raw = line.split("-->", 1)
            start = parse_time(start_raw)
            end = parse_time(end_raw.strip().split(" ")[0])
            i += 1
            text_lines: list[str] = []
            while i < len(lines) and lines[i].strip() != "":
                text_lines.append(lines[i].strip())
                i += 1
            content = " ".join(part for part in text_lines if part).strip()
            # YouTube VTT includes inline timing/colour tags; strip them.
            content = re.sub(r"<[^>]+>", "", content).strip()
            if content:
                segments.append(
                    {
                        "text": content,
                        "start": start,
                        "duration": max(end - start, 0.0),
                        "timestamp": format_timestamp(start, srt=False),
                    }
                )
        else:
            i += 1

    return segments


def normalize_segments(captions: Any) -> list[dict[str, Any]]:
    if hasattr(captions, "to_raw_data"):
        raw = captions.to_raw_data()
    else:
        raw = captions

    segments: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            text = item.get("text", "")
            start = float(item.get("start", 0))
            duration = float(item.get("duration", 0))
        else:
            text = getattr(item, "text", "")
            start = float(getattr(item, "start", 0))
            duration = float(getattr(item, "duration", 0))

        segments.append(
            {
                "text": text.replace("\n", " ").strip(),
                "start": start,
                "duration": duration,
                "timestamp": format_timestamp(start, srt=False),
            }
        )

    return segments


def format_srt(segments: list[dict[str, Any]]) -> str:
    blocks = []
    for index, segment in enumerate(segments, start=1):
        start = format_timestamp(segment["start"], srt=True)
        end = format_timestamp(segment["start"] + segment["duration"], srt=True)
        blocks.append(f"{index}\n{start} --> {end}\n{segment['text']}")

    return "\n\n".join(blocks) + ("\n" if blocks else "")


def format_timestamp(seconds: float, *, srt: bool) -> str:
    total_ms = int(round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)

    if srt:
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
