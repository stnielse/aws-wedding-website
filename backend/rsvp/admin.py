from django.contrib import admin

from .models import RSVP, Guest, Party


@admin.register(Party)
class PartyAdmin(admin.ModelAdmin):
    list_display = ('name', 'lookup_code')
    search_fields = ('name', 'lookup_code')


@admin.register(Guest)
class GuestAdmin(admin.ModelAdmin):
    list_display = ('name', 'party', 'plus_one_allowed', 'email')
    list_filter = ('plus_one_allowed',)
    search_fields = ('name', 'party__name', 'email')
    autocomplete_fields = ('party',)


@admin.register(RSVP)
class RSVPAdmin(admin.ModelAdmin):
    list_display = ('guest', 'attending', 'meal_choice', 'plus_one_attending', 'submitted_at')
    list_filter = ('attending', 'meal_choice', 'plus_one_attending')
    search_fields = ('guest__name', 'guest__party__name')
    autocomplete_fields = ('guest',)
