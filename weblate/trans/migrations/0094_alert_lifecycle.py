# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


def backfill_dismissals(alerts) -> None:
    # Import the current model because historical migration models do not expose
    # the component helpers used by alert-specific dismissal contexts.
    # ruff: ignore[import-outside-top-level]
    from weblate.trans.alerts.registry import get_alert_class
    from weblate.trans.models.component import (  # ruff: ignore[import-outside-top-level]
        Component,
    )

    dismissed_at = timezone.now()
    components = Component.objects.using(alerts.db).in_bulk(
        alerts.values_list("component_id", flat=True).distinct()
    )
    for alert in alerts.iterator():
        alert.dismissed_at = dismissed_at
        alert.dismissal_fingerprint = get_alert_class(
            alert.name
        ).get_dismissal_fingerprint(components[alert.component_id], alert.details)
        alert.save(update_fields=("dismissed_at", "dismissal_fingerprint"))


def backfill_dismissed_at(apps, schema_editor) -> None:
    Alert = apps.get_model("trans", "Alert")
    backfill_dismissals(Alert.objects.filter(dismissed=True))


def restore_dismissed(apps, schema_editor) -> None:
    Alert = apps.get_model("trans", "Alert")
    Alert.objects.filter(dismissed_at__isnull=False).update(dismissed=True)


class Migration(migrations.Migration):
    dependencies = [
        ("addons", "0014_addon_category"),
        ("screenshots", "0001_squashed_weblate_5"),
        ("trans", "0093_project_workspace_tm"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="dismissal_fingerprint",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="alert",
            name="dismissal_reason",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="alert",
            name="dismissed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="alert",
            name="dismissed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="dismissed_alerts",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(backfill_dismissed_at, restore_dismissed),
        migrations.RemoveField(
            model_name="alert",
            name="dismissed",
        ),
        migrations.AlterField(
            model_name="change",
            name="action",
            field=models.IntegerField(
                choices=[
                    (0, "Resource updated"),
                    (1, "Translation completed"),
                    (2, "Translation changed"),
                    (3, "Comment added"),
                    (4, "Suggestion added"),
                    (5, "Translation added"),
                    (6, "Automatically translated"),
                    (7, "Suggestion accepted"),
                    (8, "Translation reverted"),
                    (9, "Translation uploaded"),
                    (13, "Source string added"),
                    (14, "Component locked"),
                    (15, "Component unlocked"),
                    (17, "Changes committed"),
                    (18, "Changes pushed"),
                    (19, "Repository reset"),
                    (20, "Repository merged"),
                    (21, "Repository rebased"),
                    (22, "Repository merge failed"),
                    (23, "Repository rebase failed"),
                    (24, "Parsing failed"),
                    (25, "Translation removed"),
                    (26, "Suggestion removed"),
                    (27, "Translation replaced"),
                    (28, "Repository push failed"),
                    (29, "Suggestion removed during cleanup"),
                    (30, "Source string changed"),
                    (31, "String added"),
                    (32, "Bulk status changed"),
                    (33, "Visibility changed"),
                    (34, "User added"),
                    (35, "User removed"),
                    (36, "Translation approved"),
                    (37, "Marked for edit"),
                    (38, "Component removed"),
                    (39, "Project removed"),
                    (41, "Project renamed"),
                    (42, "Component renamed"),
                    (43, "Moved component"),
                    (45, "Contributor joined"),
                    (46, "Announcement posted"),
                    (47, "Alert triggered"),
                    (48, "Language added"),
                    (49, "Language requested"),
                    (50, "Project created"),
                    (51, "Component created"),
                    (52, "User invited"),
                    (53, "Repository notification received"),
                    (54, "Translation replaced file by upload"),
                    (55, "License changed"),
                    (56, "Contributor license agreement changed"),
                    (57, "Screenshot added"),
                    (58, "Screenshot uploaded"),
                    (59, "String updated in the repository"),
                    (60, "Add-on installed"),
                    (61, "Add-on configuration changed"),
                    (62, "Add-on uninstalled"),
                    (63, "String removed"),
                    (64, "Comment removed"),
                    (65, "Comment resolved"),
                    (66, "Explanation updated"),
                    (67, "Category removed"),
                    (68, "Category renamed"),
                    (69, "Category moved"),
                    (70, "Saving string failed"),
                    (71, "String added in the repository"),
                    (72, "String updated in the upload"),
                    (73, "String added in the upload"),
                    (74, "Translation updated by source upload"),
                    (75, "Component translation completed"),
                    (76, "Applied enforced check"),
                    (77, "Propagated change"),
                    (78, "File uploaded"),
                    (79, "Extra flags updated"),
                    (80, "Font uploaded"),
                    (81, "Font changed"),
                    (82, "Font removed"),
                    (83, "Forced synchronization of translations"),
                    (84, "Forced rescan of translations"),
                    (85, "Screenshot removed"),
                    (86, "Label added"),
                    (87, "Label removed"),
                    (88, "Repository cleanup"),
                    (89, "Source string added in the upload"),
                    (90, "Source string added in the repository"),
                    (91, "Project backed up"),
                    (92, "Project restored"),
                    (93, "Component restored"),
                    (94, "User edit reverted"),
                    (95, "Project setting changed"),
                    (96, "Component setting changed"),
                    (97, "User access changed"),
                    (98, "Workspace created"),
                    (99, "Workspace setting changed"),
                    (100, "Project moved"),
                    (101, "Remote repository updated"),
                    (102, "Remote repository update failed"),
                    (103, "Alert dismissed"),
                    (104, "Alert reopened"),
                ],
                default=2,
            ),
        ),
        migrations.AddIndex(
            model_name="alert",
            index=models.Index(
                condition=models.Q(("dismissed_at__isnull", True)),
                fields=["component", "severity"],
                name="trans_alert_active_idx",
            ),
        ),
    ]
