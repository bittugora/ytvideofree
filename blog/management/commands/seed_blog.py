"""Seed the blog with a few published demo posts and tags.

Usage:  python manage.py seed_blog
Posts whose slug already exists are skipped, so the command is safe to re-run.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from blog.models import Post, Tag

POSTS = [
    {
        "title": "How to Download YouTube Videos as MP4",
        "slug": "download-youtube-videos-as-mp4",
        "tags": ["guide", "mp4"],
        "publish_days_ago": 9,
        "body": (
            "Paste a YouTube link into the downloader and pick MP4 Video to save it as an MP4 file. "
            "Choose a quality from Best available down to 360p, then click Download MP4. "
            "The app fetches the best video and audio tracks available and merges them with FFmpeg, "
            "so the file plays on phones, tablets, and TVs without extra conversion.\n\n"
            "Regular videos, Shorts, and youtu.be links all work. Use the tool only for videos you "
            "own or have permission to download."
        ),
    },
    {
        "title": "Convert Any YouTube Video to MP3",
        "slug": "convert-youtube-video-to-mp3",
        "tags": ["guide", "mp3"],
        "publish_days_ago": 6,
        "body": (
            "Switching to the MP3 Audio tab turns any video into a high-quality audio file. "
            "Pick a bitrate from 128 to 320 kbps and click Download MP3. "
            "The audio track is extracted and encoded with FFmpeg, so it works with music players, "
            "podcast apps, and car stereos.\n\n"
            "Long videos take a little longer because the audio has to be encoded. "
            "The thumbnail appears as soon as you paste the link, so you can confirm the right "
            "video before downloading."
        ),
    },
    {
        "title": "Get Video Transcripts with Timestamps",
        "slug": "get-video-transcripts-with-timestamps",
        "tags": ["guide", "transcript"],
        "publish_days_ago": 3,
        "body": (
            "The Transcript tab pulls the captions for a video and lets you copy them or download "
            "them as TXT or SRT files. SRT keeps the timestamped captions, which is handy for "
            "subtitling and editing.\n\n"
            "Transcripts download with the video's title as the file name, and the SRT export "
            "includes the timing information for every caption. If a video has no captions, the "
            "app will tell you instead of returning an empty file."
        ),
    },
]


class Command(BaseCommand):
    help = "Create demo published blog posts and tags."

    def handle(self, *args, **options):
        user = None
        try:
            user = get_user_model().objects.filter(is_superuser=True).first()
        except Exception:
            pass

        created = 0
        for item in POSTS:
            if Post.objects.filter(slug=item["slug"]).exists():
                self.stdout.write(f"skip existing post: {item['slug']}")
                continue

            tags = [Tag.objects.get_or_create(name=name)[0] for name in item["tags"]]
            post = Post.objects.create(
                title=item["title"],
                slug=item["slug"],
                author=user,
                body=item["body"],
                publish=timezone.now() - timedelta(days=item["publish_days_ago"]),
                status=Post.Status.PUBLISHED,
            )
            post.tags.set(tags)
            created += 1
            self.stdout.write(self.style.SUCCESS(f"created post: {post.title}"))

        self.stdout.write(self.style.SUCCESS(f"Done. {created} post(s) created."))
