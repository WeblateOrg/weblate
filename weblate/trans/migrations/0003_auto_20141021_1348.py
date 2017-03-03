# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0002_auto_20141021_1347'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subproject',
            name='allow_translation_propagation',
            field=models.BooleanField(default=True, help_text='Whether translation updates in other resources will cause automatic translation in this one', verbose_name='Allow translation propagation'),
        ),
        migrations.AlterField(
            model_name='subproject',
            name='locked',
            field=models.BooleanField(default=False, help_text='Whether resource is locked for translation updates.', verbose_name='Locked'),
        ),
        migrations.AlterField(
            model_name='subproject',
            name='name',
            field=models.CharField(help_text='Name to display', max_length=100, verbose_name='Resource name'),
        ),
        migrations.AlterField(
            model_name='subproject',
            name='repo',
            field=models.CharField(help_text='URL of Git repository, use weblate://project/resource for sharing with other resource.', max_length=200, verbose_name='Source code repository'),
        ),
    ]
