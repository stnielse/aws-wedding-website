"""Tests for the gallery app.

Covers the pieces we can exercise without a real image on disk: signal-based
logging (existing) plus new coverage for the model helpers, view queryset
ordering, and the resize helper's idempotency contract. Actual JPEG bytes
are synthesized with Pillow inside tests so we don't add fixture files.
"""

import io
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from gallery.models import Photo
from gallery.services import (
    WIDTHS,
    DerivativeResult,
    derivative_key,
    generate_derivatives,
)
from gallery.signals import _log_photo_created


class PhotoUploadSignalTests(SimpleTestCase):
    def test_created_true_emits_photo_uploaded_log(self):
        instance = MagicMock()
        instance.pk = 42
        instance.slug = 'test-photo'
        instance.image.size = 12345

        with self.assertLogs('gallery.signals', level='INFO') as ctx:
            _log_photo_created(sender=None, instance=instance, created=True)

        self.assertEqual(len(ctx.records), 1)
        record = ctx.records[0]
        self.assertEqual(record.getMessage(), 'photo_uploaded')
        self.assertEqual(record.photo_id, 42)
        self.assertEqual(record.size_bytes, 12345)

    def test_created_false_emits_nothing(self):
        with self.assertNoLogs('gallery.signals', level='INFO'):
            _log_photo_created(sender=None, instance=MagicMock(), created=False)

    def test_size_unavailable_still_logs(self):
        instance = MagicMock()
        instance.pk = 7
        instance.slug = 'no-size'
        type(instance.image).size = property(
            lambda self: (_ for _ in ()).throw(OSError('no size for you'))
        )

        with self.assertLogs('gallery.signals', level='INFO') as ctx:
            _log_photo_created(sender=None, instance=instance, created=True)

        self.assertEqual(len(ctx.records), 1)
        self.assertEqual(ctx.records[0].photo_id, 7)
        self.assertIsNone(ctx.records[0].size_bytes)


def _jpeg_bytes(width=2000, height=1200, color=(180, 200, 160)):
    """Synthesize a single-color JPEG of the given dimensions."""
    im = Image.new('RGB', (width, height), color)
    buf = io.BytesIO()
    im.save(buf, format='JPEG', quality=90)
    return buf.getvalue()


