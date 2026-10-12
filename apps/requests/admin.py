from django.contrib import admin
from apps.core.admin import EvidenceAdmin
from .models import Batch, Line

admin.site.register(Batch, EvidenceAdmin)
admin.site.register(Line, EvidenceAdmin)
