# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Generated migration to set all Memory instances status to 'active'

from django.db import migrations


def set_status_to_active(apps, schema_editor):
    """Set status to 'active' for all existing Memory instances."""
    Memory = apps.get_model("memory", "Memory")
    Memory.objects.update(status=1)


def reverse_set_status_to_active(apps, schema_editor):
    """Reverse operation - set status back to 'pending' for all Memory instances."""
    Memory = apps.get_model("memory", "Memory")
    Memory.objects.update(status=0)


class Migration(migrations.Migration):
    dependencies = [
        ("memory", "0004_memory_status"),
    ]

    operations = [
        migrations.RunPython(
            set_status_to_active,
            reverse_set_status_to_active,
        ),
    ]
