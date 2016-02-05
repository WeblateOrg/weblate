# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0058_componentlist'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='componentlist',
            name='title',
        ),
        migrations.AddField(
            model_name='componentlist',
            name='name',
            field=models.CharField(default='uhno', help_text='Name to display', unique=True, max_length=100, verbose_name='Component list name'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='componentlist',
            name='slug',
            field=models.SlugField(default='uteho', max_length=100, help_text='Name used in URLs and file names.', unique=True, verbose_name='URL slug'),
            preserve_default=False,
        ),
    ]
