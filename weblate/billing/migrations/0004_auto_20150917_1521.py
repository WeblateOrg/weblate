# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0003_auto_20150917_1457'),
    ]

    operations = [
        migrations.AlterField(
            model_name='plan',
            name='price',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='plan',
            name='yearly_price',
            field=models.IntegerField(default=0),
        ),
    ]
