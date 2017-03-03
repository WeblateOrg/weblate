# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0047_project_source_language'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dictionary',
            name='source',
            field=models.CharField(max_length=190, db_index=True),
        ),
        migrations.AlterField(
            model_name='dictionary',
            name='target',
            field=models.CharField(max_length=190),
        ),
    ]
