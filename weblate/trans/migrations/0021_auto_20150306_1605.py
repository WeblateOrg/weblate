# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0020_auto_20150220_1356'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subproject',
            name='branch',
            field=models.CharField(default=b'', help_text='Repository branch to translate', max_length=50, verbose_name='Repository branch', blank=True),
            preserve_default=True,
        ),
    ]
