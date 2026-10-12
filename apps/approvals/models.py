import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Event(models.Model):
    batch = models.ForeignKey(
        "requests.Batch", on_delete=models.PROTECT, related_name="events"
    )
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=40)
    comment = models.TextField(blank=True)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
