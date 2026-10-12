import io, csv, json
from pathlib import Path
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import HttpResponse, JsonResponse
from django.core.exceptions import PermissionDenied, ValidationError, ObjectDoesNotExist
from django.db import transaction, connection
from django.db.models import Q
from django.conf import settings
from django.contrib import messages
from .models import *
from .forms import *
from .services import *
from .excel import ingest, export_workbook, FIELDS, apply_catalog


def guarded(fn):
    from functools import wraps

    @wraps(fn)
    def wrap(request, *a, **k):
        try:
            return fn(request, *a, **k)
        except Conflict as e:
            return render(request, "core/error.html", {"error": str(e)}, status=409)
        except ObjectDoesNotExist:
            return render(
                request, "core/error.html", {"error": "记录不存在"}, status=404
            )
        except KeyError:
            return render(
                request, "core/error.html", {"error": "缺少必需参数"}, status=400
            )
        except (ValidationError, ValueError) as e:
            return render(request, "core/error.html", {"error": str(e)}, status=400)

    return wrap


def page(request, title, **ctx):
    return render(
        request, "core/page.html", dict(title=title, role=role(request.user), **ctx)
    )


@login_required
@guarded
def home(request):
    q = visible(request.user).select_related("requester").order_by("-created_at")
    for k in ["year", "month", "status", "kind"]:
        if request.GET.get(k):
            q = q.filter(**{k: request.GET[k]})
    from django.core.paginator import Paginator

    return page(
        request,
        "月度申请",
        batches=Paginator(q, 100).get_page(request.GET.get("page")),
        batch_form=BatchForm(),
        filters=True,
    )


@login_required
@guarded
def batch_new(request):
    form = BatchForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        b = form.save(commit=False)
        b.requester = request.user
        b.department = department(request.user)
        b.save()
        event(request.user, b, "create", {})
        return redirect("detail", b.pk)
    return page(request, "新建申请", form=form)


@login_required
@guarded
def detail(request, pk):
    b = get_object_or_404(visible(request.user), pk=pk)
    from .diffs import line_changes

    records = list(b.events.order_by("-id"))
    for e in records:
        e.changes = (
            line_changes(e.before["lines"], e.after["lines"])
            if "lines" in e.before and "lines" in e.after
            else []
        )
    form = LineForm(initial={"lock_version": b.lock_version})
    return page(
        request,
        f"{b.year}年{b.month}月 · {b.get_kind_display()}",
        batch=b,
        batch_candidates=Batch.objects.filter(
            requester=b.requester, year=b.year, month=b.month, kind=b.kind
        ).exclude(pk=b.pk),
        lines=b.lines.select_related("item", "source_row").order_by("id"),
        events=records,
        line_form=form,
        fields=list(zip(FIELDS, HEADERS)),
    )


@login_required
@guarded
def edit_line(request, pk, lid=None):
    b = get_object_or_404(visible(request.user), pk=pk)
    may_edit(request.user, b)
    line = get_object_or_404(b.lines, pk=lid) if lid else None
    initial = dict(line.values) if line else {}
    initial.update(
        lock_version=b.lock_version,
        item=line.item if line else None,
        unit=line.unit if line else "",
        confirmed=line.confirmed if line else False,
    )
    form = LineForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        save_line(
            request.user,
            b.pk,
            d["lock_version"],
            {k: d[k] for k in FIELDS},
            d["unit"],
            line.pk if line else None,
            d["item"].pk if d["item"] else None,
            d["confirmed"],
        )
        return redirect("detail", b.pk)
    return page(request, "编辑申请明细", form=form, item_picker=True)


@login_required
@require_POST
@guarded
def remove_line(request, pk, lid):
    delete_line(request.user, pk, request.POST["lock_version"], lid)
    return redirect("detail", pk)


@login_required
@require_POST
@guarded
def action(request, pk, act):
    if act == "effective":
        select_effective(
            request.user,
            pk,
            request.POST["lock_version"],
            request.POST.getlist("other_ids"),
            request.POST.get("comment", ""),
        )
    else:
        transition(
            request.user,
            pk,
            request.POST["lock_version"],
            act,
            request.POST.get("comment", ""),
        )
    return redirect("detail", pk)


