"""Signal handlers wiring gallery lifecycle events to structured logs."""

import contextlib
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Photo

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Photo)
def _log_photo_created(sender, instance, created, **_kwargs):
    if not created:
        return

    # Remote storages may fail to size the object cheaply, and ImageField
    # access can miss on unusual code paths (tests constructing Photo
    # without a file). Log the event either way.
    size = None
    with contextlib.suppress(OSError, ValueError, AttributeError):
        size = instance.image.size

    logger.info(
        'photo_uploaded',
        extra={'photo_id': instance.pk, 'size_bytes': size},
    )
