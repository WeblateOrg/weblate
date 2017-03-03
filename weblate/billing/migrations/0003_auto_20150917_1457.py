# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0002_auto_20150917_1445'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='plan',
            options={'ordering': ['price']},
        ),
        migrations.AddField(
            model_name='plan',
            name='yearly_price',
            field=models.IntegerField(default=0),
            preserve_default=False,
        ),
    ]
