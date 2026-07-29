from django.db import models


class Photo(models.Model):
    image = models.ImageField(upload_to='gallery/')  # goes to S3 in production
    caption = models.CharField(max_length=300, blank=True)
    alt_text = models.CharField(max_length=300, blank=True)
    order = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'uploaded_at']

    def __str__(self):
        return self.caption or self.image.name
