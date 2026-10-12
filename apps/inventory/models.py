import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Equipment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=150)
    model = models.CharField(max_length=150, blank=True)
    brand = models.CharField(max_length=150, blank=True)
    location = models.CharField(max_length=150, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.code} {self.name}"


class InventorySnapshot(models.Model):
    item = models.ForeignKey("inventory.Item", on_delete=models.PROTECT)
    source_row = models.ForeignKey(
        "inventory.SourceRow", null=True, blank=True, on_delete=models.PROTECT
    )
    year = models.PositiveIntegerField()
    month = models.PositiveSmallIntegerField()
    warehouse = models.CharField(max_length=100, blank=True)
    unit = models.CharField(max_length=30)
    stock_qty = models.DecimalField(
        max_digits=20, decimal_places=6, null=True, blank=True
    )
    on_order_qty = models.DecimalField(
        max_digits=20, decimal_places=6, null=True, blank=True
    )
    as_of = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(year__gte=2000, year__lte=2100), name="valid_snapshot_year"
            ),
            models.CheckConstraint(
                condition=Q(month__gte=1, month__lte=12), name="valid_snapshot_month"
            ),
            models.CheckConstraint(
                condition=Q(stock_qty__isnull=True) | Q(stock_qty__gte=0),
                name="nonnegative_snapshot_stock",
            ),
            models.CheckConstraint(
                condition=Q(on_order_qty__isnull=True) | Q(on_order_qty__gte=0),
                name="nonnegative_snapshot_order",
            ),
            models.CheckConstraint(
                condition=~Q(unit=""), name="snapshot_unit_required"
            ),
            models.UniqueConstraint(
                fields=["item", "year", "month", "warehouse", "unit"],
                name="unique_inventory_snapshot",
            ),
        ]


class SourceFile(models.Model):
    sha256 = models.CharField(max_length=64, unique=True)
    file_name = models.CharField(max_length=255)
    original = models.FileField(upload_to="originals/")
    catalog = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)


class SourceLocation(models.Model):
    source = models.ForeignKey(
        "inventory.SourceFile", on_delete=models.CASCADE, related_name="locations"
    )
    path = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "path"], name="unique_source_path"
            )
        ]


class Item(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    new_code = models.CharField(max_length=150, blank=True, db_index=True)
    old_code = models.CharField(max_length=150, blank=True, db_index=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, blank=True)
    equipment = models.CharField(max_length=150, blank=True)
    brand = models.CharField(max_length=150, blank=True)
    location = models.CharField(max_length=150, blank=True)
    unit = models.CharField(max_length=30, blank=True)
    verified = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    equipment_record = models.ForeignKey(
        "inventory.Equipment", null=True, blank=True, on_delete=models.PROTECT
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.new_code or self.old_code or '待确认'} {self.description[:70]}"


class SourceRow(models.Model):
    source = models.ForeignKey(
        "inventory.SourceFile", on_delete=models.PROTECT, related_name="rows"
    )
    sheet = models.CharField(max_length=150)
    row = models.PositiveIntegerField()
    original_values = models.JSONField()
    headers = models.JSONField(default=list)
    cached_values = models.JSONField(default=list)
    mapped = models.JSONField(default=dict)
    issues = models.JSONField(default=list)
    status = models.CharField(max_length=30)
    template = models.CharField(max_length=30)
    month_candidates = models.JSONField(default=dict)
    item = models.ForeignKey(
        "inventory.Item", null=True, blank=True, on_delete=models.PROTECT
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "sheet", "row"], name="unique_source_row"
            )
        ]


class Alias(models.Model):
    item = models.ForeignKey(
        "inventory.Item", on_delete=models.PROTECT, related_name="aliases"
    )
    code = models.CharField(max_length=150, db_index=True)
    kind = models.CharField(max_length=30)
    verified = models.BooleanField(default=False)
    source_row = models.ForeignKey(
        "inventory.SourceRow", null=True, on_delete=models.PROTECT
    )
