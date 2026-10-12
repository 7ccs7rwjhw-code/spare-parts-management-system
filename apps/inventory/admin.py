from django.contrib import admin
from apps.core.admin import EvidenceAdmin
from .models import (
    Equipment,
    Item,
    Alias,
    SourceFile,
    SourceLocation,
    SourceRow,
    InventorySnapshot,
)

for model in [
    Equipment,
    Item,
    Alias,
    SourceFile,
    SourceLocation,
    SourceRow,
    InventorySnapshot,
]:
    admin.site.register(model, EvidenceAdmin)
