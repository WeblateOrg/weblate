# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0019_auto_20150220_1354'),
    ]

    operations = [
        migrations.AlterField(
            model_name='indexupdate',
            name='unit',
            field=models.OneToOneField(to='trans.Unit'),
            preserve_default=True,
        ),
    ]
