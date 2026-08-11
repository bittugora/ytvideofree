# ytvideofree (Django Edition)

A Django app for ytvideofree.com: inspect YouTube videos, download video/audio
with yt-dlp, fetch transcripts, and grab thumbnails — with the same web UI,
JSON API, and CLI as the original.

- **Web UI** — paste a link (or type it), see the thumbnail instantly, choose a format, download
- **Dark mode** — theme toggle that follows the OS setting and remembers your choice
- **PWA** — installable on mobile/desktop (install prompt), app-shell service worker, offline fallback
- **AMP** — a valid AMP landing page at `/amp` linked from the home page
- **Blog** — Django blog app at `/blog/` with tags, pagination, an RSS feed at `/blog/feed/`, and an admin at `/admin/`
- **SEO** — Open Graph/Twitter cards, `robots.txt`, and `sitemap.xml` (includes blog posts)
- **Rate limiting** — admin-configurable per-IP/user limits (concurrent requests, requests per window, downloads per day)
- **CLI** — `ytdl.py` for scripting and automation
- **API** — JSON endpoints for programmatic use (same shapes as the FastAPI original)
- **No history** — temporary files, no download history stored

## Project Structure

```
manage.py              Django entry point
ytvideofree/           Django project (settings, urls, wsgi/asgi)
downloader/            Django app
  core/media.py        yt-dlp integration (inspect, download, thumbnail)
  core/transcripts.py  YouTube transcript extraction
  views.py             Page + JSON API views
  site_pages.py        Static content for /docs /terms /privacy /copyright
  errors.py            Error normalization (same messages as original)
blog/                  Django blog app (posts, tags, admin)
templates/             Django HTML templates (home, pages, blog, AMP)
static/                CSS, JS, PWA manifest, service worker, icons
tests/                 Unit + route tests
ytdl.py                CLI tool (info, download, transcript)
scripts/
  start.ps1            Windows launcher
  deploy_ubuntu.sh     VPS deployment script
  generate_icons.py    Regenerates the PWA icon PNGs (stdlib only)
deploy/
  systemd/             systemd service unit
  openlitespeed/       OpenLiteSpeed proxy notes
  ytvideofree.env.example
Dockerfile
docker-compose.yml
Procfile
requirements.txt
```

## Quick Start (Local)

### Prerequisites

- Python 3.12+ (3.10+ works for Django 5)
- FFmpeg (for MP4 merging and MP3 conversion)
- Node.js (optional, improves yt-dlp extraction)

### Setup

```bash
git clone <repo-url> ytvideofree
cd ytvideofree

python -m venv .venv
source .venv/bin/activate    # Linux/macOS
# or: .\.venv\Scripts\activate  (Windows)

pip install -r requirements.txt
python manage.py migrate
python manage.py seed_blog   # optional: create demo blog posts
```

### Run the Web App

```bash
python manage.py runserver 127.0.0.1:8000
```

Open http://127.0.0.1:8000

Create an admin user for the blog:

```bash
python manage.py createsuperuser
```

Then manage posts at http://127.0.0.1:8000/admin/ and view them at
http://127.0.0.1:8000/blog/.

### Run the CLI

```bash
python ytdl.py info "https://youtube.com/watch?v=dQw4w9WgXcQ"
python ytdl.py video "https://youtu.be/dQw4w9WgXcQ" -q 1080p
python ytdl.py audio "https://youtube.com/watch?v=dQw4w9WgXcQ"
python ytdl.py transcript "https://youtube.com/watch?v=dQw4w9WgXcQ"
python ytdl.py all "https://youtube.com/watch?v=dQw4w9WgXcQ" -q 720p
```

### Run Tests

```bash
python manage.py test
```

## Rate Limiting (Security)

No sign-up/sign-in is required: each client is identified by IP address, and
all limits are enforced per IP. Limits are editable from the Django admin at
`/admin/` under **Rate limit configuration**, and current usage is visible
(and resettable) under **Client usage**:

| Setting | Default | Meaning |
|---|---|---|
| `enabled` | on | Master switch for rate limiting |
| `max_concurrent_requests` | 1 | How many API requests one client may run at the same time |
| `max_requests_per_window` | 10 | Max API requests per client per window |
| `window_seconds` | 60 | Length of the request window |
| `max_downloads_per_day` | 20 | Max **distinct video links** a client may download per day |

The daily limit counts *links*, not files: downloading the MP4, the MP3, and
the transcript of the same link together consumes a single unit, so a user can
grab everything for a link up to the admin-set daily link limit. Re-downloading
a link that was already counted today is free; a NEW link beyond the limit
returns `429` with a `detail` message. A link is counted before the download
starts, so it consumes a unit even if the download later fails, which prevents
abuse. Rate-limit bookkeeping failures never block the feature itself.

## PWA, AMP & SEO

- **PWA**: `static/manifest.json` declares the app, `static/sw.js` is served at
  `/sw.js` (root scope) and caches the app shell for offline use. The home page
  shows an install banner on browsers that support `beforeinstallprompt` (with
  an Add-to-Home-Screen hint on iOS). Icons live in `static/icons/` and can be
  regenerated with `python scripts/generate_icons.py` (also writes the 1200x630
  `static/og-image.png` social banner).
