from django.contrib import admin

from .models import FAQ, RegistryLink, HotelBlock

admin.site.register(FAQ)
admin.site.register(RegistryLink)
admin.site.register(HotelBlock)
