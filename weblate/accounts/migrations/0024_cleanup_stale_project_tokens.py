# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os

from django.contrib.auth.hashers import make_password
from django.db import migrations
from django.db.models import Exists, OuterRef


def cleanup_stale_project_tokens(apps, schema_editor) -> None:
    AuditLog = apps.get_model("accounts", "AuditLog")
    Profile = apps.get_model("accounts", "Profile")
    Subscription = apps.get_model("accounts", "Subscription")
    User = apps.get_model("weblate_auth", "User")
    Group = apps.get_model("weblate_auth", "Group")
    Token = apps.get_model("authtoken", "Token")

    defining_project_groups = Group.objects.filter(
        user=OuterRef("pk"), defining_project__isnull=False
    )
    stale_users = (
        User.objects.filter(
            is_bot=True,
            username__startswith="bot-",
            email__endswith="@bots.noreply.weblate.org",
        )
        .exclude(username__contains=":")
        .exclude(full_name="Deleted User")
        .annotate(has_defining_project_group=Exists(defining_project_groups))
        .filter(has_defining_project_group=False)
        .order_by("pk")
    )

    for user in stale_users.iterator():
        AuditLog.objects.create(
            user=user,
            activity="token-removed",
            params={"project": "unknown"},
            address=None,
            user_agent="",
        )

        user.username = f"deleted-{user.pk}"
        user.email = f"noreply+{user.pk}@weblate.org"
        while User.objects.filter(username=user.username).exclude(pk=user.pk).exists():
            user.username = f"deleted-{user.pk}-{os.urandom(5).hex()}"
        while User.objects.filter(email=user.email).exclude(pk=user.pk).exists():
            user.email = f"noreply+{user.pk}-{os.urandom(5).hex()}@weblate.org"

        user.full_name = "Deleted User"
        user.is_active = False
        user.password = make_password(None)
        user.save(
            update_fields=["username", "email", "full_name", "is_active", "password"]
        )

        user.social_auth.all().delete()
        user.groups.clear()
        user.administered_group_set.clear()
        user.memory_set.all().delete()

        Subscription.objects.filter(user_id=user.pk).delete()

        try:
            profile = Profile.objects.get(user_id=user.pk)
        except Profile.DoesNotExist:
            profile = None
        if profile is not None:
            profile.watched.clear()
            profile.website = ""
            profile.liberapay = ""
            profile.fediverse = ""
            profile.codesite = ""
            profile.github = ""
            profile.twitter = ""
            profile.linkedin = ""
            profile.location = ""
            profile.company = ""
            profile.public_email = ""
            profile.save()

        Token.objects.filter(user_id=user.pk).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0023_alter_profile_contribute_personal_tm"),
        ("weblate_auth", "0008_userblock_note"),
    ]

    operations = [
        migrations.RunPython(
            cleanup_stale_project_tokens, migrations.RunPython.noop, elidable=True
        ),
    ]
