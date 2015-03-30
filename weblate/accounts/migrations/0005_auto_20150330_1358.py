# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_auto_20150108_1424'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='languages',
            field=models.ManyToManyField(help_text='Choose languages to which you can translate.', to='lang.Language', verbose_name='Translated languages', blank=True),
            preserve_default=True,
        ),
    ]
