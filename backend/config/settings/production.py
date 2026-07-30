"""Production settings — RDS Postgres, S3 media via CloudFront OAC, DEBUG off.

Every secret comes from the environment (systemd `EnvironmentFile` on EC2).
Reads with `os.environ[...]` (not `.get(...)`) so a missing variable fails
loudly at import time — safer than silently starting with a bad config.
"""

import os

from .base import *  # noqa: F401,F403
from .base import BASE_DIR

SECRET_KEY = os.environ['DJANGO_SECRET_KEY']

DEBUG = False

ALLOWED_HOSTS = [os.environ['DOMAIN']]

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

# Django 5.x `STORAGES` dict (replaces the old `DEFAULT_FILE_STORAGE` /
# `STATICFILES_STORAGE` scalars). django-storages provides the S3 backend.
STORAGES = {
    'default': {
        'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage',
    },
}

AWS_STORAGE_BUCKET_NAME = os.environ['AWS_STORAGE_BUCKET_NAME']
AWS_S3_REGION_NAME = os.environ['AWS_REGION']
AWS_S3_CUSTOM_DOMAIN = os.environ['CLOUDFRONT_DOMAIN']
AWS_DEFAULT_ACL = None  # bucket is private; CloudFront OAC handles access.

STATIC_ROOT = BASE_DIR / 'staticfiles'
