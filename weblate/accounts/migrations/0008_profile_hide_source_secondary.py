# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_auto_20150427_1505'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='hide_source_secondary',
            field=models.BooleanField(default=False, verbose_name='Hide source if there is secondary language'),
        ),
    ]
