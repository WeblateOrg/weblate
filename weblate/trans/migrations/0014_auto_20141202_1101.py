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
            lambda apps, schema_editor: migrate_data_dirs(),
            reverse_code=lambda apps, schema_editor: unmigrate_data_dirs(),
        ),
    ]
