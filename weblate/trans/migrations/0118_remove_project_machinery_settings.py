# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0117_change_addon_redact_automation_workflow"),
        ("machinery", "0002_import_settings"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="project",
            name="machinery_settings",
        ),
    ]
