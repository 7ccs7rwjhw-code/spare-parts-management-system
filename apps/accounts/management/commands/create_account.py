import getpass
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from apps.accounts.models import Profile, Audit
from django.db import transaction


class Command(BaseCommand):
    help = (
        "Create named account; password securely entered at prompt, never command line."
    )

    def add_arguments(self, p):
        p.add_argument("username")
        p.add_argument(
            "--role", choices=["requester", "reviewer", "admin"], default="requester"
        )
        p.add_argument("--department", default="")

    @transaction.atomic
    def handle(self, *a, **o):
        pw = getpass.getpass("密码: ")
        if pw != getpass.getpass("重复密码: "):
            raise CommandError("密码不一致")
        validate_password(pw)
        u = get_user_model().objects.create_user(
            username=o["username"],
            password=pw,
            is_staff=o["role"] == "admin",
            is_superuser=o["role"] == "admin",
        )
        Profile.objects.create(user=u, role=o["role"], department=o["department"])
        Audit.objects.create(
            actor=u,
            target=f"user:{u.pk}",
            action="create_account",
            after={"role": o["role"], "department": o["department"]},
        )
        self.stdout.write("账号创建成功")
