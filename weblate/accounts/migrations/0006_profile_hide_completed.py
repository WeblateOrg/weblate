# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_auto_20150330_1358'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='hide_completed',
            field=models.BooleanField(default=False, verbose_name='Hide completed translations on dashboard'),
            preserve_default=True,
        ),
    ]
