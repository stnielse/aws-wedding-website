from django.contrib import admin

from .models import Photo


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'order', 'uploaded_at')
    search_fields = ('caption', 'alt_text')
    ordering = ('order', 'uploaded_at')
