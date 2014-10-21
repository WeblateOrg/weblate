# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations

def fill_in_fields(apps, schema_editor):
    SubProject = apps.get_model('trans', 'SubProject')

    for subproject in SubProject.objects.all():
        subproject.license = subproject.project.license
        subproject.license_url = subproject.project.license_url
        subproject.new_lang = subproject.project.new_lang
        subproject.merge_style = subproject.project.merge_style
        subproject.commit_message = subproject.project.commit_message
        subproject.committer_name = subproject.project.committer_name
        subproject.committer_email = subproject.project.committer_email
        subproject.save()


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0004_auto_20141021_1550'),
    ]

    operations = [
        migrations.RunPython(fill_in_fields),
    ]
