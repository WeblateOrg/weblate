# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0029_auto_20150415_1318'),
    ]

    operations = [
        migrations.AddField(
            model_name='change',
            name='subproject',
            field=models.ForeignKey(to='trans.SubProject', null=True),
        ),
    ]
