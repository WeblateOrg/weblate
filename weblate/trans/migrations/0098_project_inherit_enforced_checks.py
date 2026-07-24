# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations, models


def set_project_inherit_enforced_checks(apps, schema_editor):
    Project = apps.get_model('trans', 'Project')
    # Projects with custom enforced_checks should not inherit
    Project.objects.exclude(enforced_checks=[]).update(inherit_enforced_checks=False)
    # Projects with empty enforced_checks (default) should inherit
    Project.objects.filter(enforced_checks=[]).update(inherit_enforced_checks=True)


class Migration(migrations.Migration):
    dependencies = [
        ('trans', '0097_component_inherit_enforced_checks'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='enforced_checks',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='List of checks which can not be dismissed.',
                verbose_name='Enforced checks',
            ),
        ),
        migrations.AddField(
            model_name='project',
            name='inherit_enforced_checks',
            field=models.BooleanField(
                default=True,
                help_text='Use enforced checks from the workspace.',
                verbose_name='Inherit enforced checks',
            ),
        ),
        migrations.RunPython(
            set_project_inherit_enforced_checks,
            reverse_code=migrations.RunPython.noop,
        ),
    ]