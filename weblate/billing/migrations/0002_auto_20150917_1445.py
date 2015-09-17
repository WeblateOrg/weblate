# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='plan',
            name='limit_languages',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='plan',
            name='limit_projects',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='plan',
            name='limit_repositories',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='plan',
            name='limit_strings',
            field=models.IntegerField(default=0),
        ),
    ]
