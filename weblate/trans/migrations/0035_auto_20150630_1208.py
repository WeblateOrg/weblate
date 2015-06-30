# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0034_auto_20150618_1140'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subproject',
            name='allow_translation_propagation',
            field=models.BooleanField(default=True, help_text='Whether translation updates in other components will cause automatic translation in this one', db_index=True, verbose_name='Allow translation propagation'),
        ),
    ]
