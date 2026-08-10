# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from urllib.parse import urlparse

from django.db import migrations

COMPONENT_SETTING_CHANGE = 96
BATCH_SIZE = 1000


def cleanup_repo_url(url: str) -> str:
    """Remove raw userinfo from a repository URL."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    userinfo, separator, _hostinfo = parsed.netloc.rpartition("@")
    if separator:
        return url.replace(f"//{userinfo}@", "//", 1)
    return url


def sanitize_repository_redirect_credentials(apps, schema_editor) -> None:
    Change = apps.get_model("trans", "Change")
    database_alias = schema_editor.connection.alias
    queryset = (
        Change.objects.using(database_alias)
        .filter(
            action=COMPONENT_SETTING_CHANGE,
            target__in=("repo", "push"),
            details__reason="http_redirect",
            details__field__in=("repo", "push"),
        )
        .only("id", "details")
    )
    pending = []
    for change in queryset.iterator(chunk_size=BATCH_SIZE):
        if not isinstance(change.details, dict):
            continue
        details = change.details.copy()
        for field in ("old", "target"):
            value = details.get(field)
            if isinstance(value, str):
                details[field] = cleanup_repo_url(value)
        if details == change.details:
            continue
        change.details = details
        pending.append(change)
        if len(pending) == BATCH_SIZE:
            Change.objects.using(database_alias).bulk_update(
                pending, ("details",), batch_size=BATCH_SIZE
            )
            pending.clear()
    if pending:
        Change.objects.using(database_alias).bulk_update(
            pending, ("details",), batch_size=BATCH_SIZE
        )


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0098_scrub_addon_change_details"),
    ]

    operations = [
        migrations.RunPython(
            sanitize_repository_redirect_credentials, migrations.RunPython.noop
        ),
    ]
