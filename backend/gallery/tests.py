"""Tests for the gallery app — Photo signal-based structured logging."""

from unittest.mock import MagicMock

from django.test import SimpleTestCase

from gallery.signals import _log_photo_created


class PhotoUploadSignalTests(SimpleTestCase):
    def test_created_true_emits_photo_uploaded_log(self):
        instance = MagicMock()
        instance.pk = 42
        instance.image.size = 12345

        with self.assertLogs('gallery.signals', level='INFO') as ctx:
            _log_photo_created(sender=None, instance=instance, created=True)

        self.assertEqual(len(ctx.records), 1)
        record = ctx.records[0]
        self.assertEqual(record.getMessage(), 'photo_uploaded')
        self.assertEqual(record.photo_id, 42)
        self.assertEqual(record.size_bytes, 12345)

    def test_created_false_emits_nothing(self):
        # Update to an existing Photo (created=False) shouldn't spam logs.
        with self.assertNoLogs('gallery.signals', level='INFO'):
            _log_photo_created(sender=None, instance=MagicMock(), created=False)

    def test_size_unavailable_still_logs(self):
        instance = MagicMock()
        instance.pk = 7
        # Simulate a storage backend that raises when asked for size.
        type(instance.image).size = property(
            lambda self: (_ for _ in ()).throw(OSError('no size for you'))
        )

        with self.assertLogs('gallery.signals', level='INFO') as ctx:
            _log_photo_created(sender=None, instance=instance, created=True)

        self.assertEqual(len(ctx.records), 1)
        self.assertEqual(ctx.records[0].photo_id, 7)
        self.assertIsNone(ctx.records[0].size_bytes)
