# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0011_auto_20141114_1008'),
    ]

    operations = [
        migrations.AddField(
            model_name='translation',
            name='have_comment',
            field=models.IntegerField(default=0, db_index=True),
            preserve_default=True,
        ),
    ]
