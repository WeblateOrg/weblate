# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def fill_in_owners(apps, schema_editor):
    Project = apps.get_model('trans', 'Project')

    for project in Project.objects.all():
        if project.owner:
            project.owners.add(project.owner)


def fill_in_owner(apps, schema_editor):
    Project = apps.get_model('trans', 'Project')

    for project in Project.objects.all():
        if project.owners.exists():
            project.owner = project.owners.all()[0]
            project.save()


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0037_auto_20150810_1348'),
    ]

    operations = [
        migrations.RunPython(
            fill_in_owners,
            reverse_code=fill_in_owner,
        ),
    ]
