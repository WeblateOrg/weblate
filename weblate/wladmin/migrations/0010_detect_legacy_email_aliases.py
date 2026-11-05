# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import string
from typing import TYPE_CHECKING

from django.db import migrations, models
from django.db.models import F
from django.db.models.functions import Cast, Upper

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps


def detect_legacy_email_aliases(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    alias = schema_editor.connection.alias
    User = apps.get_model("weblate_auth", "User")
    VerifiedEmail = apps.get_model("accounts", "VerifiedEmail")
    SecurityScan = apps.get_model("wladmin", "SecurityScan")
    SecurityFinding = apps.get_model("wladmin", "SecurityFinding")
    SecurityFindingEvent = apps.get_model("wladmin", "SecurityFindingEvent")
    ascii_lower = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)

    # Cast to a plain character field so the custom e-mail lookup cannot
    # replace this deliberate reproduction of the old database comparison.
    candidates = (
        VerifiedEmail.objects.using(alias)
        .select_related("social__user")
        .exclude(social__user__email__isnull=True)
        .annotate(
            old_email=Upper(Cast(F("email"), models.CharField())),
            old_primary=Upper(Cast(F("social__user__email"), models.CharField())),
        )
        .filter(old_email=F("old_primary"))
        .order_by("pk")
    )
    scan = None
    affected: set[int] = set()
    for entry in candidates.iterator(chunk_size=500):
        primary = entry.social.user.email
        if not primary or entry.email.translate(ascii_lower) == primary.translate(
            ascii_lower
        ):
            continue
        if scan is None:
            bot, _ = User.objects.using(alias).get_or_create(
                username="weblate:alerts",
                defaults={
                    "email": None,
                    "full_name": "Automatic alerts",
                    "password": "!",
                    "is_active": False,
                    "is_bot": True,
                },
            )
            scan = SecurityScan.objects.using(alias).create(
                actor_id=bot.pk,
                operation="legacy-email-check",
                finding_type="legacy-email-alias",
                state="completed",
            )
        evidence = {
            "verified_email_id": entry.pk,
            "social_id": entry.social_id,
            "email": entry.email,
            "primary_email": primary,
            "provider": entry.social.provider,
            "matches": [{"identifier": entry.email, "method": "verified-email"}],
        }
        finding, _ = SecurityFinding.objects.using(alias).get_or_create(
            user_id=entry.social.user_id,
            finding_type="legacy-email-alias",
            key=str(entry.pk),
            defaults={"evidence": evidence},
        )
        SecurityFindingEvent.objects.using(alias).get_or_create(
            finding_id=finding.pk,
            scan_id=scan.pk,
            action="detected",
            defaults={"actor_id": scan.actor_id, "evidence": evidence},
        )
        scan.total += 1
        affected.add(entry.social.user_id)
    if scan is not None:
        scan.processed = scan.total
        scan.summary = {"accounts": len(affected), "matched": scan.total}
        scan.save(using=alias, update_fields=["processed", "total", "summary"])


class Migration(migrations.Migration):
    dependencies = [
        ("wladmin", "0009_securityscan_filename"),
        ("accounts", "0037_safe_verified_email_identity"),
        ("weblate_auth", "0017_safe_email_identity"),
    ]

    operations = [
        migrations.RunPython(detect_legacy_email_aliases, migrations.RunPython.noop)
    ]
