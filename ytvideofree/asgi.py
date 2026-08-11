"""ASGI config for the ytvideofree Django edition."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ytvideofree.settings")

application = get_asgi_application()
