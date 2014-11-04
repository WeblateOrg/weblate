# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0007_auto_20141022_1159'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subproject',
            name='name',
            field=models.CharField(help_text='Name to display', max_length=100, verbose_name='Component name'),
            preserve_default=True,
        ),
    ]
