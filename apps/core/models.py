"""Compatibility names for the imported candidate's views and regression tests.

Model ownership and migrations live in the five business apps.
"""

from apps.accounts.models import Profile, Audit
from apps.inventory.models import (
    Equipment,
    InventorySnapshot,
    SourceFile,
    SourceLocation,
    Item,
    SourceRow,
    Alias,
)
from apps.requests.models import Batch, Line
from apps.approvals.models import Event
