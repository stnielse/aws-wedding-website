"""Gallery views.

Renders the ordered Photo queryset into ``templates/gallery.html``, which
mounts the ``Gallery`` React island for the grid + lightbox UI. Photo
metadata (URLs, dims, captions) is serialized into an inline
``<script type="application/json" id="gallery-data">`` block — same
pattern as the RSVP island.
"""

import json

from django.shortcuts import render

from .models import Photo


def gallery_index(request):
    photos = [
        {
            'id': photo.pk,
            'slug': photo.slug,
            'src': photo.src,
            'srcset': photo.srcset,
            'width': photo.width,
            'height': photo.height,
            'caption': photo.caption,
            'alt': photo.alt_text or photo.caption or '',
        }
        for photo in Photo.objects.all()
        if photo.width and photo.height
    ]

    return render(
        request,
        'gallery.html',
        {
            'photos': photos,
            'photo_count': len(photos),
            'gallery_data_json': json.dumps({'photos': photos}),
        },
    )
