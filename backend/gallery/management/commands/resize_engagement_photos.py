"""Emit the 640/1024/1600/2400 srcset variants for the home page's editorial
engagement photos, plus a `dimensions.json` sidecar templates read via a
template tag.

Sources live in `backend/static/img/engagement/`; derivatives land in
`backend/static/img/engagement/derivatives/`. Idempotent — a derivative is
skipped if its mtime is newer than the source's.
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from PIL import Image

SOURCE_STEMS = [
    'hero',
    'arch',
    'break',
    'teaser-1',
    'teaser-2',
    'teaser-3',
    'teaser-4',
]

WIDTHS = [640, 1024, 1600, 2400]

JPEG_QUALITY = 82


class Command(BaseCommand):
    help = 'Regenerate srcset variants for the home page engagement photos.'

    def handle(self, *args, **options):
        src_dir = Path(settings.BASE_DIR) / 'static' / 'img' / 'engagement'
        out_dir = src_dir / 'derivatives'
        out_dir.mkdir(parents=True, exist_ok=True)

        dimensions = {}
        generated = 0
        skipped = 0

        for stem in SOURCE_STEMS:
            source = _resolve_source(src_dir, stem)
            if source is None:
                raise CommandError(
                    f"missing source for slot '{stem}' — expected "
                    f"{src_dir}/{stem}.{{jpg,jpeg,png}}"
                )

            with Image.open(source) as im:
                im = im.convert('RGB')
                intrinsic_w, intrinsic_h = im.size
                dimensions[stem] = {'width': intrinsic_w, 'height': intrinsic_h}

                for width in WIDTHS:
                    out_path = out_dir / f'{stem}-{width}.jpg'
                    if _is_fresh(out_path, source):
                        skipped += 1
                        continue

                    if width >= intrinsic_w:
                        resized = im.copy()
                    else:
                        height = round(intrinsic_h * (width / intrinsic_w))
                        resized = im.resize((width, height), Image.LANCZOS)

                    resized.save(
                        out_path,
                        format='JPEG',
                        quality=JPEG_QUALITY,
                        progressive=True,
                        optimize=True,
                    )
                    generated += 1
                    self.stdout.write(f'  wrote {out_path.name}')

        dims_path = out_dir / 'dimensions.json'
        dims_path.write_text(json.dumps(dimensions, indent=2) + '\n')

        self.stdout.write(self.style.SUCCESS(
            f'done — {generated} generated, {skipped} skipped, '
            f'{len(SOURCE_STEMS)} sources tracked in {dims_path.name}'
        ))


def _resolve_source(src_dir: Path, stem: str) -> Path | None:
    for ext in ('jpg', 'jpeg', 'png'):
        candidate = src_dir / f'{stem}.{ext}'
        if candidate.exists():
            return candidate
    return None


def _is_fresh(out_path: Path, source: Path) -> bool:
    if not out_path.exists():
        return False
    return out_path.stat().st_mtime >= source.stat().st_mtime
