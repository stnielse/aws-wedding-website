from django.db import models


MEAL_CHOICES = [
    ('short_rib', 'Braised short rib'),
    ('trout', 'Trout, almondine'),
    ('farrotto', 'Wild mushroom farrotto'),
]


class Party(models.Model):
    name = models.CharField(max_length=200)
    lookup_code = models.CharField(max_length=20, unique=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = 'parties'

    def save(self, *args, **kwargs):
        self.lookup_code = self.lookup_code.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Guest(models.Model):
    party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name='guests')
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    plus_one_allowed = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class RSVP(models.Model):
    guest = models.OneToOneField(Guest, on_delete=models.CASCADE)
    attending = models.BooleanField()
    meal_choice = models.CharField(max_length=100, blank=True, choices=MEAL_CHOICES)
    plus_one_attending = models.BooleanField(default=False)
    plus_one_name = models.CharField(max_length=200, blank=True)
    plus_one_meal = models.CharField(max_length=100, blank=True, choices=MEAL_CHOICES)
    submitted_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f'RSVP: {self.guest.name}'
