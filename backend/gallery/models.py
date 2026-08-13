from django.core.files.storage import default_storage
from django.db import models


def _photo_upload_to(instance, filename):
    return f'gallery/originals/{filename}'


class Photo(models.Model):
    """A single gallery photo.

    Uploaded through admin or seeded via ``sync_gallery_photos``. A post_save
    signal generates srcset derivatives at ``gallery/derivatives/<slug>-<W>.jpg``
    for W in ``WIDTHS``, and populates intrinsic ``width`` / ``height`` from
    the original so templates can render explicit ``<img>`` dimensions.
    """

    WIDTHS = (640, 1024, 1600, 2400)
    DEFAULT_WIDTH = 1600

    image = models.ImageField(upload_to=_photo_upload_to)
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text='Used for derivative filenames. Auto-filled on save if left blank.',
        blank=True,
    )
    width = models.PositiveIntegerField(default=0, editable=False)
    height = models.PositiveIntegerField(default=0, editable=False)
    caption = models.CharField(max_length=300, blank=True)
    alt_text = models.CharField(max_length=300, blank=True)
    order = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', '-uploaded_at']

    def __str__(self):
        return self.caption or self.slug or self.image.name

    def variant_url(self, width: int) -> str:
        return default_storage.url(f'gallery/derivatives/{self.slug}-{width}.jpg')

    @property
    def src(self) -> str:
        return self.variant_url(self.DEFAULT_WIDTH)

    @property
    def srcset(self) -> str:
        return ', '.join(f'{self.variant_url(w)} {w}w' for w in self.WIDTHS)
