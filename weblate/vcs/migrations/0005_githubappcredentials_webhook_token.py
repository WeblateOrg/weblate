# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from django.db import migrations, models


def populate_webhook_token(apps, schema_editor):
    GitHubAppCredentials = apps.get_model("vcs", "GitHubAppCredentials")
    for credentials in GitHubAppCredentials.objects.all():
        credentials.webhook_token = uuid.uuid4()
        credentials.save(update_fields=["webhook_token"])


class Migration(migrations.Migration):
    dependencies = [
        ("vcs", "0004_githubappcredentials"),
    ]

    operations = [
        migrations.AddField(
            model_name="githubappcredentials",
            name="webhook_token",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                verbose_name="Webhook token",
            ),
        ),
        migrations.RunPython(
            populate_webhook_token, reverse_code=migrations.RunPython.noop
        ),
        migrations.AlterField(
            model_name="githubappcredentials",
            name="webhook_token",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
                verbose_name="Webhook token",
            ),
        ),
    ]
