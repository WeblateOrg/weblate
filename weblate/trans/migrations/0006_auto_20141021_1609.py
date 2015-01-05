# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0005_auto_20141021_1550'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='project',
            name='commit_message',
        ),
        migrations.RemoveField(
            model_name='project',
            name='committer_email',
        ),
        migrations.RemoveField(
            model_name='project',
            name='committer_name',
        ),
        migrations.RemoveField(
            model_name='project',
            name='license',
        ),
        migrations.RemoveField(
            model_name='project',
            name='license_url',
        ),
        migrations.RemoveField(
            model_name='project',
            name='merge_style',
        ),
        migrations.RemoveField(
            model_name='project',
            name='new_lang',
        ),
    ]
