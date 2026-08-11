"""Static content for the /docs, /terms, /privacy, and /copyright pages."""

SITE_PAGES = {
    "docs": {
        "title": "API",
        "intro": "Use these JSON endpoints from the web UI, mobile clients, or automation.",
        "sections": [
            {
                "heading": "Inspect a video",
                "body": "Returns title, channel, thumbnail, duration, available quality choices, and FFmpeg availability.",
                "code": 'POST /api/inspect\n{\n  "url": "https://www.youtube.com/watch?v=VIDEO_ID"\n}',
            },
            {
                "heading": "Download media",
                "body": "Returns an MP4 or MP3 file response. Video quality accepts best, 2160p, 1440p, 1080p, 720p, 480p, or 360p.",
                "code": 'POST /api/download\n{\n  "url": "https://youtu.be/VIDEO_ID",\n  "mode": "video",\n  "quality": "1080p",\n  "audio_quality": "192"\n}',
            },
            {
                "heading": "Fetch transcript",
                "body": "Returns transcript text, SRT text, segments with timestamps, and available caption languages.",
                "code": 'POST /api/transcript\n{\n  "url": "https://youtube.com/shorts/VIDEO_ID",\n  "languages": ["en", "en-US"],\n  "translate_to": null,\n  "format": "txt"\n}',
            },
        ],
    },
    "terms": {
        "title": "Terms",
        "intro": "ytvideofree is a utility for content the user has the right to save, process, or reuse.",
        "sections": [
            {
                "heading": "User responsibility",
                "body": "Users are responsible for making sure they have permission to download, convert, store, or reuse any content they submit.",
            },
            {
                "heading": "Service limits",
                "body": "The service may reject unsupported URLs, unavailable videos, private videos, unavailable captions, or files that cannot be processed by the configured media tools.",
            },
            {
                "heading": "No affiliation",
                "body": "ytvideofree is an independent tool and is not affiliated with, endorsed by, or sponsored by YouTube or Google.",
            },
        ],
    },
    "privacy": {
        "title": "Privacy",
        "intro": "The app is designed to process links only long enough to complete the requested action.",
        "sections": [
            {
                "heading": "Submitted links",
                "body": "The default application does not store a download history. Temporary media files are removed after each response is sent.",
            },
            {
                "heading": "Deployment logs",
                "body": "Your hosting provider may keep access logs, error logs, IP addresses, and request metadata depending on its own settings.",
            },
            {
                "heading": "Cookies",
                "body": "The default web UI does not require user accounts or tracking cookies.",
            },
        ],
    },
    "copyright": {
        "title": "Copyright",
        "intro": "ytvideofree should be used with content you own, content licensed for download, or content you otherwise have permission to process.",
        "sections": [
            {
                "heading": "Rights holders",
                "body": "If you deploy this app publicly, add your contact email here so rights holders can report misuse or request review.",
            },
            {
                "heading": "Recommended policy",
                "body": "For a public launch, connect an abuse inbox, document a takedown process, and keep hosting logs long enough to investigate credible reports.",
            },
        ],
    },
}
