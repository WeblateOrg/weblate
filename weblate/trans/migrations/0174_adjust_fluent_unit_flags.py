# Copyright © Henry Wilkes <henry@torproject.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations

from weblate.checks.flags import Flags


def fix_fluent_flags(apps, schema_editor):
    Unit = apps.get_model("trans", "Unit")
    db_alias = schema_editor.connection.alias

    updates = []
    for unit in Unit.objects.using(db_alias).filter(
        translation__component__file_format="fluent"
    ):
        # Remove old placeholders, this was used for references, which is now
        # handled by the fluent-references check instead.
        unit_flags = Flags(unit.flags)
        if "placeholders" in unit_flags:
            unit_flags.remove("placeholders")

        if "fluent-type" not in unit_flags:
            # Add fluent_type flag based on the current id.
            if unit.context and unit.context.startswith("-"):
                unit_flags.set_value("fluent-type", "Term")
            else:
                unit_flags.set_value("fluent-type", "Message")

        unit.flags = unit_flags.format()

        updates.append(unit)

    Unit.objects.using(db_alias).bulk_update(updates, ["flags"])


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0173_change_duplicate_string"),
    ]

    operations = [migrations.RunPython(fix_fluent_flags, elidable=True)]
