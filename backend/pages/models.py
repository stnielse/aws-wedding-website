from django.db import models


class FAQ(models.Model):
    question = models.CharField(max_length=500)
    answer = models.TextField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.question


class RegistryLink(models.Model):
    name = models.CharField(max_length=200)   # e.g. "Crate & Barrel"
    url = models.URLField()
    order = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.name


class HotelBlock(models.Model):
    hotel_name = models.CharField(max_length=200)
    address = models.TextField()
    booking_url = models.URLField(blank=True)
    booking_code = models.CharField(max_length=100, blank=True)
    rate = models.CharField(max_length=100, blank=True)  # e.g. "$189/night"
    cutoff_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return self.hotel_name
