"""Bulk-seed the Photo table from a directory of image files.

Usage:

    ../.venv/bin/python manage.py sync_gallery_photos /path/to/photos/

For each ``*.jpg`` / ``*.jpeg`` / ``*.png`` in the source directory, a Photo
row is created (slug = slugified filename stem, caption + alt_text blank).
Photo save fires the ``post_save`` signal in ``gallery.signals`` which
generates srcset derivatives and captures intrinsic dimensions.

Idempotent — a filename whose slug already has a Photo row is skipped by
default. Pass ``--force`` to delete-and-recreate that row (also regenerates
derivatives).
"""

from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from gallery.models import Photo

SUPPORTED_EXTS = {'.jpg', '.jpeg', '.png'}


class Command(BaseCommand):
    help = 'Create Photo rows for every supported image in the given directory.'

    def add_arguments(self, parser):
        parser.add_argument(
            'source_dir',
            help='Directory containing photo files to import.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Delete + recreate photos whose slugs already exist.',
        )

    def handle(self, *args, source_dir, force, **options):
        src = Path(source_dir).expanduser().resolve()
        if not src.is_dir():
            raise CommandError(f'not a directory: {src}')

        files = sorted(
            p for p in src.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
        )
        if not files:
            self.stdout.write(self.style.WARNING(f'no supported images under {src}'))
            return

        created = 0
        skipped = 0

        for path in files:
            slug = self._slug_from(path)
            existing = Photo.objects.filter(slug=slug).first()
            if existing and not force:
                self.stdout.write(f'  skip  {path.name} (slug={slug} already imported)')
                skipped += 1
                continue

            if existing and force:
                self.stdout.write(f'  drop  {path.name} (slug={slug}, --force)')
                existing.delete()

            photo = Photo(slug=slug)
            with path.open('rb') as fp:
                photo.image.save(path.name, ContentFile(fp.read()), save=True)

            self.stdout.write(self.style.SUCCESS(
                f'  add   {path.name} → id={photo.pk} slug={photo.slug} '
                f'({photo.width}×{photo.height})'
            ))
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f'done — {created} added, {skipped} skipped, {len(files)} scanned'
        ))

    @staticmethod
    def _slug_from(path: Path) -> str:
        from django.utils.text import slugify
        return slugify(path.stem)[:90] or 'photo'
