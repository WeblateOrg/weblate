# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from weblate.trans.data import migrate_data_dirs, unmigrate_data_dirs


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0013_auto_20141124_1036'),
    ]

    operations = [
        migrations.RunPython(
            migrate_data_dirs,
            reverse_code=unmigrate_data_dirs,
        ),
    ]
