"""Tests for the storage + logging plumbing added in Session 10, the
ALLOWED_HOSTS parsing added in Session 13, and the CloudFront-aware
settings (CSRF_TRUSTED_ORIGINS, secure cookies, proxy SSL header,
S3 location prefixes) added in Session 14."""

import importlib
import json
import logging
import os
import sys
from unittest import mock

from django.test import SimpleTestCase

from config.log_formatters import JsonFormatter
from config.storage_backends import ManifestS3StaticStorage


class ManifestS3StaticStorageTests(SimpleTestCase):
    def test_mro_composes_manifest_mixin_and_s3_static_storage(self):
        from django.contrib.staticfiles.storage import ManifestFilesMixin
        from storages.backends.s3 import S3StaticStorage

        mro = ManifestS3StaticStorage.__mro__
        self.assertIn(ManifestFilesMixin, mro)
        self.assertIn(S3StaticStorage, mro)
        # ManifestFilesMixin must appear before S3StaticStorage so its
        # post_process hook wins.
        self.assertLess(mro.index(ManifestFilesMixin), mro.index(S3StaticStorage))

    def test_inherits_manifest_hashing_api(self):
        # The mixin exposes hashed_name — that's the smoke test for whether
        # collectstatic will actually hash filenames.
        self.assertTrue(hasattr(ManifestS3StaticStorage, 'hashed_name'))
        self.assertTrue(hasattr(ManifestS3StaticStorage, 'post_process'))


