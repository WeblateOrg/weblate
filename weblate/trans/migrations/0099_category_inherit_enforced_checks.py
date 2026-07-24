# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations, models


def set_category_inherit_enforced_checks(apps, schema_editor):
    Category = apps.get_model('trans', 'Category')
    # Categories with custom enforced_checks should not inherit
    Category.objects.exclude(enforced_checks=[]).update(inherit_enforced_checks=False)
    # Categories with empty enforced_checks (default) should inherit
    Category.objects.filter(enforced_checks=[]).update(inherit_enforced_checks=True)


class Migration(migrations.Migration):
    dependencies = [
        ('trans', '0098_project_inherit_enforced_checks'),
    ]

    operations = [
        migrations.AddField(
            model_name='category',
            name='enforced_checks',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='List of checks which can not be dismissed.',
                verbose_name='Enforced checks',
            ),
        ),
        migrations.AddField(
            model_name='category',
            name='inherit_enforced_checks',
            field=models.BooleanField(
                default=True,
                help_text='Use enforced checks from the parent category, project or workspace.',
                verbose_name='Inherit enforced checks',
            ),
        ),
        migrations.RunPython(
            set_category_inherit_enforced_checks,
            reverse_code=migrations.RunPython.noop,
        ),
    ]