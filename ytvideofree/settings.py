"""
Django settings for the ytvideofree Django edition.

Environment variables mirror the original FastAPI app where the behavior
overlaps: YTTAKEN_OUTPUT_DIR, YTTAKEN_FFMPEG_LOCATION, YTTAKEN_NODE_LOCATION,
YTTAKEN_COOKIES_FILE, and YTTAKEN_ALLOWED_HOSTS. Django-specific variables are
DJANGO_SECRET_KEY and DJANGO_DEBUG.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-ytvideofree-dev-key-change-me")

# SECURITY WARNING: don't run with debug turned on in production!
#DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
DEBUG = False

# Comma-separated list, e.g. YTTAKEN_ALLOWED_HOSTS=ytvideofree.com,www.ytvideofree.com
ALLOWED_HOSTS = [host.strip() for host in os.getenv("YTTAKEN_ALLOWED_HOSTS", "*").split(",") if host.strip()]
if not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.admin",
    "django.contrib.staticfiles",
    "django.contrib.syndication",
    "downloader",
    "blog",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "ytvideofree.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "downloader.context_processors.site_context",
            ],
        },
    },
]

WSGI_APPLICATION = "ytvideofree.wsgi.application"
ASGI_APPLICATION = "ytvideofree.asgi.application"

# The blog app stores posts; the downloader app has no models of its own.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Match the original app's trailing-slash-free routes (/docs, /healthz, /api/...).
APPEND_SLASH = False

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
