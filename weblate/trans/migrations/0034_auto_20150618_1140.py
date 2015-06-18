# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0033_auto_20150618_1138'),
    ]

    operations = [
        migrations.AlterField(
            model_name='project',
            name='slug',
            field=models.SlugField(help_text='Name used in URLs and file names.', unique=True, max_length=100, verbose_name='URL slug'),
        ),
        migrations.AlterField(
            model_name='subproject',
            name='slug',
            field=models.SlugField(help_text='Name used in URLs and file names.', max_length=100, verbose_name='URL slug'),
        ),
    ]
