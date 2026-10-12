from .excel import FIELDS, HEADERS

LABELS = dict(zip(FIELDS, HEADERS)) | {
    "quantity": "解析数量",
    "unit": "单位",
    "item_id": "关联物料",
    "confirmed": "人工确认",
    "raw_quantity": "原始数量",
}


def line_changes(before, after):
    old = {r.get("id", f"legacy-{i}"): r for i, r in enumerate(before)}
    new = {r.get("id", f"legacy-{i}"): r for i, r in enumerate(after)}
    changes = []
    for key in dict.fromkeys(list(old) + list(new)):
        a = old.get(key)
        b = new.get(key)
        if a is None or b is None:
            r = b or a
            changes.append(
                {
                    "line": key,
                    "field": "新增行" if a is None else "删除行",
                    "before": ""
                    if a is None
                    else r.get("values", {}).get("material_description", ""),
                    "after": r.get("values", {}).get("material_description", "")
                    if a is None
                    else "",
                }
            )
            continue
        for field in FIELDS + [
            "quantity",
            "unit",
            "item_id",
            "confirmed",
            "raw_quantity",
        ]:
            av = a.get("values", {}).get(field, "") if field in FIELDS else a.get(field)
            bv = b.get("values", {}).get(field, "") if field in FIELDS else b.get(field)
            if av != bv:
                changes.append(
                    {"line": key, "field": LABELS[field], "before": av, "after": bv}
                )
    return changes
