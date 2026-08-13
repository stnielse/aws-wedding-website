"""Image processing helpers for the gallery app.

Generates srcset derivatives (640/1024/1600/2400 widths) from an original
photo and uploads each to whichever storage backend is currently active
(``FileSystemStorage`` in local dev, ``S3Storage`` in production).

Idempotent — a derivative that already exists at its expected key is
skipped unless ``force=True``.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import BinaryIO

from django.core.files.base import ContentFile
from django.core.files.storage import Storage, default_storage
from PIL import Image, ImageOps

WIDTHS = (640, 1024, 1600, 2400)
JPEG_QUALITY = 82


@dataclass
class DerivativeResult:
    width: int
    height: int
    generated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def derivative_key(slug: str, width: int) -> str:
    return f'gallery/derivatives/{slug}-{width}.jpg'


def generate_derivatives(
    source: BinaryIO | str,
    slug: str,
    storage: Storage | None = None,
    force: bool = False,
) -> DerivativeResult:
    """Resize the source image to each width in WIDTHS and upload as JPEG.

    ``source`` is either a file-like object opened for binary read or a
    storage key that ``storage`` knows how to open. Returns the intrinsic
    (EXIF-rotated) dimensions of the original plus which derivative keys
    were written vs skipped. When ``force`` is False and a derivative
    already exists at its expected key, that width is skipped rather
    than rewritten.
    """
    storage = storage or default_storage

    close_after = isinstance(source, str)
    source_fp = storage.open(source, 'rb') if close_after else source

    result = DerivativeResult(width=0, height=0)
    try:
        with Image.open(source_fp) as raw:
            im = ImageOps.exif_transpose(raw).convert('RGB')
            result.width, result.height = im.size

            for width in WIDTHS:
                key = derivative_key(slug, width)
                if not force and storage.exists(key):
                    result.skipped.append(key)
                    continue

                if width >= result.width:
                    resized = im.copy()
                else:
                    height = round(result.height * (width / result.width))
                    resized = im.resize((width, height), Image.LANCZOS)

                buf = io.BytesIO()
                resized.save(
                    buf,
                    format='JPEG',
                    quality=JPEG_QUALITY,
                    progressive=True,
                    optimize=True,
                )
                buf.seek(0)

                if storage.exists(key):
                    storage.delete(key)
                storage.save(key, ContentFile(buf.read()))
                result.generated.append(key)
    finally:
        if close_after:
            source_fp.close()

    return result
