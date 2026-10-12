from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from apps.accounts.models import Profile, Audit
from apps.requests.models import Batch


def role(user):
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied("需要有效登录账户")
    if user.is_superuser:
        return "admin"
    p = Profile.objects.filter(user=user).first()
    return p.role if p else "requester"


def department(user):
    p = Profile.objects.filter(user=user).first()
    return p.department if p else ""


def admin_only(user):
    if role(user) != "admin":
        Audit.objects.create(actor=user, target="authorization", action="denied_admin")
        raise PermissionDenied("需要管理员权限")


def visible(user):
    q = Batch.objects.all()
    if role(user) == "admin":
        return q
    if role(user) == "reviewer" and department(user):
        return q.filter(
            Q(requester=user)
            | Q(
                department=department(user),
                status__in=["submitted", "approved", "returned"],
            )
        )
    return q.filter(requester=user)


def may_edit(user, b):
    if role(user) != "admin" and b.requester_id != user.pk:
        raise PermissionDenied("无权修改此申请")
    if b.status not in ["draft", "returned"]:
        raise ValidationError("此状态不可修改，请创建修订")
