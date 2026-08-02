"""Signal handlers wiring gallery lifecycle events to structured logs."""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Photo

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Photo)
def _log_photo_created(sender, instance, created, **_kwargs):
    if not created:
        return

    size = None
    try:
        size = instance.image.size
    except (OSError, ValueError, AttributeError):
        # Remote storages may fail to size the object cheaply, and
        # ImageField access can miss on unusual code paths (tests
        # constructing Photo without a file). Log the event either way.
        pass

    logger.info(
        'photo_uploaded',
        extra={'photo_id': instance.pk, 'size_bytes': size},
    )
