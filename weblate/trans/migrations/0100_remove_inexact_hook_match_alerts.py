# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations


def remove_inexact_hook_match_alerts(apps, schema_editor) -> None:
    Alert = apps.get_model("trans", "Alert")
    Alert.objects.filter(name="InexactHookMatch").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0099_sanitize_repository_redirect_credentials"),
    ]

    operations = [
        migrations.RunPython(
            remove_inexact_hook_match_alerts,
            migrations.RunPython.noop,
            elidable=True,
        ),
    ]
