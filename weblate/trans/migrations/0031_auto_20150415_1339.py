# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def fill_in_subproject(apps, schema_editor):
    Change = apps.get_model('trans', 'Change')

    actions = set((14, 15, 16, 18, 19, 20, 21, 22, 23))

    for change in Change.objects.all():
        if change.subproject:
            continue
        if change.action in actions and change.translation:
            change.subproject = change.translation.subproject
            change.translation = None
            change.save()
        elif change.translation:
            change.subproject = change.translation.subproject
            change.save()


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0030_change_subproject'),
    ]

    operations = [
        migrations.RunPython(fill_in_subproject),
    ]
