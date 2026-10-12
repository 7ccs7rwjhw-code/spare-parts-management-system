from django.db.models import Sum
from apps.accounts.policies import visible
from apps.requests.models import Line


def summary(user, year, month, filters=None):
    qs = Line.objects.filter(
        batch__in=visible(user).filter(
            year=year, month=month, effective=True, status="approved"
        ),
        confirmed=True,
        quantity__isnull=False,
    ).exclude(unit="")
    filters = filters or {}
    for key in [
        "customer",
        "equipment_name",
        "new_material_code",
        "material_attribute",
    ]:
        if filters.get(key):
            qs = qs.filter(**{f"values__{key}__icontains": filters[key]})
    if filters.get("requester"):
        qs = qs.filter(batch__requester_id=int(filters["requester"]))
    if filters.get("kind"):
        qs = qs.filter(batch__kind=filters["kind"])
    return (
        qs.values(
            "item_id",
            "values__new_material_code",
            "values__material_description",
            "values__customer",
            "values__equipment_name",
            "unit",
        )
        .annotate(total=Sum("quantity"))
        .order_by("unit", "values__new_material_code")
    )
