# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('lang', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='language',
            options={'ordering': ['name'], 'verbose_name': 'Language', 'verbose_name_plural': 'Languages'},
        ),
    ]
