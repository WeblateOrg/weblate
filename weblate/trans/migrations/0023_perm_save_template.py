# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0022_auto_20150309_0932'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='unit',
            options={'ordering': ['priority', 'position'], 'permissions': (('save_translation', 'Can save translation'), ('save_template', 'Can save template'),)},
        ),
    ]
