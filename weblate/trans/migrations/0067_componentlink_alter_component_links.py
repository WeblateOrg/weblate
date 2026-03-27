# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0066_alter_variant_key"),
    ]

    operations = [
        # The auto-generated M2M table trans_component_links already exists
        # with columns (id, component_id, project_id). Use SeparateDatabaseAndState
        # to register the explicit through model without touching the database.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="ComponentLink",
                    fields=[
                        (
                            "id",
                            models.AutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "component",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                to="trans.component",
                            ),
                        ),
                        (
                            "project",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                to="trans.project",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "trans_component_links",
                        "unique_together": {("component", "project")},
                    },
                ),
                migrations.AlterField(
                    model_name="component",
                    name="links",
                    field=models.ManyToManyField(
                        blank=True,
                        help_text="Choose additional projects where this component will be listed.",
                        related_name="shared_components",
                        through="trans.ComponentLink",
                        to="trans.project",
                        verbose_name="Share in projects",
                    ),
                ),
            ],
            database_operations=[],
        ),
        # Now add the category column via standard AddField.
        migrations.AddField(
            model_name="componentlink",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="trans.category",
            ),
        ),
    ]
