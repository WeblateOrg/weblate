# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_auto_20140923_1543'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='subscriptions',
            field=models.ManyToManyField(to='trans.Project', verbose_name='Subscribed projects', blank=True),
            preserve_default=True,
        ),
    ]
