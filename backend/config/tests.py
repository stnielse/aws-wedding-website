"""Tests for the storage + logging plumbing added in Session 10."""

import json
import logging

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
