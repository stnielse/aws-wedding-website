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
    name = models.CharField(max_length=200)  # e.g. "Crate & Barrel"
    url = models.URLField()
    order = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.name
