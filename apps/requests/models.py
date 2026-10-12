import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Batch(models.Model):
    year = models.PositiveIntegerField()
    month = models.PositiveSmallIntegerField()
    kind = models.CharField(
        max_length=30,
        choices=[("spare_purchase", "备件购买"), ("department_purchase", "部门自购")],
    )
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    department = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=20,
        default="draft",
        choices=[
            ("draft", "草稿"),
            ("submitted", "已提交"),
            ("approved", "已批准"),
            ("returned", "退回"),
        ],
    )
    version = models.PositiveIntegerField(default=1)
    lock_version = models.PositiveIntegerField(default=1)
    family = models.UUIDField(default=uuid.uuid4, editable=False)
    effective = models.BooleanField(default=False)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    source = models.ForeignKey(
        "inventory.SourceFile", null=True, blank=True, on_delete=models.PROTECT
    )
    source_sheet = models.CharField(max_length=150, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(month__gte=1, month__lte=12), name="valid_batch_month"
            ),
            models.CheckConstraint(
                condition=Q(year__gte=2000, year__lte=2100), name="valid_batch_year"
            ),
            models.UniqueConstraint(
                fields=["source", "source_sheet"],
                condition=Q(source__isnull=False, parent__isnull=True),
                name="one_import_per_sheet",
            ),
            models.UniqueConstraint(
                fields=["family"],
                condition=Q(effective=True),
                name="one_effective_family",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["draft", "submitted", "approved", "returned"]),
                name="valid_batch_status",
            ),
            models.CheckConstraint(
                condition=Q(kind__in=["spare_purchase", "department_purchase"]),
                name="valid_batch_kind",
            ),
            models.CheckConstraint(
                condition=Q(effective=False) | Q(status="approved"),
                name="effective_requires_approved",
            ),
            models.UniqueConstraint(
                fields=["family", "version"], name="unique_family_version"
            ),
            models.CheckConstraint(
                condition=Q(version__gte=1, lock_version__gte=1),
                name="positive_batch_versions",
            ),
        ]


class Line(models.Model):
    batch = models.ForeignKey(
        "requests.Batch", on_delete=models.CASCADE, related_name="lines"
    )
    item = models.ForeignKey(
        "inventory.Item", null=True, blank=True, on_delete=models.PROTECT
    )
    source_row = models.ForeignKey(
        "inventory.SourceRow", null=True, blank=True, on_delete=models.PROTECT
    )
    values = models.JSONField(default=dict)
    raw_quantity = models.TextField(blank=True)
    quantity = models.DecimalField(
        max_digits=20, decimal_places=6, null=True, blank=True
    )
    unit = models.CharField(max_length=30, blank=True)
    confirmed = models.BooleanField(default=False)
    safety_stock = models.DecimalField(
        max_digits=20, decimal_places=6, null=True, blank=True
    )
    machine_count_per_line = models.DecimalField(
        max_digits=20, decimal_places=6, null=True, blank=True
    )
    usage_per_machine = models.DecimalField(
        max_digits=20, decimal_places=6, null=True, blank=True
    )
    lifetime_months = models.DecimalField(
        max_digits=20, decimal_places=6, null=True, blank=True
    )
    theoretical_monthly_qty = models.DecimalField(
        max_digits=20, decimal_places=6, null=True, blank=True
    )
    previous_month_actual_qty = models.DecimalField(
        max_digits=20, decimal_places=6, null=True, blank=True
    )
    factory_stock = models.DecimalField(
        max_digits=20, decimal_places=6, null=True, blank=True
    )
    outstanding_qty = models.DecimalField(
        max_digits=20, decimal_places=6, null=True, blank=True
    )
    nvb2 = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    required_purchase_qty = models.DecimalField(
        max_digits=20, decimal_places=6, null=True, blank=True
    )

    equipment_record = models.ForeignKey(
        "inventory.Equipment", null=True, blank=True, on_delete=models.PROTECT
    )
    old_material_code = models.TextField(blank=True)
    new_material_code = models.TextField(blank=True)
    material_description = models.TextField(blank=True)
    equipment_name = models.TextField(blank=True)
    material_attribute = models.TextField(blank=True)
    line_name = models.TextField(blank=True)
    customer = models.TextField(blank=True)
    section_manager = models.TextField(blank=True)
    remark = models.TextField(blank=True)
    order_number = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        # Text columns are searchable projections of the preserved business snapshot.
        text_fields = [
            "old_material_code",
            "new_material_code",
            "material_description",
            "equipment_name",
            "material_attribute",
            "line_name",
            "customer",
            "section_manager",
            "remark",
            "order_number",
        ]
        for field in text_fields:
            value = self.values.get(field, "")
            setattr(self, field, "" if value is None else str(value))
        if kwargs.get("update_fields") and "values" in kwargs["update_fields"]:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | set(text_fields)
        super().save(*args, **kwargs)

    @property
    def forecast_qty(self):
        return self.quantity

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__isnull=True) | Q(quantity__gte=0),
                name="nonnegative_quantity",
            )
        ]