class JsonFormatterTests(SimpleTestCase):
    def setUp(self):
        self.formatter = JsonFormatter()

    def _format(self, record):
        return json.loads(self.formatter.format(record))

    def _make_record(self, msg='hello', level=logging.INFO, **extra):
        record = logging.LogRecord(
            name='test.logger',
            level=level,
            pathname=__file__,
            lineno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for key, value in extra.items():
            setattr(record, key, value)
        return record

    def test_core_fields(self):
        payload = self._format(self._make_record())
        self.assertEqual(payload['level'], 'INFO')
        self.assertEqual(payload['logger'], 'test.logger')
        self.assertEqual(payload['message'], 'hello')
        self.assertRegex(payload['timestamp'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$')

    def test_extra_kwargs_surface_at_top_level(self):
        payload = self._format(self._make_record(guest_id=42, party_code='FALLS-3K7'))
        self.assertEqual(payload['guest_id'], 42)
        self.assertEqual(payload['party_code'], 'FALLS-3K7')

    def test_reserved_logrecord_attrs_are_not_leaked(self):
        payload = self._format(self._make_record())
        # None of the internal LogRecord fields should end up as JSON keys.
        for reserved in ('args', 'levelno', 'pathname', 'msg', 'process'):
            self.assertNotIn(reserved, payload)

    def test_exception_info_nested(self):
        try:
            raise ValueError('boom')
        except ValueError:
            import sys

            record = self._make_record(msg='oops', level=logging.ERROR)
            record.exc_info = sys.exc_info()
        payload = self._format(record)
        self.assertIn('exception', payload)
        self.assertEqual(payload['exception']['type'], 'ValueError')
        self.assertEqual(payload['exception']['message'], 'boom')
        self.assertIn('ValueError: boom', payload['exception']['stack'])

    def test_non_json_serializable_extra_falls_back_to_str(self):
        class Weird:
            def __str__(self):
                return 'weird-repr'

        payload = self._format(self._make_record(thing=Weird()))
        self.assertEqual(payload['thing'], 'weird-repr')


class AllowedHostsParsingTests(SimpleTestCase):
    """production.settings parses ALLOWED_HOSTS as a comma-separated env var
    (Session 13). Falls back to [DOMAIN] when ALLOWED_HOSTS is unset."""

    # Minimum env every reimport of production.settings needs; ALLOWED_HOSTS
    # is set/omitted per-test to exercise the parsing branch.
    _base_env = {
        'DJANGO_SECRET_KEY': 'test-secret-key-not-used-outside-tests',
        'DOMAIN': 'example.com',
        'DB_NAME': 'wedding',
        'DB_USER': 'wedding_admin',
        'DB_PASSWORD': 'test-pw',
        'DB_HOST': 'db.example.com',
        'DB_PORT': '5432',
        'AWS_STORAGE_BUCKET_NAME': 'media-bucket',
        'AWS_STATIC_BUCKET_NAME': 'static-bucket',
        'AWS_REGION': 'us-east-1',
    }

    def _reimport_production(self):
        sys.modules.pop('config.settings.production', None)
        return importlib.import_module('config.settings.production')

    def test_defaults_to_domain_when_allowed_hosts_unset(self):
        env = dict(self._base_env)
        env.pop('ALLOWED_HOSTS', None)
        with mock.patch.dict(os.environ, env, clear=True):
            module = self._reimport_production()
        self.assertEqual(module.ALLOWED_HOSTS, ['example.com'])

    def test_splits_comma_separated_values(self):
        env = {**self._base_env, 'ALLOWED_HOSTS': '203.0.113.7,example.com,www.example.com'}
        with mock.patch.dict(os.environ, env, clear=True):
            module = self._reimport_production()
        self.assertEqual(
            module.ALLOWED_HOSTS,
            ['203.0.113.7', 'example.com', 'www.example.com'],
        )

    def test_strips_whitespace_and_drops_empty_entries(self):
        env = {**self._base_env, 'ALLOWED_HOSTS': ' a.example.com , ,b.example.com,'}
        with mock.patch.dict(os.environ, env, clear=True):
            module = self._reimport_production()
        self.assertEqual(module.ALLOWED_HOSTS, ['a.example.com', 'b.example.com'])


# The Session 14 tests all reimport production.settings under a mocked env.
# Share the base env used above so a new required var lands in exactly one
# spot.
_PROD_BASE_ENV = AllowedHostsParsingTests._base_env


def _reimport_production():
    sys.modules.pop('config.settings.production', None)
    return importlib.import_module('config.settings.production')


class CsrfTrustedOriginsTests(SimpleTestCase):
    """production.settings parses CSRF_TRUSTED_ORIGINS as a comma-separated
    env var, falling back to https://<DOMAIN> + https://www.<DOMAIN>."""

    def test_defaults_to_apex_and_www_https(self):
        env = dict(_PROD_BASE_ENV)
        env.pop('CSRF_TRUSTED_ORIGINS', None)
        with mock.patch.dict(os.environ, env, clear=True):
            module = _reimport_production()
        self.assertEqual(
            module.CSRF_TRUSTED_ORIGINS,
            ['https://example.com', 'https://www.example.com'],
        )

    def test_splits_comma_separated_values(self):
        env = {
            **_PROD_BASE_ENV,
            'CSRF_TRUSTED_ORIGINS': 'https://a.example.com,https://b.example.com',
        }
        with mock.patch.dict(os.environ, env, clear=True):
            module = _reimport_production()
        self.assertEqual(
            module.CSRF_TRUSTED_ORIGINS,
            ['https://a.example.com', 'https://b.example.com'],
        )

    def test_strips_whitespace_and_drops_empty_entries(self):
        env = {
            **_PROD_BASE_ENV,
            'CSRF_TRUSTED_ORIGINS': ' https://a.example.com , ,https://b.example.com,',
        }
        with mock.patch.dict(os.environ, env, clear=True):
            module = _reimport_production()
        self.assertEqual(
            module.CSRF_TRUSTED_ORIGINS,
            ['https://a.example.com', 'https://b.example.com'],
        )


class SecureCookieAndProxyHeaderTests(SimpleTestCase):
    """production.settings sets SESSION_COOKIE_SECURE, CSRF_COOKIE_SECURE,
    and trusts X-Forwarded-Proto from CloudFront."""

    def test_secure_proxy_ssl_header_is_x_forwarded_proto(self):
        with mock.patch.dict(os.environ, _PROD_BASE_ENV, clear=True):
            module = _reimport_production()
        self.assertEqual(
            module.SECURE_PROXY_SSL_HEADER,
            ('HTTP_X_FORWARDED_PROTO', 'https'),
        )

    def test_session_and_csrf_cookies_are_secure(self):
        with mock.patch.dict(os.environ, _PROD_BASE_ENV, clear=True):
            module = _reimport_production()
        self.assertTrue(module.SESSION_COOKIE_SECURE)
        self.assertTrue(module.CSRF_COOKIE_SECURE)

    def test_secure_ssl_redirect_stays_off(self):
        # CloudFront handles the HTTP->HTTPS redirect at the edge; Django
        # should not compete.
        with mock.patch.dict(os.environ, _PROD_BASE_ENV, clear=True):
            module = _reimport_production()
        self.assertFalse(getattr(module, 'SECURE_SSL_REDIRECT', False))


class StorageLocationPrefixTests(SimpleTestCase):
    """production.settings sets location='media' / 'static' on the S3
    storage backends so keys match CloudFront's /media/* and /static/*
    behaviors."""

    def test_media_backend_uses_media_prefix(self):
        with mock.patch.dict(os.environ, _PROD_BASE_ENV, clear=True):
            module = _reimport_production()
        self.assertEqual(module.STORAGES['default']['OPTIONS']['location'], 'media')

    def test_static_backend_uses_static_prefix(self):
        with mock.patch.dict(os.environ, _PROD_BASE_ENV, clear=True):
            module = _reimport_production()
        self.assertEqual(
            module.STORAGES['staticfiles']['OPTIONS']['location'],
            'static',
        )
