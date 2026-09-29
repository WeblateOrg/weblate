# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

# Generated manually
from typing import TYPE_CHECKING

from django.db import migrations, models

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps


def set_inherit_enforced_checks(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    Component = apps.get_model("trans", "Component")
    # Components with custom enforced_checks should not inherit
    Component.objects.exclude(enforced_checks=[]).update(inherit_enforced_checks=False)
    # Components with empty enforced_checks (default) should inherit
    Component.objects.filter(enforced_checks=[]).update(inherit_enforced_checks=True)


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0107_xliff_format_params"),
    ]

    operations = [
        migrations.AddField(
            model_name="component",
            name="inherit_enforced_checks",
            field=models.BooleanField(
                default=True,
                verbose_name="Inherit enforced checks",
                help_text="Use enforced checks from the project, category or workspace.",
            ),
        ),
        migrations.RunPython(
            set_inherit_enforced_checks, reverse_code=migrations.RunPython.noop
        ),
    ]
