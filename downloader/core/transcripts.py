from __future__ import annotations

from typing import Any

from youtube_transcript_api import YouTubeTranscriptApi


DEFAULT_LANGUAGES = ["en", "en-US", "en-GB"]


def get_transcript(
    video_id: str,
    *,
    languages: list[str] | None = None,
    translate_to: str | None = None,
) -> dict[str, Any]:
    preferred = languages or DEFAULT_LANGUAGES
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
