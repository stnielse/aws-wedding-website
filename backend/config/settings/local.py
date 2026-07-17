"""Local development settings — SQLite, DEBUG on, filesystem media.

Never used in production. The insecure SECRET_KEY below is safe to commit —
the `django-insecure-` prefix is Django's convention for dev-only keys.
"""

from .base import *  # noqa: F401,F403
from .base import BASE_DIR

SECRET_KEY = 'django-insecure-local-dev-only-do-not-use-in-prod-8@!=ip@c0ap4o'

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

MEDIA_ROOT = BASE_DIR / 'media'
MEDIA_URL = '/media/'