class GenerateDerivativesTests(SimpleTestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.storage = FileSystemStorage(location=self._tmpdir.name)

    def test_writes_all_widths_and_reports_intrinsic_dims(self):
        source_key = 'gallery/originals/synthesized.jpg'
        self.storage.save(source_key, ContentFile(_jpeg_bytes(3200, 2000)))

        result = generate_derivatives(source_key, 'synth', storage=self.storage)

        self.assertEqual(result.width, 3200)
        self.assertEqual(result.height, 2000)
        self.assertEqual(len(result.generated), len(WIDTHS))
        self.assertEqual(result.skipped, [])

        for w in WIDTHS:
            key = derivative_key('synth', w)
            self.assertTrue(self.storage.exists(key), f'missing derivative {key}')

    def test_second_run_skips_existing_derivatives(self):
        source_key = 'gallery/originals/synth.jpg'
        self.storage.save(source_key, ContentFile(_jpeg_bytes(2400, 1600)))

        first = generate_derivatives(source_key, 'synth-idem', storage=self.storage)
        self.assertEqual(len(first.generated), len(WIDTHS))

        second = generate_derivatives(source_key, 'synth-idem', storage=self.storage)
        self.assertEqual(second.generated, [])
        self.assertEqual(len(second.skipped), len(WIDTHS))

    def test_force_true_regenerates_existing_derivatives(self):
        source_key = 'gallery/originals/synth-force.jpg'
        self.storage.save(source_key, ContentFile(_jpeg_bytes(2400, 1600)))

        generate_derivatives(source_key, 'synth-force', storage=self.storage)
        forced = generate_derivatives(
            source_key, 'synth-force', storage=self.storage, force=True
        )
        self.assertEqual(len(forced.generated), len(WIDTHS))
        self.assertEqual(forced.skipped, [])

    def test_smaller_source_produces_full_size_copies_no_upscale(self):
        # 900px-wide source: only the 640 derivative should be a true resize;
        # 1024/1600/2400 are all >= source width and get copied without upscale.
        source_key = 'gallery/originals/small.jpg'
        self.storage.save(source_key, ContentFile(_jpeg_bytes(900, 600)))

        generate_derivatives(source_key, 'small-src', storage=self.storage)

        for w in WIDTHS:
            key = derivative_key('small-src', w)
            with self.storage.open(key, 'rb') as fp:
                im = Image.open(fp)
                actual_w = im.size[0]
            if w >= 900:
                self.assertEqual(actual_w, 900, f'{w}w derivative should not upscale')
            else:
                self.assertEqual(actual_w, w)


@override_settings(MEDIA_ROOT=None)  # per-test tempdir set in setUp
class PhotoModelAndPipelineTests(TestCase):
    """End-to-end: create a Photo → signal fires → derivatives exist + dims set.

    Uses a per-test tempdir as MEDIA_ROOT so real files land there and get
    cleaned up. Requires the DB (creates Photo rows).
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        settings_override = override_settings(MEDIA_ROOT=self._tmpdir.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)

    def _make_photo(self, filename='candid.jpg', width=1600, height=1200, **kwargs):
        photo = Photo(**kwargs)
        photo.image.save(filename, ContentFile(_jpeg_bytes(width, height)), save=True)
        photo.refresh_from_db()
        return photo

    def test_signal_populates_slug_dims_and_writes_derivatives(self):
        photo = self._make_photo(filename='seaside-01.jpg', width=1800, height=1200)

        self.assertEqual(photo.slug, 'seaside-01')
        self.assertEqual(photo.width, 1800)
        self.assertEqual(photo.height, 1200)

        base = Path(self._tmpdir.name)
        for w in WIDTHS:
            self.assertTrue(
                (base / 'gallery' / 'derivatives' / f'seaside-01-{w}.jpg').exists(),
                f'missing derivative {w}',
            )

    def test_srcset_lists_all_widths_in_ascending_order(self):
        photo = self._make_photo(filename='arch.jpg', width=1600, height=2000)

        parts = [chunk.strip() for chunk in photo.srcset.split(',')]
        self.assertEqual(len(parts), len(WIDTHS))
        for part, width in zip(parts, WIDTHS, strict=True):
            self.assertIn(f'{width}w', part)
            self.assertIn(f'arch-{width}.jpg', part)

    def test_src_uses_default_1600_width(self):
        photo = self._make_photo(filename='hero.jpg')
        self.assertIn('hero-1600.jpg', photo.src)

    def test_slug_collision_gets_counter_suffix(self):
        # Storage backends uniquify filenames on write, so the "same filename
        # again" case never actually reaches the slug-derivation logic. The
        # collision path matters when derived slugs would clash independent
        # of the file — e.g., different filenames slugify to the same stem,
        # or two rapid saves from the sync command. Exercise the pre_save
        # handler directly with a mock instance to cover it.
        Photo.objects.create(slug='sunset', width=100, height=100)

        from gallery.signals import _populate_slug

        instance = MagicMock(spec=Photo)
        instance.slug = ''
        instance.pk = None
        instance.image.name = 'gallery/originals/sunset.jpg'
        _populate_slug(sender=Photo, instance=instance)
        self.assertEqual(instance.slug, 'sunset-2')

        # And a third collision should bump to -3.
        Photo.objects.create(slug='sunset-2', width=100, height=100)
        instance.slug = ''
        _populate_slug(sender=Photo, instance=instance)
        self.assertEqual(instance.slug, 'sunset-3')


@override_settings(ALLOWED_HOSTS=['*'])
class GalleryViewTests(TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        settings_override = override_settings(MEDIA_ROOT=self._tmpdir.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)

    def _make_photo(self, filename, order=0, caption=''):
        photo = Photo(order=order, caption=caption)
        photo.image.save(filename, ContentFile(_jpeg_bytes(1400, 900)), save=True)
        return photo

    def test_empty_gallery_still_returns_200_with_root_and_data_block(self):
        response = self.client.get(reverse('gallery:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="gallery-root"')
        self.assertContains(response, 'id="gallery-data"')
        self.assertContains(response, 'Photos are on the way')

    def test_view_orders_by_order_then_uploaded_at_desc(self):
        # Same order, different upload times: newest wins in tiebreaker.
        self._make_photo('one.jpg', order=0, caption='one')
        b = self._make_photo('two.jpg', order=0, caption='two')
        self._make_photo('three.jpg', order=-1 if False else 0, caption='three')

        response = self.client.get(reverse('gallery:index'))
        payload = self._extract_json(response.content)
        slugs = [p['slug'] for p in payload['photos']]
        # order tie: newest upload first
        self.assertEqual(slugs, ['three', 'two', 'one'])

        # Now explicit order wins
        b.order = -1  # PositiveIntegerField won't accept negative; use larger value.
        # (Guarding against user surprise: use a value bump instead.)
        b.order = 10
        b.save(update_fields=['order'])
        response = self.client.get(reverse('gallery:index'))
        slugs = [p['slug'] for p in self._extract_json(response.content)['photos']]
        # b sinks to the bottom because it's after the order=0 rows.
        self.assertEqual(slugs[-1], 'two')

    def test_view_serializes_each_photo_with_expected_shape(self):
        self._make_photo('single.jpg', caption='hello')
        response = self.client.get(reverse('gallery:index'))
        payload = self._extract_json(response.content)

        self.assertEqual(len(payload['photos']), 1)
        photo = payload['photos'][0]
        for key in ('id', 'slug', 'src', 'srcset', 'width', 'height', 'caption', 'alt'):
            self.assertIn(key, photo)
        self.assertEqual(photo['slug'], 'single')
        self.assertEqual(photo['caption'], 'hello')
        # alt falls back to caption when alt_text is blank.
        self.assertEqual(photo['alt'], 'hello')
        self.assertIn('single-1600.jpg', photo['src'])

    def _extract_json(self, body: bytes) -> dict:
        import re
        m = re.search(
            rb'<script[^>]*id="gallery-data"[^>]*>(.*?)</script>',
            body,
            re.S,
        )
        assert m, 'gallery-data block missing'
        return json.loads(m.group(1))


class DerivativeResultDataclassTests(SimpleTestCase):
    def test_defaults_to_empty_lists(self):
        r = DerivativeResult(width=100, height=200)
        self.assertEqual(r.generated, [])
        self.assertEqual(r.skipped, [])
