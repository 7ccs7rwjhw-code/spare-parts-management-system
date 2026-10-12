from django.contrib import admin
from apps.core.admin import EvidenceAdmin
from .models import Event

admin.site.register(Event, EvidenceAdmin)
