# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("memory", "0004_memory_status_and_context"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="memory",
            index=models.Index(
                "source_language",
                "target_language",
                condition=Q(from_file=True),
                name="memory_file_lang_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="memory",
            index=models.Index(
                "project",
                "source_language",
                "target_language",
                condition=Q(project__isnull=False, shared=False),
                name="memory_project_lang_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="memory",
            index=models.Index(
                "user",
                "source_language",
                "target_language",
                condition=Q(user__isnull=False, shared=False),
                name="memory_user_lang_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="memory",
            index=models.Index(
                "source_language",
                "target_language",
                condition=Q(shared=True),
                name="memory_shared_lang_idx",
            ),
        ),
    ]
