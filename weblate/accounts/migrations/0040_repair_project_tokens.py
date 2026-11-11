# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.hashers import make_password
from django.db import migrations
from django.db.models import Exists, OuterRef

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps


def repair_project_tokens(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    db_alias = schema_editor.connection.alias
    User = apps.get_model("weblate_auth", "User")
    Group = apps.get_model("weblate_auth", "Group")
    TeamMembership = apps.get_model("weblate_auth", "TeamMembership")
    Token = apps.get_model("authtoken", "Token")
    AuditLog = apps.get_model("accounts", "AuditLog")
    group_admin = Group.admins.through

    # Display names are editable, including the name used for deleted accounts.
    project_tokens = (
        User.objects.using(db_alias)
        .filter(
            is_bot=True,
            username__startswith="bot-",
            email__endswith="@bots.noreply.weblate.org",
        )
        .exclude(username__contains=":")
    )
    token_ids = project_tokens.values_list("pk", flat=True)
    TeamMembership.objects.using(db_alias).filter(
        user_id__in=token_ids, group__defining_project__isnull=True
    ).delete()
    group_admin.objects.using(db_alias).filter(
        user_id__in=token_ids, group__defining_project__isnull=True
    ).delete()

    project_memberships = TeamMembership.objects.using(db_alias).filter(
        user_id=OuterRef("pk"), group__defining_project__isnull=False
    )
    orphaned = (
        project_tokens.annotate(has_project=Exists(project_memberships))
        .filter(has_project=False)
        .order_by("pk")
    )
    for user in orphaned.iterator():
        tokens = Token.objects.using(db_alias).filter(user_id=user.pk)
        # Avoid duplicate audit records on repeated runs or already revoked bots.
        if user.is_active or tokens.exists():
            AuditLog.objects.using(db_alias).create(
                user_id=user.pk,
                activity="token-removed",
                params={"project": "unknown"},
                address=None,
                user_agent="",
            )
        tokens.delete()
        User.objects.using(db_alias).filter(pk=user.pk).update(
            is_active=False, password=make_password(None), date_expires=None
        )
        TeamMembership.objects.using(db_alias).filter(user_id=user.pk).delete()
        group_admin.objects.using(db_alias).filter(user_id=user.pk).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0039_alter_auditlog_activity"),
        ("weblate_auth", "0020_invitation_team_admin"),
        ("authtoken", "0004_alter_tokenproxy_options"),
    ]

    operations = [
        migrations.RunPython(repair_project_tokens, migrations.RunPython.noop),
    ]
