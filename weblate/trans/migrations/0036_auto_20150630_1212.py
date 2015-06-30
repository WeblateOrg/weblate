# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0035_auto_20150630_1208'),
    ]

    operations = [
        migrations.AlterField(
            model_name='unit',
            name='target',
            field=models.TextField(default=b'', db_index=True, blank=True),
        ),
    ]
