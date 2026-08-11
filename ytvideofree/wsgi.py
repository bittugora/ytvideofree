"""WSGI config for the ytvideofree Django edition."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ytvideofree.settings")

application = get_wsgi_application()
