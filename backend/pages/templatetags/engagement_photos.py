"""Template tag exposing the seven editorial engagement photos to `home.html`.

`resize_engagement_photos` emits derivatives + a `dimensions.json` sidecar in
`static/img/engagement/derivatives/`. This tag reads the sidecar once per
process (module-level cache), then returns per-slot dicts the template
composes into `<img>` markup.

Usage:
    {% load engagement_photos %}
    {% engagement_photo 'hero' as hero %}
    <img src="{{ hero.src }}" srcset="{{ hero.srcset }}"
         width="{{ hero.width }}" height="{{ hero.height }}"
         sizes="100vw" loading="eager" alt="…">
"""

import json
from pathlib import Path

from django import template
from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage

register = template.Library()

WIDTHS = [640, 1024, 1600, 2400]
DEFAULT_WIDTH = 1600  # `src` fallback for browsers that ignore srcset

_dimensions_cache: dict | None = None


def _load_dimensions() -> dict:
    global _dimensions_cache
    if _dimensions_cache is None:
        path = (
            Path(settings.BASE_DIR)
            / 'static'
            / 'img'
            / 'engagement'
            / 'derivatives'
            / 'dimensions.json'
        )
        _dimensions_cache = json.loads(path.read_text())
    return _dimensions_cache


@register.simple_tag
def engagement_photo(slot: str) -> dict:
    dims = _load_dimensions()
    if slot not in dims:
        raise template.TemplateSyntaxError(
            f'engagement_photo: unknown slot {slot!r} (known: {sorted(dims)})'
        )

    def variant_url(width: int) -> str:
        return staticfiles_storage.url(f'img/engagement/derivatives/{slot}-{width}.jpg')

    srcset = ', '.join(f'{variant_url(w)} {w}w' for w in WIDTHS)

    return {
        'src': variant_url(DEFAULT_WIDTH),
        'srcset': srcset,
        'width': dims[slot]['width'],
        'height': dims[slot]['height'],
    }