- **AMP**: the home page declares `<link rel="amphtml" href="/amp">`; `/amp` is a
  valid AMP page (no custom JS) with a canonical link back to the home page.
- **SEO**: every page ships Open Graph and Twitter Card meta tags plus a
  canonical URL. `robots.txt` and `sitemap.xml` are generated from Django views
  and include published blog posts.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DJANGO_SECRET_KEY` | dev-only key | Django secret key (required in production) |
| `DJANGO_DEBUG` | `1` | Set to `0` in production |
| `YTTAKEN_ALLOWED_HOSTS` | `*` | Comma-separated allowed Host headers |
| `YTTAKEN_OUTPUT_DIR` | system temp dir | Temporary download directory |
| `YTTAKEN_FFMPEG_LOCATION` | auto-detected | Path to ffmpeg binary |
| `YTTAKEN_NODE_LOCATION` | auto-detected | Path to node binary |
| `YTTAKEN_JS_RUNTIMES` | auto-detected | Comma-separated JS runtimes for yt-dlp (`deno`, `node`, `bun`, `quickjs`) |
| `YTTAKEN_DENO_LOCATION` | auto-detected | Path to deno binary |
| `YTTAKEN_BUN_LOCATION` | auto-detected | Path to bun binary |
| `YTTAKEN_QUICKJS_LOCATION` | auto-detected | Path to quickjs binary |
| `YTTAKEN_COOKIES_FILE` | (none) | yt-dlp cookies file path |

## YouTube anti-bot checks

YouTube periodically challenges automated requests with “Sign in to confirm
you're not a bot.” Modern yt-dlp answers these JS challenges and mints PO
tokens using an external JavaScript runtime — only `deno` is enabled by
default, so this app auto-detects `node`/`bun`/`deno`/`quickjs` from `PATH`
(overridable with `YTTAKEN_JS_RUNTIMES` and the per-runtime location vars above)
and enables every runtime it finds. Install one of those runtimes on the
server. For IPs that YouTube flags regardless of the solver, export cookies
to a file and set `YTTAKEN_COOKIES_FILE` (see the yt-dlp wiki for how to
export YouTube cookies).

## Docker

```bash
docker compose up -d
```

Opens on http://localhost:8000

Or build and run manually:

```bash
docker build -t ytvideofree .
docker run -d -p 8000:8000 ytvideofree
```

## API Endpoints

All endpoints accept `POST` with `Content-Type: application/json`.

### Inspect

```http
POST /api/inspect
{"url": "https://www.youtube.com/watch?v=VIDEO_ID"}
```

Returns title, channel, duration, thumbnail, available qualities, FFmpeg status.

### Download

```http
POST /api/download
{
  "url": "https://youtu.be/VIDEO_ID",
  "mode": "video",
  "quality": "1080p",
  "audio_quality": "192"
}
```

- `mode`: `"video"` or `"audio"`
- `quality`: `best`, `2160p`, `1440p`, `1080p`, `720p`, `480p`, `360p`
- `audio_quality`: `128`, `192`, `256`, `320`

Returns the media file directly.

### Thumbnail

```http
POST /api/thumbnail
{"url": "https://www.youtube.com/watch?v=VIDEO_ID"}
```

Returns the largest available thumbnail (JPEG attachment) for the video.

### Transcript

```http
POST /api/transcript
{
  "url": "https://youtube.com/shorts/VIDEO_ID",
  "languages": ["en"],
  "translate_to": null,
  "format": "txt"
}
```

```http
POST /api/transcript/download
{
  "url": "https://youtube.com/watch?v=VIDEO_ID",
  "format": "srt",
  "title": "Optional video title used for the file name"
}
```

The downloaded TXT/SRT file is named after the video title when one is
provided (falling back to the video ID and language code).

## Notes

- The JSON API views are CSRF-exempt because the web UI posts JSON without a
  CSRF token. Keep the site behind a reverse proxy and restrict
  `YTTAKEN_ALLOWED_HOSTS` in production.
- Temporary media files are cleaned up after each download response finishes.
- The 404 page, `/docs`, `/terms`, `/privacy`, `/copyright`, and the frontend
  follow the same design as the original.

## Deploying

See `scripts/deploy_ubuntu.sh` and `deploy/openlitespeed/vhost-notes.md` for a
Hostinger/OpenLiteSpeed walkthrough, or push to Render/Heroku using the
included `render.yaml` / `Procfile`. Migrations run automatically at startup
on Docker, Render/Heroku (Procfile), and systemd deployments.

## Security Notes

- gunicorn listens on `127.0.0.1` in the systemd unit — never expose port 8000 publicly
- Restrict OpenLiteSpeed WebAdmin (port 7080) to trusted IPs
- Use HTTPS in production (required for clipboard access and service workers)
- Review the copyright page and add a contact email before public launch

## License

Use only for content you own or have permission to download. The authors are not affiliated with YouTube or Google.
#   y t v i d e o f r e e  
 