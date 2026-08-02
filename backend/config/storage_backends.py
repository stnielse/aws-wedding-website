"""Custom Django storage backends.

``ManifestS3StaticStorage`` composes django-storages' ``S3StaticStorage``
with Django's ``ManifestFilesMixin`` so ``collectstatic`` hashes filenames
AND uploads them to S3 in one pass. MRO order matters: the mixin has to
appear first so its ``post_process`` step runs before the upload.

django-storages 1.14+ used to ship an ``S3ManifestStaticStorage`` for
exactly this composition, but it was removed in favor of the one-line
subclass since ``ManifestFilesMixin`` is a stable public API.
"""

from django.contrib.staticfiles.storage import ManifestFilesMixin
from storages.backends.s3 import S3StaticStorage


class ManifestS3StaticStorage(ManifestFilesMixin, S3StaticStorage):
    pass
