"""Production settings — RDS Postgres, S3 media + static via CloudFront OAC, DEBUG off.

Every secret comes from the environment (systemd ``EnvironmentFile`` on EC2).
Reads with ``os.environ[...]`` (not ``.get(...)``) so a missing variable fails
loudly at import time — safer than silently starting with a bad config.

CloudFront custom domains are optional: if ``AWS_S3_CUSTOM_DOMAIN`` /
``AWS_STATIC_CUSTOM_DOMAIN`` are unset, django-storages falls back to the
bucket's regional S3 URL. That's the path used during Session 10 verification
before the CloudFront distribution exists.
"""

import os

from .base import *  # noqa: F401,F403
from .base import BASE_DIR

SECRET_KEY = os.environ['DJANGO_SECRET_KEY']

DEBUG = False

# ALLOWED_HOSTS: comma-separated env var so the EIP, apex domain, and any
# other public hostnames can all coexist without redeploying settings.
# Falls back to [DOMAIN] when unset -- covers the local run case where
# only DOMAIN is populated.
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get('ALLOWED_HOSTS', os.environ['DOMAIN']).split(',')
    if host.strip()
]

# CloudFront terminates TLS and forwards X-Forwarded-Proto; trust the header
# so request.is_secure() reports correctly. Do NOT enable SECURE_SSL_REDIRECT
# -- CloudFront already redirects HTTP to HTTPS at the edge, and a Django-
# side redirect would compete with the origin fetch.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# HSTS soak (Session 15). 60 seconds is short enough that any HTTPS
# breakage recovers in a minute, but the header is actually being sent
# and browsers pin us to HTTPS for that window. Session 16 ramps to
# 31536000 (one year) + INCLUDE_SUBDOMAINS + PRELOAD once we're
# confident nothing else regresses.
SECURE_HSTS_SECONDS = 60

# CSRF_TRUSTED_ORIGINS is scheme+host per Django 4+. Same comma-separated
# env shape as ALLOWED_HOSTS. Falls back to apex + www over https for the
# local `runserver --settings=config.settings.production` path.
_domain = os.environ['DOMAIN']
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        'CSRF_TRUSTED_ORIGINS',
        f'https://{_domain},https://www.{_domain}',
    ).split(',')
    if origin.strip()
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ['DB_NAME'],
        'USER': os.environ['DB_USER'],
        'PASSWORD': os.environ['DB_PASSWORD'],
        'HOST': os.environ['DB_HOST'],
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}


# --------------------------------------------------------------------------
# Storage backends
# --------------------------------------------------------------------------
# Two S3 buckets provisioned by ``infra/phase3``: one for MEDIA_URL uploads
# (``AWS_STORAGE_BUCKET_NAME``), one for collectstatic output
# (``AWS_STATIC_BUCKET_NAME``). Static gets ``ManifestS3StaticStorage`` so
# ``collectstatic`` hashes filenames + uploads them in one step.

# S3 key prefixes (``location``) match CloudFront's path patterns exactly:
# ``/media/*`` and ``/static/*`` behaviors route to the corresponding S3
# origin without any prefix rewriting. Also keeps the two buckets tidy --
# every uploaded object sits under its purpose prefix.
_media_options = {
    'bucket_name': os.environ['AWS_STORAGE_BUCKET_NAME'],
    'region_name': os.environ['AWS_REGION'],
    'location': 'media',
    'default_acl': None,  # bucket is private; CloudFront OAC handles access.
    'querystring_auth': False,  # public URLs, no signature params.
}
if _media_domain := os.environ.get('AWS_S3_CUSTOM_DOMAIN'):
    _media_options['custom_domain'] = _media_domain

_static_options = {
    'bucket_name': os.environ['AWS_STATIC_BUCKET_NAME'],
    'region_name': os.environ['AWS_REGION'],
    'location': 'static',
    'default_acl': None,
    'querystring_auth': False,
}
if _static_domain := os.environ.get('AWS_STATIC_CUSTOM_DOMAIN'):
    _static_options['custom_domain'] = _static_domain

STORAGES = {
    'default': {
        'BACKEND': 'storages.backends.s3.S3Storage',
        'OPTIONS': _media_options,
    },
    'staticfiles': {
        'BACKEND': 'config.storage_backends.ManifestS3StaticStorage',
        'OPTIONS': _static_options,
    },
}

STATIC_ROOT = BASE_DIR / 'staticfiles'


# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
# All records go to stderr as JSON via config.log_formatters.JsonFormatter.
# systemd's journald picks stderr up on EC2; the CloudWatch Agent (Session
# 12+) tails journald and ships records to ``/wedding/django``. See handoff
# amendment "Logging — AWS CloudWatch across the stack".
#
# ``django`` and ``django.request`` are declared explicitly to strip
# ``mail_admins`` from Django's default handler set (we ship to CloudWatch,
# not to email). Everything else — including ``rsvp``, ``gallery``,
# ``pages`` — propagates up to the root logger.

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {'()': 'config.log_formatters.JsonFormatter'},
    },
    'handlers': {
        'stderr': {
            'class': 'logging.StreamHandler',
            'formatter': 'json',
        },
    },
    'root': {'handlers': ['stderr'], 'level': 'INFO'},
    'loggers': {
        'django': {
            'level': 'INFO',
            'handlers': ['stderr'],
            'propagate': False,
        },
        'django.request': {
            # Django logs 4xx at WARNING and 5xx at ERROR under this logger;
            # bumping the floor to WARNING skips the noisy request-completed
            # DEBUG chatter we don't want in prod.
            'level': 'WARNING',
            'handlers': ['stderr'],
            'propagate': False,
        },
    },
}
