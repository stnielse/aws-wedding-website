from django.contrib import admin

from .models import FAQ, HotelBlock, RegistryLink

admin.site.register(FAQ)
admin.site.register(RegistryLink)
admin.site.register(HotelBlock)
