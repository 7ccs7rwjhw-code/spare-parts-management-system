import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(
        max_length=20,
        choices=[("requester", "申请人"), ("reviewer", "审核人"), ("admin", "管理员")],
        default="requester",
    )
    department = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(role__in=["requester", "reviewer", "admin"]),
                name="valid_profile_role",
            )
        ]


class Audit(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT
    )
    target = models.CharField(max_length=150)
    action = models.CharField(max_length=50)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
