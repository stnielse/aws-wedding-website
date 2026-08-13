"""Signal handlers wiring Photo lifecycle events.

Two signals attach:

* ``pre_save`` — auto-populates ``slug`` from the image filename when the
  user leaves it blank. Slug is what drives derivative filenames, so it
  must be settled before the post_save handler runs.
* ``post_save`` — on first save of a Photo, generates srcset derivatives
  (via ``gallery.services.generate_derivatives``) and back-fills the
  intrinsic ``width`` / ``height`` fields without re-triggering the
  signal. Also emits the ``photo_uploaded`` structured log record we've
  had since Session 10.
"""

import contextlib
import logging
import os

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils.text import slugify

from .models import Photo
from .services import generate_derivatives

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Photo)
def _populate_slug(sender, instance, **_kwargs):
    if instance.slug:
        return

    name = getattr(instance.image, 'name', '') or ''
    stem = os.path.splitext(os.path.basename(name))[0] or 'photo'
    base = slugify(stem)[:90] or 'photo'

    candidate = base
    counter = 2
    existing = Photo.objects.filter(slug=candidate).exclude(pk=instance.pk)
    while existing.exists():
        candidate = f'{base}-{counter}'
        counter += 1
        existing = Photo.objects.filter(slug=candidate).exclude(pk=instance.pk)

    instance.slug = candidate


@receiver(post_save, sender=Photo)
def _log_photo_created(sender, instance, created, **_kwargs):
    if not created:
        return

    size = None
    with contextlib.suppress(OSError, ValueError, AttributeError):
        size = instance.image.size

    logger.info(
        'photo_uploaded',
        extra={'photo_id': instance.pk, 'size_bytes': size, 'slug': instance.slug},
    )


@receiver(post_save, sender=Photo)
def _generate_photo_derivatives(sender, instance, created, **_kwargs):
    if not created:
        return
    if not instance.image or not instance.image.name:
        return

    try:
        result = generate_derivatives(instance.image.name, instance.slug)
    except Exception:
        logger.exception(
            'photo_derivative_generation_failed',
            extra={'photo_id': instance.pk, 'slug': instance.slug},
        )
        return

    # `update()` bypasses save() so we don't re-fire post_save.
    Photo.objects.filter(pk=instance.pk).update(
        width=result.width, height=result.height
    )
    instance.width = result.width
    instance.height = result.height

    logger.info(
        'photo_derivatives_generated',
        extra={
            'photo_id': instance.pk,
            'slug': instance.slug,
            'generated': len(result.generated),
            'skipped': len(result.skipped),
            'intrinsic_width': result.width,
            'intrinsic_height': result.height,
        },
    )