@login_required
@guarded
def copy_batch(request, pk, revision=False):
    b = get_object_or_404(visible(request.user), pk=pk)
    form = CopyForm(
        request.POST or None,
        initial={"year": b.year, "month": b.month, "lock_version": b.lock_version},
    )
    if request.method == "POST" and form.is_valid():
        new = clone(
            request.user,
            pk,
            form.cleaned_data["lock_version"],
            form.cleaned_data["year"],
            form.cleaned_data["month"],
            revision,
        )
        return redirect("detail", new.pk)
    return page(request, "创建修订" if revision else "复制为新月份草稿", form=form)


@login_required
def items(request):
    q = Item.objects.all().order_by("category", "new_code", "id")
    if request.GET.get("q"):
        s = request.GET["q"]
        q = q.filter(
            Q(new_code__icontains=s)
            | Q(old_code__icontains=s)
            | Q(description__icontains=s)
            | Q(aliases__code__icontains=s)
            | Q(sourcerow__sheet__icontains=s)
        ).distinct()
    from django.core.paginator import Paginator

    return page(
        request,
        "备件资料",
        items=Paginator(q, 40).get_page(request.GET.get("page")),
        search=True,
    )


@login_required
@guarded
def item_edit(request, pk=None):
    admin_only(request.user)
    obj = get_object_or_404(Item, pk=pk) if pk else None
    form = ItemForm(
        request.POST or None,
        instance=obj,
        initial={"version": obj.version if obj else 1},
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            before = {}
            if obj:
                locked = Item.objects.select_for_update().get(pk=pk)
                if locked.version != form.cleaned_data["version"]:
                    raise Conflict("配件资料已更新，请刷新")
                before = Item.objects.filter(pk=pk).values().first()
                before["id"] = str(before["id"])
            changed = form.save(commit=False)
            changed.version = (obj.version if obj else 0) + 1
            changed.save()
            changed.aliases.update(verified=changed.verified)
            for field, kind in [("new_code", "new"), ("old_code", "old")]:
                code = getattr(changed, field)
                if code and code not in INVALID_CODES:
                    Alias.objects.get_or_create(
                        item=changed,
                        code=code,
                        kind=kind,
                        defaults={"verified": changed.verified},
                    )
            Audit.objects.create(
                actor=request.user,
                target=f"item:{changed.pk}",
                action="edit_item",
                before=before,
                after={k: str(v) for k, v in form.cleaned_data.items()},
            )
        return redirect("items")
    return page(
        request,
        "编辑备件",
        form=form,
        source_rows=SourceRow.objects.filter(item=obj) if obj else [],
    )


@login_required
def item_json(request, pk):
    x = get_object_or_404(Item, pk=pk, active=True)
    return JsonResponse(
        {
            "new_material_code": x.new_code,
            "old_material_code": x.old_code,
            "material_description": x.description,
            "equipment_name": x.equipment,
            "unit": x.unit,
        }
    )


@login_required
@guarded
def imports(request):
    admin_only(request.user)
    form = UploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        f = form.cleaned_data["file"]
        if not f.name.lower().endswith(".xlsx") or f.size > 25 * 1024 * 1024:
            raise ValidationError("只支持25MB以内XLSX")
        src, new = ingest(
            f.read(), Path(f.name).name, request.user, form.cleaned_data["catalog"]
        )
        if not new:
            messages.info(request, "相同SHA-256已存在，本次没有新增业务行")
        return redirect("import_detail", src.pk)
    return page(
        request,
        "导入中心 · 上传后先预览，逐工作表确认",
        form=form,
        sources=SourceFile.objects.order_by("-id"),
    )


@login_required
@guarded
def import_detail(request, pk):
    admin_only(request.user)
    f = get_object_or_404(SourceFile, pk=pk)
    form = ConfirmForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        mapping = {
            k: int(d[k]) for k in ["factory_stock", "outstanding_qty"] if d[k] != ""
        }
        b = confirm_sheet(
            request.user,
            pk,
            d["sheet"],
            d["year"],
            d["month"],
            d["requester"],
            d["department"],
            d["reason"],
            mapping,
        )
        return redirect("detail", b.pk)
    from django.core.paginator import Paginator

    return page(
        request,
        "导入预览 / 原行与异常",
        form=None if f.catalog else form,
        source=f,
        source_rows=Paginator(f.rows.order_by("sheet", "row"), 100).get_page(
            request.GET.get("page")
        ),
        sheet_stats=(
            Audit.objects.filter(target=f"source:{f.pk}", action="preview_import")
            .order_by("id")
            .first()
            .after.get("sheets", [])
            if Audit.objects.filter(
                target=f"source:{f.pk}", action="preview_import"
            ).exists()
            else list(f.rows.values("sheet", "template").distinct())
        ),
    )


@login_required
@guarded
def issues_csv(request, pk):
    admin_only(request.user)
    f = get_object_or_404(SourceFile, pk=pk)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["sheet", "row", "status", "issues", "original_values"])

    def safe(v):
        t = str(v)
        return "'" + t if t.startswith(("=", "+", "-", "@")) else t

    for r in f.rows.order_by("sheet", "row"):
        w.writerow(
            [
                safe(r.sheet),
                r.row,
                r.status,
                safe(json.dumps(r.issues, ensure_ascii=False)),
                safe(json.dumps(r.original_values, ensure_ascii=False)),
            ]
        )
    res = HttpResponse(
        "\ufeff" + out.getvalue(), content_type="text/csv; charset=utf-8"
    )
    res["Content-Disposition"] = 'attachment; filename="import_rows.csv"'
    return res


