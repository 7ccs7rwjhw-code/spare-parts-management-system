from django.db import transaction
from django.db.models import Q
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from apps.requests.models import Batch
from apps.requests.services import checked
from apps.accounts.policies import role, department, may_edit
from .audit import event


@transaction.atomic
def transition(user, bid, version, action, comment=""):
    b = Batch.objects.select_for_update().get(pk=bid)
    checked(b, version)
    before = {"status": b.status, "lock_version": b.lock_version}
    if action == "submit":
        may_edit(user, b)
        if not b.lines.exists():
            raise ValidationError("空单不能提交")
        if b.lines.filter(
            Q(quantity__isnull=True) | Q(confirmed=False) | Q(unit="")
        ).exists():
            raise ValidationError("请确认全部数量和单位后提交")
        b.status = "submitted"
        b.submitted_at = timezone.now()
    elif action in ["approve", "return"]:
        if role(user) not in ["admin", "reviewer"] or (
            role(user) == "reviewer"
            and (not department(user) or department(user) != b.department)
        ):
            raise PermissionDenied("无权审核此部门")
        if b.status != "submitted":
            raise ValidationError("只可审核已提交记录")
        if b.requester_id == user.pk and role(user) != "admin":
            raise PermissionDenied("不能审核自己的申请")
        if action == "return" and (not comment.strip()):
            raise ValidationError("退回理由必填")
        b.status = "approved" if action == "approve" else "returned"
        b.reviewed_at = timezone.now()
    else:
        raise ValidationError("无效动作")
    b.lock_version += 1
    b.save()
    event(user, b, action, before, comment)
    return b
