from django.contrib import admin
from django.db import transaction

from apps.core.admin import EvidenceAdmin
from .models import Audit, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "role", "department"]

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        before = {}
        if change:
            previous = Profile.objects.select_for_update().get(pk=obj.pk)
            before = {"role": previous.role, "department": previous.department}
        super().save_model(request, obj, form, change)
        Audit.objects.create(
            actor=request.user,
            target=f"profile:{obj.pk}",
            action="change_role",
            before=before,
            after={"role": obj.role, "department": obj.department},
        )

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Audit, EvidenceAdmin)