@login_required
@guarded
def original(request, pk):
    admin_only(request.user)
    f = get_object_or_404(SourceFile, pk=pk)
    from django.http import FileResponse

    return FileResponse(
        f.original.open("rb"),
        as_attachment=True,
        filename="source_" + f.sha256 + ".xlsx",
    )


@login_required
@guarded
def reports(request):
    from django.utils import timezone

    now = timezone.localdate()
    year = int(request.GET.get("year", now.year))
    month = int(request.GET.get("month", now.month))
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        raise ValueError("非法年月")
    return page(
        request,
        "生效版本月度汇总（数量按单位分组）",
        totals=summary(request.user, year, month, request.GET),
        report=True,
        year=year,
        month=month,
    )


@login_required
@guarded
def export(request):
    year = int(request.GET["year"])
    month = int(request.GET["month"])
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        raise ValueError("非法年月")
    q = visible(request.user).filter(
        year=year, month=month, effective=True, status="approved"
    )
    if request.GET.get("batch"):
        q = visible(request.user).filter(pk=int(request.GET["batch"]))
        if not q.exists() or any(b.year != year or b.month != month for b in q):
            raise PermissionDenied
    data = export_workbook(
        q, year, month, settings.BASE_DIR / "templates/default21.xlsx"
    )
    res = HttpResponse(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    res["Content-Disposition"] = f'attachment; filename="spares_{year}_{month}.xlsx"'
    return res


@login_required
@guarded
def queue(request):
    admin_only(request.user)
    from django.core.paginator import Paginator

    return page(
        request,
        "数据质量 / 待关联队列",
        queue_lines=Paginator(
            Line.objects.filter(item=None)
            .select_related("batch", "source_row")
            .order_by("id"),
            100,
        ).get_page(request.GET.get("page")),
        source_rows=Paginator(
            SourceRow.objects.exclude(issues=[]).order_by("source_id", "sheet", "row"),
            100,
        ).get_page(request.GET.get("page")),
    )


@login_required
@guarded
def bind(request, pk):
    admin_only(request.user)
    l = get_object_or_404(Line, pk=pk)
    form = BindForm(
        request.POST or None, initial={"lock_version": l.batch.lock_version}
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            b = Batch.objects.select_for_update().get(pk=l.batch_id)
            may_edit(request.user, b)
            checked(b, form.cleaned_data["lock_version"])
            before = {"line": l.pk, "item": str(l.item_id)}
            l.item = form.cleaned_data["item"]
            l.save(update_fields=["item"])
            b.lock_version += 1
            b.save()
            event(request.user, b, "bind_item", before)
        return redirect("queue")
    return page(request, "绑定主资料（已提交/批准单须先退回/修订）", form=form)


@login_required
@guarded
def audit(request):
    admin_only(request.user)
    return page(
        request,
        "操作审计",
        audits=Audit.objects.order_by("-id")[:200],
        events=Event.objects.order_by("-id")[:200],
    )


def health(request):
    from django.db.utils import OperationalError

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except OperationalError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


@login_required
@require_POST
@guarded
def catalog_commit(request, pk):
    admin_only(request.user)
    apply_catalog(pk, request.user)
    return redirect("import_detail", pk)
