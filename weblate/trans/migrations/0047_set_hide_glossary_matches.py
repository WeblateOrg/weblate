# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations


def forwards(apps, schema_editor):
    Component = apps.get_model("trans", "Component")
    # For glossary components, hide  hide glossary matches by default
    Component.objects.filter(is_glossary=True).update(hide_glossary_matches=True)


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0046_component_hide_glossary_matches"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
