# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0014_auto_20141202_1101'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='source',
            options={'permissions': (('edit_priority', 'Can edit priority'), ('edit_flags', 'Can edit check flags'))},
        ),
    ]
