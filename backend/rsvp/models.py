from django.db import models


class Guest(models.Model):
    name = models.CharField(max_length=200)
    lookup_code = models.CharField(max_length=20, unique=True)  # printed on invite
    email = models.EmailField(blank=True)
    plus_one_allowed = models.BooleanField(default=False)


class RSVP(models.Model):
    guest = models.OneToOneField(Guest, on_delete=models.CASCADE)
    attending = models.BooleanField()
    meal_choice = models.CharField(max_length=100, blank=True)
    plus_one_attending = models.BooleanField(default=False)
    plus_one_name = models.CharField(max_length=200, blank=True)
    plus_one_meal = models.CharField(max_length=100, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
