# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0044_auto_20150916_0952'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='change',
            options={'ordering': ['-timestamp'], 'permissions': (('download_changes', 'Can download changes'),)},
        ),
    ]
