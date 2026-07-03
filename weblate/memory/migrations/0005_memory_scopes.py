# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone
from django.utils.translation import pgettext_lazy


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0024_cleanup_stale_project_tokens"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("memory", "0004_memory_status_and_context"),
        ("trans", "0093_project_workspace_tm"),
        ("workspaces", "0003_workspace_translation_memory"),
    ]

    operations = [
        migrations.RenameField(
            model_name="memory",
            old_name="project",
            new_name="legacy_project",
        ),
        migrations.RenameField(
            model_name="memory",
            old_name="user",
            new_name="legacy_user",
        ),
        migrations.RenameField(
            model_name="memory",
            old_name="shared",
            new_name="legacy_shared",
        ),
        migrations.RenameField(
            model_name="memory",
            old_name="from_file",
            new_name="legacy_from_file",
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveIndex(
                    model_name="memory",
                    name="memory_from_file",
                ),
                migrations.AddIndex(
                    model_name="memory",
                    index=models.Index(
                        "legacy_from_file",
                        condition=models.Q(legacy_from_file=True),
                        name="memory_from_file",
                    ),
                ),
            ],
        ),
        migrations.AlterField(
            model_name="memory",
            name="legacy_project",
            field=models.ForeignKey(
                blank=True,
                default=None,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="trans.project",
            ),
        ),
        migrations.AlterField(
            model_name="memory",
            name="legacy_user",
            field=models.ForeignKey(
                blank=True,
                default=None,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name="MemoryScopeMigrationState",
            fields=[
                (
                    "name",
                    models.CharField(max_length=50, primary_key=True, serialize=False),
                ),
                ("last_memory_id", models.IntegerField(default=0)),
                ("completed", models.BooleanField(default=False)),
                ("updated", models.DateTimeField(default=timezone.now)),
            ],
            options={
                "verbose_name": "Translation memory scope migration state",
                "verbose_name_plural": "Translation memory scope migration states",
            },
        ),
        migrations.CreateModel(
            name="MemoryScope",
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
                    "scope",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (
                                1,
                                pgettext_lazy("Translation memory scope", "Project"),
                            ),
                            (
                                2,
                                pgettext_lazy("Translation memory scope", "Workspace"),
                            ),
                            (
                                3,
                                pgettext_lazy("Translation memory scope", "Shared"),
                            ),
                            (
                                4,
                                pgettext_lazy("Translation memory scope", "Personal"),
                            ),
                            (
                                5,
                                pgettext_lazy("Translation memory scope", "File"),
                            ),
                            (
                                6,
                                pgettext_lazy(
                                    "Translation memory scope", "Project file"
                                ),
                            ),
                            (
                                7,
                                pgettext_lazy(
                                    "Translation memory scope", "Personal file"
                                ),
                            ),
                        ],
                    ),
                ),
                (
                    "memory",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scopes",
                        to="memory.memory",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="trans.project",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="workspaces.workspace",
                    ),
                ),
                (
                    "source_project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="trans.project",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Translation memory scope",
                "verbose_name_plural": "Translation memory scopes",
            },
        ),
        migrations.AddIndex(
            model_name="memoryscope",
            index=models.Index(
                fields=["scope", "memory"], name="memory_scope_scope_memory"
            ),
        ),
        migrations.AddIndex(
            model_name="memoryscope",
            index=models.Index(
                fields=["scope", "project", "memory"], name="memory_scope_project"
            ),
        ),
        migrations.AddIndex(
            model_name="memoryscope",
            index=models.Index(
                fields=["scope", "workspace", "memory"],
                name="memory_scope_workspace",
            ),
        ),
        migrations.AddIndex(
            model_name="memoryscope",
            index=models.Index(
                fields=["scope", "source_project", "memory"],
                name="memory_scope_source_project",
            ),
        ),
        migrations.AddIndex(
            model_name="memoryscope",
            index=models.Index(
                fields=["scope", "workspace", "source_project", "memory"],
                name="memory_scope_workspace_source",
            ),
        ),
        migrations.AddIndex(
            model_name="memoryscope",
            index=models.Index(
                fields=["scope", "user", "memory"], name="memory_scope_user"
            ),
        ),
        migrations.AddConstraint(
            model_name="memoryscope",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("project__isnull", False),
                    ("scope__in", (1, 6)),
                ),
                fields=("memory", "scope", "project"),
                name="memory_scope_unique_project",
            ),
        ),
        migrations.AddConstraint(
            model_name="memoryscope",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("scope", 2),
                    ("source_project__isnull", False),
                    ("workspace__isnull", False),
                ),
                fields=("memory", "scope", "workspace", "source_project"),
                name="memory_scope_unique_workspace",
            ),
        ),
        migrations.AddConstraint(
            model_name="memoryscope",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("scope", 2),
                    ("source_project__isnull", True),
                    ("workspace__isnull", False),
                ),
                fields=("memory", "scope", "workspace"),
                name="memory_scope_workspace_null",
            ),
        ),
        migrations.AddConstraint(
            model_name="memoryscope",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("scope__in", (4, 7)),
                    ("user__isnull", False),
                ),
                fields=("memory", "scope", "user"),
                name="memory_scope_unique_user",
            ),
        ),
        migrations.AddConstraint(
            model_name="memoryscope",
            constraint=models.UniqueConstraint(
                condition=models.Q(("scope", 5)),
                fields=("memory", "scope"),
                name="memory_scope_unique_global",
            ),
        ),
        migrations.AddConstraint(
            model_name="memoryscope",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("scope", 3),
                    ("source_project__isnull", False),
                ),
                fields=("memory", "scope", "source_project"),
                name="memory_scope_unique_shared",
            ),
        ),
        migrations.AddConstraint(
            model_name="memoryscope",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("scope", 3),
                    ("source_project__isnull", True),
                ),
                fields=("memory", "scope"),
                name="memory_scope_shared_null",
            ),
        ),
    ]
