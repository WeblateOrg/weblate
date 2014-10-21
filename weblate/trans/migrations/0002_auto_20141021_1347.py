# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='enable_hooks',
            field=models.BooleanField(default=True, help_text='Whether to allow updating this repository by remote hooks.', verbose_name='Enable hooks'),
            preserve_default=True,
        ),
    ]
